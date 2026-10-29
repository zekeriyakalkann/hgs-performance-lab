"""Hassas değerlerin sonuçlara, metadata'ya ve analiz çıktılarına sızmasını önleyen maskeleme yardımcıları.

* Anahtar adı hassas görünen (büyük/küçük harf duyarsız) değerler maskelenir:
  - kimlik bilgileri: token, access_token, api_key, apikey, password, passwd, secret, authorization, cookie, ...
  - bağlantı dizeleri: connection_string, dsn, jdbc, datasource_url, ...
  - kişisel veriler (HGS2): kartNo, ogrenciNo / öğrenciNo, parmakIzi, card_number, student_id, fingerprint,
    biyometri, tcKimlikNo, HGS2 terminal parametreleri eskiNo / yeniNo (öğrenci numarası) ve slot / fpSlot
    (parmak izi sensör slotu; adın tamamı eşleşmelidir, ör. `timeslot` maskelenmez), ...
* URL'lerde ve form gövdelerinde yalnızca hassas parametrelerin DEĞERİ değişir; path, diğer
  parametreler ve kodlamaları bayt bayt korunur.
* Yapılandırılmış veride (JSON nesnesi/listesi) maskeleme veri yapısı üzerinden yapılır: hassas
  anahtarın değeri (iç içe nesne ya da liste olsa da) bütünüyle maskelenir; diğer metinler serbest
  metin kurallarından geçer.
* Serbest metinde (hata mesajı, log satırı, stack trace, test raporu) `anahtar=değer`, `"anahtar": değer`,
  `anahtar: değer` kalıpları, `Bearer`/`Basic` kimlik bilgileri, URL'deki kullanıcı bilgisi parolası,
  veritabanı bağlantı URL'leri ve çağıranın bildirdiği bilinen gizli değerler maskelenir.
* Değerler kısmen gösterilmez; maskelenen değerin tamamı `***REDACTED***` olur.
* Desteklenmeyen girdi türünde maskeleme sessizce atlanmaz: `TypeError` fırlatılır ve hata mesajı
  yalnızca türün adını içerir (değeri değil).

Sınır: maskeleme anahtar adına ve bilinen kalıplara dayanır. Masum adlı bir alana ya da anahtarsız serbest
metne yazılmış kişisel değer (ör. yalnızca bir kart numarası) tanınmaz.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import unquote_plus

REDACTED = "***REDACTED***"

SENSITIVE_KEY_RE = re.compile(
    # kimlik bilgileri
    r"(auth|bearer|cookie|token|secret|passw|pwd|api[-_]?key|access[-_]?key|private[-_]?key"
    r"|credential|session|signature|^key$|^sig$"
    # bağlantı dizeleri
    r"|conn(ection)?[-_.]?str|^dsn$|jdbc|data[-_.]?source[-_.]?url|database[-_.]?url"
    # kişisel veriler: kart, öğrenci ve kimlik numaraları, biyometri (HGS2 parametreleri dahil)
    r"|kart[-_.]?(no|num)|card[-_.]?(no|num)"
    r"|[oö][gğ]renci[-_.]?(no|num|id)|student[-_.]?(no|num|id)"
    r"|parmak[-_.]?iz|finger[-_.]?print|biy?ometri"
    # HGS2 terminal parametreleri: eskiNo/yeniNo (öğrenci numarası), slot (parmak izi sensör slotu)
    r"|^(eski|yeni)[-_.]?(no|num(ara)?)$|^(fp[-_.]?)?slot([-_.]?(id|no))?$"
    r"|tc[-_.]?kimlik|^tckn$|kimlik[-_.]?(no|num)|national[-_.]?id|^ssn$)",
    re.IGNORECASE,
)
# Bu uzunluktan kısa "gizli" değerler metinde birebir aranmaz (ör. "1" her yeri maskelerdi).
_MIN_LITERAL_SECRET_LEN = 4

# anahtar=değer: değer tırnaklı olabilir ("..." / '...'); tırnaksızsa ayraçta biter.
_KEY_VALUE_RE = re.compile(
    r"(?P<key>[A-Za-z0-9_.~%+\-À-ɏ]+)=(?P<value>\"[^\"]*\"|'[^']*'|[^&\s#'\"<>)]*)"
)
# "anahtar": değer (JSON/Python repr) ya da noktasız anahtar: değer (log, header satırı). Noktalı ve tırnaksız
# anahtarlar dışarıda bırakılır; Java sınıf adlarını (`a.b.TokenException: mesaj`) ve `Dosya.java:12`
# satır numaralarını maskelememek için.
_KEY_COLON_RE = re.compile(
    r"(?P<q>[\"'])(?P<qkey>[^\"'\s]{1,128})(?P=q)\s*:\s*(?P<qvalue>\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'"
    r"|[^\s,;&}\]\)]+)"
    r"|(?<![\w.\-])(?P<key>[A-Za-z0-9_\-À-ɏ]{1,128}):[ \t]*(?P<value>\"(?:[^\"\\]|\\.)*\""
    r"|'(?:[^'\\]|\\.)*'|[^\s,;&}\]\)]+)"
)
_AUTH_SCHEME_RE = re.compile(r"(?P<scheme>\b[Bb]earer|\bBasic|\bDigest)\s+[A-Za-z0-9._~+/=\-]{4,}")
_USERINFO_PASSWORD_RE = re.compile(r"(?P<prefix>://[^/\s:@]+:)[^@\s/]+@")
_CONNECTION_URL_RE = re.compile(
    r"(?P<prefix>\bjdbc:[A-Za-z0-9]+:|\b(?:postgres(?:ql)?|mysql|mariadb|sqlserver|oracle|mongodb(?:\+srv)?|redis"
    r"|amqps?)://)[^\s'\"<>]+",
    re.IGNORECASE,
)


def _require_text(value: Any, what: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{what} metin olmalı (alınan: {type(value).__name__})")
    return value


def is_sensitive_key(name: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(name))


def _query_pairs(query: str) -> list[tuple[str, str, str]]:
    """(ham anahtar, '=' ya da '', ham değer) üçlüleri; sıra ve kodlama korunur."""
    return [piece.partition("=") for piece in query.split("&")]


def _sanitize_query(query: str) -> str:
    pieces = []
    for key, eq, value in _query_pairs(query):
        if eq and value and is_sensitive_key(unquote_plus(key)):
            value = REDACTED
        pieces.append(f"{key}{eq}{value}")
    return "&".join(pieces)


def sanitize_url(url: str) -> str:
    """Mutlak ya da göreli URL'deki hassas sorgu değerlerini ve kullanıcı bilgisi parolasını maskeler."""
    _require_text(url, "URL")
    url = _USERINFO_PASSWORD_RE.sub(rf"\g<prefix>{REDACTED}@", url)
    base, question, rest = url.partition("?")
    if not question:
        return url
    query, hash_, fragment = rest.partition("#")
    return f"{base}?{_sanitize_query(query)}{hash_}{fragment}"


def sanitize_form(body: str) -> str:
    """`application/x-www-form-urlencoded` gövdesindeki hassas alanların değerlerini maskeler (kodlama korunur)."""
    return _sanitize_query(_require_text(body, "Form gövdesi"))


def sensitive_values(headers: Mapping[str, str], url: str) -> list[str]:
    """Bir istekte geçen, metinlerde birebir maskelenmesi gereken gizli değerler."""
    found: set[str] = set()
    for name, value in headers.items():
        if is_sensitive_key(name):
            found.add(value)
            scheme, space, credential = value.partition(" ")  # "Bearer <değer>" biçimi
            if space:
                found.add(credential)
    _, question, rest = url.partition("?")
    if question:
        for key, eq, value in _query_pairs(rest.partition("#")[0]):
            if eq and value and is_sensitive_key(unquote_plus(key)):
                found.update({value, unquote_plus(value)})
    return sorted((v for v in found if len(v) >= _MIN_LITERAL_SECRET_LEN), key=len, reverse=True)


def _masked_like(value: str) -> str:
    """Değeri maskeler; tırnaklıysa tırnak biçimini korur (JSON benzeri metin geçerli kalır)."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return f"{value[0]}{REDACTED}{value[0]}"
    return REDACTED


def _mask_key_value(match: re.Match[str]) -> str:
    key, value = match.group("key"), match.group("value")
    if value and value not in ('""', "''") and is_sensitive_key(unquote_plus(key)):
        return f"{key}={_masked_like(value)}"
    return match.group(0)


def _mask_key_colon(match: re.Match[str]) -> str:
    if match.group("qkey") is not None:
        key, value, start = match.group("qkey"), match.group("qvalue"), match.start("qvalue")
    else:
        key, value, start = match.group("key"), match.group("value"), match.start("value")
    if not is_sensitive_key(key) or value in ('""', "''"):
        return match.group(0)
    offset = start - match.start()
    return match.group(0)[:offset] + _masked_like(value)


def sanitize_text(text: str, secrets: Iterable[str] = ()) -> str:
    """Serbest metindeki bilinen gizli değerleri, hassas anahtar/değer kalıplarını ve bağlantı bilgilerini maskeler.

    Aynı metne tekrar uygulanması sonucu değiştirmez (idempotent).
    """
    _require_text(text, "Maskelenecek metin")
    for secret in sorted(set(secrets), key=len, reverse=True):
        if len(secret) >= _MIN_LITERAL_SECRET_LEN:
            text = text.replace(secret, REDACTED)
    text = _CONNECTION_URL_RE.sub(rf"\g<prefix>{REDACTED}", text)
    text = _USERINFO_PASSWORD_RE.sub(rf"\g<prefix>{REDACTED}@", text)
    text = _AUTH_SCHEME_RE.sub(rf"\g<scheme> {REDACTED}", text)
    text = _KEY_VALUE_RE.sub(_mask_key_value, text)
    return _KEY_COLON_RE.sub(_mask_key_colon, text)


def sanitize_data(value: Any) -> Any:
    """JSON uyumlu veriyi (sözlük, liste, metin, sayı, bool, None) yapısı üzerinden maskeler; kopya döndürür.

    Hassas anahtarın değeri, iç içe nesne veya liste olsa da bütünüyle `***REDACTED***` olur; diğer metinler
    `sanitize_text` kurallarından geçer. Desteklenmeyen türlerde `TypeError` (değer mesaja yazılmaz).
    """
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"Sözlük anahtarı metin olmalı (alınan: {type(key).__name__})")
            out[key] = REDACTED if is_sensitive_key(key) and item not in (None, "") else sanitize_data(item)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize_data(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise TypeError(f"Maskelenemeyen veri türü: {type(value).__name__}")


def sanitize_json_text(text: str) -> str:
    """JSON metnini veri yapısı üzerinden maskeler; geçerli JSON değilse serbest metin kurallarına düşer.

    Geçerli JSON için çıktı yeniden serileştirilmiş JSON'dur (anahtar sırası korunur, boşluklar normalleşir).
    """
    _require_text(text, "JSON metni")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        return sanitize_text(text)
    return json.dumps(sanitize_data(data), ensure_ascii=False)
