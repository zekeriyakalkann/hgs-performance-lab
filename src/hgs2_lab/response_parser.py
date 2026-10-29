"""HTTP yanıt gövdesi ayrıştırıcısı: ham yanıttan güvenli, yapılandırılmış bir özet ve iş sonucu çıkarır (ağ yok).

Ayrıştırıcı yalnızca yanıtta açıkça yazanı çıkarır; iş sonucunun anlamını (başarı mı, ret mi, hata mı)
belirlemez. Anlam, testin beklenen sonucuyla karşılaştırılarak sınıflandırıcıda (classify.py) verilir.

Tanınan iş sonucu değerleri (`RECOGNIZED_BUSINESS_OUTCOMES`) HGS2 kaynak kodundan statik olarak doğrulanmıştır
(bkz. README "Gerçek HGS2 API sözleşmesi"); gerçek HGS2'ye hiç istek gönderilmedi:

* düz metin (`text/plain`): ONAYLANDI, REDDEDILDI (AuthController); OK, HATA (TerminalEnrollmentController);
  NONE, SCAN_CARD, SCAN_FP, SCAN_SCHOOL_NO (`GET /api/sensor/pending`, SensorCaptureService.getPendingAction);
* JSON `status` alanı: WAITING, READY (`GET /api/sensor/result`, SensorCaptureController.pollResult).

KAYDEDILDI HGS2'nin HTTP yanıtlarında yoktur (yalnızca veritabanındaki `logs.sonuc` değeridir); önceki sürümle
yazılmış kayıtlar ve beklentilerle uyum için tanınmaya devam eder. Değerler yalnızca metin olarak tanınır; her uçta
aynı anlama geldikleri varsayılmaz (READY "sensör değeri hazır" demektir, kimlik doğrulama onayı değildir).

Kurallar (`rule_id`):

| Kural | Koşul | `business_outcome` |
|---|---|---|
| `R-NO-RESPONSE` | HTTP yanıtı yok (taşıma hatası) | None |
| `R-BODY-NOT-CAPTURED` | Taşıyıcı gövdeyi vermedi | None |
| `R-EMPTY-BODY` | Gövde boş | None |
| `R-TOO-LARGE` | Gövde `MAX_PARSE_BYTES`'tan büyük; ayrıştırılmadı | None |
| `R-UNSUPPORTED-TYPE` | İçerik türü metin veya JSON değil | None |
| `R-UNDECODABLE` | Gövde bildirilen/varsayılan karakter kümesiyle çözülemedi | None |
| `R-TEXT-TOKEN` | Düz metin gövdenin TAMAMI (boşluklar ve büyük/küçük harf hariç) tanınan bir değer | değer |
| `R-TEXT-UNRECOGNIZED` | Düz metin, tanınan bir değer değil (alt dize araması yapılmaz) | None |
| `R-JSON-STRING` | JSON gövde tek bir metin (`"REDDEDILDI"`; Spring'in text/plain olmayan dönüşü) ve tanınan değer | değer |
| `R-JSON-FIELD` | JSON nesnesinin üst düzey `business_outcome` alanı tanınan bir değer (Lab'in kendi sözleşmesi) | değer |
| `R-JSON-STATUS` | `business_outcome` alanı yok; üst düzey `status` alanı metin ve `SENSOR_STATUS_OUTCOMES`'tan biri (HGS2 sensör sonucu) | değer |
| `R-JSON-UNRECOGNIZED` | Geçerli JSON ama yukarıdaki biçimlerden biri değil (iç içe alanlar aranmaz; sayısal `status`, ör. Spring hata gövdesi, tanınmaz) | None |
| `R-MALFORMED-JSON` | İçerik türü JSON ama gövde geçerli JSON değil | None |

İçerik türü yoksa gövde düz metin kurallarıyla değerlendirilir ve `content_type_missing` uyarısı eklenir.

Gizlilik: özet yalnızca medya türünü, bayt sayısını, kuralı, uyarıları ve izin listesindeki iş sonucu değerini
taşır. Gövdenin kendisi, bir kısmı veya özeti (hash) hiçbir zaman çıktıya yazılmaz.
"""

from __future__ import annotations

import codecs
import json
import re
from dataclasses import dataclass
from typing import Any

PARSER_VERSION = "response-parser-v2"
# HGS2'nin iş sonucu yanıtları birkaç baytlık düz metindir; 4 KiB tek bir iş sonucu için fazlasıyla yeterlidir ve
# büyük gövdelerin (ör. liste uçları) ayrıştırılmasını önler. Ölçüm (duration_ms) gövdenin tamamını okumaya devam eder.
MAX_PARSE_BYTES = 4096

# HGS2 `GET /api/sensor/result` JSON gövdesinin `status` alanı: {"status":"WAITING"} / {"status":"READY","value":…}.
# `value` (yakalanan kart/numara/slot) hiçbir zaman okunmaz ve yazılmaz.
SENSOR_STATUS_OUTCOMES = frozenset({"WAITING", "READY"})
RECOGNIZED_BUSINESS_OUTCOMES = frozenset({
    "ONAYLANDI", "REDDEDILDI", "OK", "HATA", "KAYDEDILDI",
    "NONE", "SCAN_CARD", "SCAN_FP", "SCAN_SCHOOL_NO",
}) | SENSOR_STATUS_OUTCOMES
JSON_OUTCOME_FIELD = "business_outcome"
JSON_STATUS_FIELD = "status"

STATE_NO_RESPONSE = "no_response"
STATE_NOT_CAPTURED = "not_captured"
STATE_EMPTY = "empty"
STATE_TOO_LARGE = "too_large"
STATE_UNSUPPORTED = "unsupported"
STATE_UNDECODABLE = "undecodable"
STATE_TEXT = "text"
STATE_JSON = "json"
STATE_MALFORMED_JSON = "malformed_json"
BODY_STATES = frozenset({STATE_NO_RESPONSE, STATE_NOT_CAPTURED, STATE_EMPTY, STATE_TOO_LARGE, STATE_UNSUPPORTED,
                         STATE_UNDECODABLE, STATE_TEXT, STATE_JSON, STATE_MALFORMED_JSON})

_RULE_IDS = frozenset({
    "R-NO-RESPONSE", "R-BODY-NOT-CAPTURED", "R-EMPTY-BODY", "R-TOO-LARGE", "R-UNSUPPORTED-TYPE", "R-UNDECODABLE",
    "R-TEXT-TOKEN", "R-TEXT-UNRECOGNIZED", "R-JSON-STRING", "R-JSON-FIELD", "R-JSON-STATUS", "R-JSON-UNRECOGNIZED",
    "R-MALFORMED-JSON",
})
# Gövde okundu ama içinden tanınan bir iş sonucu çıkmadı (ya da gövde biçimi okunamadı). Sınıflandırıcı bu kuralları,
# yalnızca durum kodu beklentisi karşılandığı için PASS vermemek üzere kullanır (classify.py, H-STATUS-OK-UNKNOWN-BODY).
UNRECOGNIZED_BODY_RULES = frozenset({
    "R-TEXT-UNRECOGNIZED", "R-JSON-UNRECOGNIZED", "R-MALFORMED-JSON", "R-UNDECODABLE", "R-UNSUPPORTED-TYPE",
})
_WARNING_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_MEDIA_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$")
_CHARSET_RE = re.compile(r";\s*charset\s*=\s*\"?([A-Za-z0-9._:-]{1,40})\"?", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedResponse:
    """Bir HTTP yanıtının güvenli özeti. Ham gövde içermez."""

    status_code: int | None  # geçersiz/eksikse None (+ uyarı)
    media_type: str | None  # yalnızca `tür/alt tür`, küçük harf; parametreler atılır
    body_state: str
    body_bytes: int | None
    parseable: bool  # gövde, desteklenen bir biçim olarak (metin veya JSON) okunabildi mi
    business_outcome: str | None  # yalnızca RECOGNIZED_BUSINESS_OUTCOMES'tan biri
    rule_id: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status_code": self.status_code, "media_type": self.media_type, "body_state": self.body_state,
                "body_bytes": self.body_bytes, "parseable": self.parseable,
                "business_outcome": self.business_outcome, "rule_id": self.rule_id, "warnings": list(self.warnings)}

    @classmethod
    def from_dict(cls, data: Any) -> "ParsedResponse":
        """`to_dict` çıktısını (ör. metadata'dan) doğrulayarak geri kurar; tutarsız girdide ValueError (değer yazılmaz)."""
        keys = {"status_code", "media_type", "body_state", "body_bytes", "parseable", "business_outcome", "rule_id",
                "warnings"}
        if not isinstance(data, dict) or not keys <= set(data):
            raise ValueError("Yanıt ayrıştırma özeti eksik alan içeriyor")
        status, media, size = data["status_code"], data["media_type"], data["body_bytes"]
        outcome, warnings = data["business_outcome"], data["warnings"]
        if status is not None and (isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599):
            raise ValueError("Yanıt ayrıştırma özetinde geçersiz durum kodu")
        if media is not None and (not isinstance(media, str) or not _MEDIA_TYPE_RE.match(media)):
            raise ValueError("Yanıt ayrıştırma özetinde geçersiz medya türü")
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
            raise ValueError("Yanıt ayrıştırma özetinde geçersiz bayt sayısı")
        if data["body_state"] not in BODY_STATES or data["rule_id"] not in _RULE_IDS                 or not isinstance(data["parseable"], bool):
            raise ValueError("Yanıt ayrıştırma özetinde bilinmeyen durum veya kural")
        if outcome is not None and outcome not in RECOGNIZED_BUSINESS_OUTCOMES:
            raise ValueError("Yanıt ayrıştırma özetinde tanınmayan iş sonucu")
        if not isinstance(warnings, list) or not all(isinstance(w, str) and _WARNING_RE.match(w) for w in warnings):
            raise ValueError("Yanıt ayrıştırma özetinde geçersiz uyarı listesi")
        return cls(status, media, data["body_state"], size, data["parseable"], outcome, data["rule_id"],
                   tuple(warnings))


def _media_type(content_type: str | None, warnings: list[str]) -> tuple[str | None, str | None]:
    """(medya türü, karakter kümesi). Geçersiz başlık güvenli biçimde None olur."""
    if content_type is None or not content_type.strip():
        warnings.append("content_type_missing")
        return None, None
    media = content_type.split(";", 1)[0].strip().lower()
    if not _MEDIA_TYPE_RE.match(media):
        warnings.append("content_type_invalid")
        return None, None
    match = _CHARSET_RE.search(content_type)
    return media, (match.group(1) if match else None)


def _is_json(media: str | None) -> bool:
    return media is not None and (media == "application/json" or media.endswith("+json"))


def _is_text(media: str | None) -> bool:
    return media is None or media == "text/plain"


def _token(value: str) -> str | None:
    candidate = value.strip().upper()
    return candidate if candidate in RECOGNIZED_BUSINESS_OUTCOMES else None


def _valid_status(status_code: Any, warnings: list[str]) -> int | None:
    if status_code is None:
        return None
    if isinstance(status_code, bool) or not isinstance(status_code, int) or not 100 <= status_code <= 599:
        warnings.append("invalid_status_code")
        return None
    return status_code


def parse_response(
    status_code: int | None,
    content_type: str | None,
    body: bytes | None,
    *,
    response_received: bool = True,
) -> ParsedResponse:
    """Yanıtı ayrıştırır. Hiçbir girdi istisna fırlatmaz; sorunlar `rule_id` ve `warnings` ile bildirilir.

    `response_received=False`: taşıma hatası (zaman aşımı, bağlantı kopması); durum kodu ve gövde yok sayılır.
    """
    warnings: list[str] = []
    if not response_received:
        return ParsedResponse(None, None, STATE_NO_RESPONSE, None, False, None, "R-NO-RESPONSE", ())
    status = _valid_status(status_code, warnings)
    if status_code is None:
        warnings.append("status_code_missing")
    if content_type is not None and not isinstance(content_type, str):
        content_type = None
        warnings.append("content_type_invalid")

    def result(state: str, rule: str, *, size: int | None, media: str | None, parseable: bool = False,
               outcome: str | None = None) -> ParsedResponse:
        return ParsedResponse(status, media, state, size, parseable, outcome, rule, tuple(warnings))

    if body is None:
        media, _ = _media_type(content_type, []) if content_type else (None, None)
        return result(STATE_NOT_CAPTURED, "R-BODY-NOT-CAPTURED", size=None, media=media)
    if not isinstance(body, (bytes, bytearray)):
        warnings.append("body_not_bytes")
        return result(STATE_NOT_CAPTURED, "R-BODY-NOT-CAPTURED", size=None, media=None)
    size = len(body)
    if size == 0:
        media, _ = _media_type(content_type, []) if content_type else (None, None)
        warnings.append("empty_body")
        return result(STATE_EMPTY, "R-EMPTY-BODY", size=0, media=media)
    media, charset = _media_type(content_type, warnings)
    if size > MAX_PARSE_BYTES:
        warnings.append("body_too_large_not_parsed")
        return result(STATE_TOO_LARGE, "R-TOO-LARGE", size=size, media=media)
    if not (_is_text(media) or _is_json(media)):
        warnings.append("unsupported_content_type")
        return result(STATE_UNSUPPORTED, "R-UNSUPPORTED-TYPE", size=size, media=media)

    encoding = charset or "utf-8-sig"
    try:
        codecs.lookup(encoding)
    except LookupError:
        warnings.append("unknown_charset")
        return result(STATE_UNDECODABLE, "R-UNDECODABLE", size=size, media=media)
    try:
        text = bytes(body).decode("utf-8-sig" if encoding.lower().replace("_", "-") in ("utf-8", "utf8") else encoding)
    except (UnicodeDecodeError, ValueError, LookupError):
        warnings.append("body_decode_error")
        return result(STATE_UNDECODABLE, "R-UNDECODABLE", size=size, media=media)

    if _is_json(media):
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, RecursionError):
            warnings.append("malformed_json")
            return result(STATE_MALFORMED_JSON, "R-MALFORMED-JSON", size=size, media=media)
        if isinstance(data, str) and _token(data):
            return result(STATE_JSON, "R-JSON-STRING", size=size, media=media, parseable=True, outcome=_token(data))
        if isinstance(data, dict) and isinstance(data.get(JSON_OUTCOME_FIELD), str) \
                and _token(data[JSON_OUTCOME_FIELD]):
            return result(STATE_JSON, "R-JSON-FIELD", size=size, media=media, parseable=True,
                          outcome=_token(data[JSON_OUTCOME_FIELD]))
        if isinstance(data, dict) and JSON_OUTCOME_FIELD in data:
            warnings.append("business_outcome_field_unrecognized")
        elif isinstance(data, dict) and isinstance(data.get(JSON_STATUS_FIELD), str):
            status_value = data[JSON_STATUS_FIELD].strip().upper()
            if status_value in SENSOR_STATUS_OUTCOMES:
                return result(STATE_JSON, "R-JSON-STATUS", size=size, media=media, parseable=True,
                              outcome=status_value)
            warnings.append("status_field_unrecognized")
        else:
            warnings.append("business_outcome_not_found")
        return result(STATE_JSON, "R-JSON-UNRECOGNIZED", size=size, media=media, parseable=True)

    outcome = _token(text)
    if outcome is not None:
        return result(STATE_TEXT, "R-TEXT-TOKEN", size=size, media=media, parseable=True, outcome=outcome)
    warnings.append("business_outcome_not_recognized")
    return result(STATE_TEXT, "R-TEXT-UNRECOGNIZED", size=size, media=media, parseable=True)
