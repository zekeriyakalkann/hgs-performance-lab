"""Kanıta dayalı kural tabanlı test sonucu sınıflandırıcısı (`rules-v3`; ağ yok, model yok).

rules-v2: yalnızca durum kodu (ya da yalnızca "yanıt alınır") beklentisi 2xx bir yanıtla karşılandığında, yanıt
ayrıştırıcısı gövdeden tanınan bir iş sonucu çıkaramadıysa (`UNRECOGNIZED_BODY_RULES`) karar PASS değil INCONCLUSIVE'dir
(`H-STATUS-OK-UNKNOWN-BODY`).

rules-v3 (N12, rules-v2'ye göre fark): aynı koşulda (2xx + iş sonucu beklentisi yok) gövde hakkında güvenilir kanıt
yoksa ya da gövde yalnızca bir ara durum bildiriyorsa da karar INCONCLUSIVE'dir:
* `H-STATUS-OK-EMPTY-BODY`: gövde boş; durum kodu gövdesiz yanıt tanımlamıyor (204/205 dışında);
* `H-STATUS-OK-BODY-NOT-PARSED`: gövde ayrıştırılmadı (`R-TOO-LARGE`, `R-BODY-NOT-CAPTURED`);
* `H-STATUS-OK-BODY-UNVERIFIED`: Lab kaydında ayrıştırma özeti yok (eksik/bozuk metadata ya da eski dosya); sonuç
  dosyasında bir iş sonucu yazılı olsa bile gövdenin incelendiği kanıtlanamaz;
* `H-STATUS-OK-STATE-BODY`: gövde bir ara durum (`STATE_BUSINESS_OUTCOMES`: WAITING, READY, NONE, SCAN_*); bunlar
  iş başarısı ya da kimlik doğrulama onayı değildir.
204/205 + boş gövde, beklenen 3xx/4xx/5xx ve iş sonucu beklentisi tanımlı kayıtlarda davranış değişmedi.

Her kayıt için bir `Classification` üretir: sınıf, uygulanan kural kimlikleri, gerekçe, yapılandırılmış kanıtlar
(maskeli alan değerleri), güven düzeyi, inceleme gereksinimi, uyarılar ve sınırlamalar. Kaynak test sonucu
(`TestRecord.test_outcome`) değiştirilmez; analiz ayrı alana (`analysis`) yazılır.

Sınıflar:

* PASS — kaynak geçti (JUnit) ya da gözlenen sonuç açıkça tanımlı beklentiyi karşıladı (HTTP).
* APPLICATION_FAILURE — beklenti açıkça tanımlıyken gözlenen yanıt (durum kodu ve/veya iş sonucu) uymadı, ya da
  JUnit assertion başarısızlığı.
* TRANSPORT_FAILURE — bağlantı/taşıma hatası kaydedildi. Uygulama hatası olduğu kanıtlanmış sayılmaz.
* TIMEOUT — zaman aşımı kaydedildi. Kök neden (uygulama, veritabanı, ağ, test ortamı) belirlenmez.
* TEST_INFRASTRUCTURE_FAILURE — test bağlamı/ortamı başlatılamadı (bağımlılık enjeksiyonu, sınıf yolu, test
  veritabanı bağlantısı vb.); uygulamanın yapılandırma hatası da olabileceği için inceleme ister.
* INVALID_TEST_DATA — kayıt geçersiz işaretlenmiş (veri kalitesi `invalid`).
* INCONCLUSIVE — kanıt yetersiz veya çelişkili; daha fazla bilgiyle (ör. beklenen sonuç, yanıt gövdesi) karar
  verilebilir. Örnekler: beklenen sonuç bilinmiyor, test çalıştırılmadı (skipped), kaynak içinde çelişki.
* UNKNOWN — sistemin bu kayıt türü için kuralı yok (ör. tanınmayan istisna türüyle JUnit error, kaynağın
  bilinmeyen sonucu).

Güven düzeyi (`confidence`) istatistiksel olarak kalibre edilmiş bir olasılık DEĞİLDİR; kararın dayandığı kanıtın
türünü özetleyen sıralı bir etikettir:

* high   — doğrudan ve çelişkisiz kanıta dayanan deterministik kural (ör. açık beklentiyle uyuşmayan durum kodu,
           kaydedilmiş zaman aşımı, JUnit'in kendi PASS kararı).
* medium — karar kısmi bir denetime ya da yoruma dayanır (ör. yalnızca durum kodu denetlendi; assertion
           başarısızlığının uygulamaya atfedilmesi; tanınan istisna türünden altyapı/taşıma çıkarımı).
* low    — yalnızca hata mesajındaki metin kalıbına dayanır.
* None   — INCONCLUSIVE ve UNKNOWN: kesin karar yok.

Kurallar gerçek HGS2 hata örnekleriyle doğrulanmadı (bugün gerçek HGS2'den yalnızca bir başarılı JUnit testi var);
"high" ölçülmüş doğruluk anlamına gelmez.

F5 (Robust Z-score) ile ilişki: bu sınıflandırıcı gecikme anomalisini değerlendirmez ve F5 çıktısını girdi
olarak kullanmaz. Yavaş bir yanıt işlevsel olarak PASS olabilir; HTTP 200 ile dönen bir iş mantığı hatası
gecikme anomalisi olmadan görülebilir. İki sonuç ayrı eksenlerdir.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from .junit_report import JUnitReport, JUnitReportError
from .models import ERROR_TIMEOUT, ERROR_TYPES
from .records import (
    CLASS_APPLICATION_FAILURE,
    CLASS_INCONCLUSIVE,
    CLASS_INVALID_TEST_DATA,
    CLASS_PASS,
    CLASS_TEST_INFRASTRUCTURE_FAILURE,
    CLASS_TIMEOUT,
    CLASS_TRANSPORT_FAILURE,
    CLASS_UNKNOWN,
    CLASSES,
    DATASET_FIXTURE,
    DATASET_REAL,
    DATASET_SYNTHETIC,
    DATASET_UNKNOWN,
    EXPECTATION_SOURCE_REGISTRY,
    SCOPE_REAL,
    SCOPE_SYNTHETIC,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_SKIPPED,
    QUALITY_CONTRADICTORY,
    QUALITY_INVALID,
    RECORD_SCHEMA_VERSION,
    SOURCE_JUNIT_XML,
    SOURCE_LAB_RESULT,
    Classification,
    Evidence,
    TestRecord,
)
from .response_parser import RECOGNIZED_BUSINESS_OUTCOMES, UNRECOGNIZED_BODY_RULES

CLASSIFIER_VERSION = "rules-v3"
_RESPONSE_RULE_PREFIX = "response_rule:"  # records.record_from_raw_result'ın ayrıştırma kuralı uyarısı
DOCUMENT_FORMAT = "hgs2-lab-test-classification"
DOCUMENT_SCHEMA_VERSION = 1

# HGS2'nin düz metin iş sonuçları (AuthController / TerminalEnrollmentController, HTTP 200 ile döner). Tek kaynak:
# yanıt ayrıştırıcısının izin listesi.
KNOWN_BUSINESS_OUTCOMES = RECOGNIZED_BUSINESS_OUTCOMES
NEGATIVE_BUSINESS_OUTCOMES = frozenset({"REDDEDILDI", "HATA"})
# Ara durumlar (HGS2 sensör uçları): ne iş başarısı ne hata. Yalnızca açık iş sonucu beklentisiyle PASS olabilir.
STATE_BUSINESS_OUTCOMES = frozenset({"WAITING", "READY", "NONE", "SCAN_CARD", "SCAN_FP", "SCAN_SCHOOL_NO"})
# HTTP anlamı gereği gövde taşımayan başarılı yanıtlar (ör. HGS2 `DELETE /api/sensor/session` → 204).
BODYLESS_SUCCESS_STATUSES = frozenset({204, 205})
_NOT_PARSED_BODY_RULES = frozenset({"R-TOO-LARGE", "R-BODY-NOT-CAPTURED"})
GATEWAY_STATUSES = frozenset({502, 503, 504})

# İstisna türleri basit sınıf adıyla eşleştirilir (paket ve iç sınıf öneki atılır).
TIMEOUT_EXCEPTIONS = frozenset({
    "TimeoutException", "SocketTimeoutException", "HttpTimeoutException", "HttpConnectTimeoutException",
    "ConnectTimeoutException", "ReadTimeoutException", "QueryTimeoutException", "ConditionTimeoutException",
    "ReadTimeout", "ConnectTimeout",
})
TRANSPORT_EXCEPTIONS = frozenset({
    "ConnectException", "UnknownHostException", "NoRouteToHostException", "SocketException",
    "ResourceAccessException", "HttpHostConnectException", "SSLHandshakeException", "ConnectionError",
})
INFRASTRUCTURE_EXCEPTIONS = frozenset({
    "BeanCreationException", "UnsatisfiedDependencyException", "ApplicationContextException",
    "NoSuchBeanDefinitionException", "BeanDefinitionStoreException", "CannotGetJdbcConnectionException",
    "PoolInitializationException", "CannotCreateTransactionException", "DataAccessResourceFailureException",
    "JDBCConnectionException", "NoClassDefFoundError", "ClassNotFoundException", "NoSuchMethodError",
    "ExceptionInInitializerError", "ParameterResolutionException", "ExtensionConfigurationException",
    "PreconditionViolationException", "OutOfMemoryError",
})
ASSERTION_EXCEPTIONS = frozenset({
    "AssertionError", "AssertionFailedError", "ComparisonFailure", "MultipleFailuresError", "AssertionFailure",
})
_CONTEXT_LOAD_RE = re.compile(r"Failed to load ApplicationContext|ApplicationContext failure threshold", re.I)
_TIMEOUT_MESSAGE_RE = re.compile(r"\btimed out\b|\btimeout (?:expired|exceeded)\b|execution exceeded timeout", re.I)
_CAUSED_BY_RE = re.compile(r"^\s*Caused by:\s*(?P<type>[A-Za-z_$][\w$.]*)", re.M)

_LIMIT_TIMEOUT = ("Zaman aşımının kök nedeni (uygulama, veritabanı, ağ veya test ortamı) kayıttan belirlenemez; "
                  "veritabanı veya ağ yavaşlığı yalnızca ölçülmedikçe hipotezdir.")
_LIMIT_TRANSPORT = "Taşıma hatası tek başına uygulamanın hatalı olduğunu kanıtlamaz."
_LIMIT_ASSERTION = ("Assertion başarısızlığı uygulamanın testin beklentisini karşılamadığını gösterir; testin "
                    "kendisinin veya test verisinin hatalı olması dışlanamaz.")
_LIMIT_INFRA = ("Bağlam/ortam başlatma hatası test altyapısından da uygulamanın yapılandırma hatasından da "
                "kaynaklanabilir.")
_LIMIT_STATUS_ONLY = "Yalnızca HTTP durum kodu doğrulandı; HTTP 200 iş mantığı başarısını tek başına kanıtlamaz."


def _simple_name(type_name: str) -> str:
    return re.split(r"[.$]", type_name.strip())[-1]


def _cause_chain(record: TestRecord) -> list[str]:
    """Üst istisna + iz metnindeki `Caused by:` türleri (basit adlarıyla, sırasıyla)."""
    chain = [_simple_name(record.exception_type)] if record.exception_type else []
    if record.stack_trace:
        chain += [_simple_name(m.group("type")) for m in _CAUSED_BY_RE.finditer(record.stack_trace)]
    return chain


def _norm_outcome(value: str) -> str:
    return value.strip().upper()


def _response_rule(record: TestRecord) -> str | None:
    """Kayda eklenmiş yanıt ayrıştırma kuralı (ör. R-TEXT-UNRECOGNIZED); ayrıştırma özeti yoksa None."""
    for warning in record.warnings:
        if warning.startswith(_RESPONSE_RULE_PREFIX):
            return warning[len(_RESPONSE_RULE_PREFIX):]
    return None


def _status_ok_body_gap(record: TestRecord) -> tuple[str, str, str] | None:
    """2xx + iş sonucu beklentisi yokken gövdenin işlevsel anlamı bilinmiyorsa (kural, gerekçe, uyarı); yoksa None.

    Yalnızca durum kodu (ya da yalnızca "yanıt alınır") beklentisi karşılandığında çağrılır; olumsuz iş sonucu daha
    önce H-STATUS-OK-NEGATIVE-BODY ile ele alınır.
    """
    rule = _response_rule(record)
    if rule is None and record.source_type == SOURCE_LAB_RESULT \
            and record.status_code not in BODYLESS_SUCCESS_STATUSES:
        return ("H-STATUS-OK-BODY-UNVERIFIED",
                "Durum kodu beklentisi karşılandı, ancak kayıtta yanıt ayrıştırma özeti yok (eksik/bozuk metadata ya "
                "da eski sonuç dosyası); gövdenin incelendiğine dair kanıt yok.", "response_parsing_not_available")
    outcome = _norm_outcome(record.business_outcome) if record.business_outcome else None
    if outcome in STATE_BUSINESS_OUTCOMES:
        return ("H-STATUS-OK-STATE-BODY",
                f"Durum kodu beklentisi karşılandı, ancak yanıt gövdesi bir ara durum bildiriyor ({outcome}); bu, iş "
                "başarısı veya kimlik doğrulama onayı değildir ve iş sonucu için beklenti tanımlı değil.",
                "business_outcome_state_only")
    if outcome is not None:
        return None
    if rule in UNRECOGNIZED_BODY_RULES:
        return ("H-STATUS-OK-UNKNOWN-BODY",
                "Durum kodu beklentisi karşılandı, ancak yanıt gövdesinden tanınan bir iş sonucu çıkarılamadı "
                f"({rule}); yanıtın işlevsel anlamı bilinmiyor.", "business_outcome_unrecognized")
    if rule == "R-EMPTY-BODY" and record.status_code not in BODYLESS_SUCCESS_STATUSES:
        return ("H-STATUS-OK-EMPTY-BODY",
                f"Durum kodu beklentisi karşılandı, ancak gövde boş ve HTTP {record.status_code} gövdesiz yanıt "
                "tanımlamıyor (yalnızca 204/205); yanıtın işlevsel anlamı bilinmiyor.", "response_body_empty")
    if rule in _NOT_PARSED_BODY_RULES:
        return ("H-STATUS-OK-BODY-NOT-PARSED",
                f"Durum kodu beklentisi karşılandı, ancak yanıt gövdesi ayrıştırılmadı ({rule}); yanıtın işlevsel "
                "anlamı bilinmiyor.", "response_body_not_parsed")
    return None


def _result(classification: str, rule: str, reason: str, evidence: Sequence[Evidence], *,
            confidence: str | None, review: bool = False, warnings: Sequence[str] = (),
            limitations: Sequence[str] = ()) -> Classification:
    return Classification(classification=classification, rule_ids=(rule,), reason=reason, evidence=tuple(evidence),
                          confidence=confidence, requires_review=review, warnings=tuple(warnings),
                          limitations=tuple(limitations), classifier_version=CLASSIFIER_VERSION)


def _ev(record: TestRecord, *names: str) -> list[Evidence]:
    """Kayıtta gerçekten dolu olan alanların kanıtları (boş alan kanıt sayılmaz)."""
    out = []
    for name in names:
        value = getattr(record, name)
        if value is None or value == ():
            continue
        if name == "expected_result":
            out.append(Evidence("expected_result", value.to_dict()))
        elif isinstance(value, tuple):
            out.append(Evidence(name, list(value)))
        else:
            out.append(Evidence(name, value))
    return out


# --- veri kalitesi ---
def _quality_rule(record: TestRecord) -> Classification | None:
    if record.data_quality_status == QUALITY_INVALID:
        return _result(CLASS_INVALID_TEST_DATA, "DQ-INVALID", "Kayıt veri kalitesi denetiminde geçersiz işaretlendi.",
                       _ev(record, "data_quality_status", "warnings"), confidence="high", review=True)
    if record.data_quality_status == QUALITY_CONTRADICTORY:
        return _result(CLASS_INCONCLUSIVE, "DQ-CONTRADICTORY",
                       "Kaynak kayıt kendi içinde çelişkili; tek bir sonuç seçilmedi.",
                       _ev(record, "data_quality_status", "test_outcome", "warnings"), confidence=None, review=True)
    return None


# --- JUnit / Surefire ---
def _classify_junit(record: TestRecord) -> Classification:
    base = _ev(record, "test_outcome", "exception_type", "error_message")
    outcome = record.test_outcome
    if outcome == OUTCOME_PASS:
        return _result(CLASS_PASS, "J-PASS", "Test çerçevesi testi başarılı raporladı.", _ev(record, "test_outcome"),
                       confidence="high", warnings=[w for w in record.warnings if w.startswith("flaky")],
                       limitations=["Kaynak rapor bu testi başarılı bildiriyor; testin neyi doğruladığı rapordan bilinmez ve "
                                    "uygulamanın genel olarak hatasız olduğunu göstermez."])
    if outcome == OUTCOME_SKIPPED:
        return _result(CLASS_INCONCLUSIVE, "J-SKIPPED", "Test çalıştırılmadı (skipped); başarılı sayılmaz.",
                       _ev(record, "test_outcome", "error_message"), confidence=None, warnings=["test_not_executed"])
    if outcome not in (OUTCOME_FAIL, OUTCOME_ERROR):
        return _result(CLASS_UNKNOWN, "J-UNKNOWN-OUTCOME", "Kaynak test sonucu bilinmiyor; bu durum için kural yok.",
                       base, confidence=None, review=True)

    chain = _cause_chain(record)
    message = record.error_message or ""
    chain_evidence = [Evidence("exception_chain", chain, source="rule")] if len(chain) > 1 else []
    infra = [t for t in chain if t in INFRASTRUCTURE_EXCEPTIONS]
    if infra or _CONTEXT_LOAD_RE.search(message) or _CONTEXT_LOAD_RE.search(record.stack_trace or ""):
        note = f"tanınan altyapı istisnası: {infra[0]}" if infra else "bağlam yükleme hatası mesajı"
        return _result(CLASS_TEST_INFRASTRUCTURE_FAILURE, "J-INFRA",
                       "Test bağlamı veya ortamı başlatılamadı.",
                       base + chain_evidence + [Evidence("matched", note, source="rule")],
                       confidence="medium", review=True, limitations=[_LIMIT_INFRA])
    timeout = [t for t in chain if t in TIMEOUT_EXCEPTIONS]
    if timeout:
        return _result(CLASS_TIMEOUT, "J-TIMEOUT-TYPE", "Zaman aşımı istisnası kaydedildi.",
                       base + chain_evidence + [Evidence("matched", timeout[0], source="rule")],
                       confidence="high", limitations=[_LIMIT_TIMEOUT])
    if _TIMEOUT_MESSAGE_RE.search(message):
        return _result(CLASS_TIMEOUT, "J-TIMEOUT-MESSAGE", "Hata mesajı zaman aşımını bildiriyor.",
                       base + [Evidence("matched", "zaman aşımı metin kalıbı", source="rule")],
                       confidence="low", review=True, limitations=[_LIMIT_TIMEOUT])
    transport = [t for t in chain if t in TRANSPORT_EXCEPTIONS]
    if transport:
        return _result(CLASS_TRANSPORT_FAILURE, "J-TRANSPORT", "Bağlantı/taşıma istisnası kaydedildi.",
                       base + chain_evidence + [Evidence("matched", transport[0], source="rule")],
                       confidence="medium", review=True, limitations=[_LIMIT_TRANSPORT])
    top = chain[0] if chain else None
    if outcome == OUTCOME_FAIL or top in ASSERTION_EXCEPTIONS:
        return _result(CLASS_APPLICATION_FAILURE, "J-ASSERTION",
                       "Test beklentisi karşılanmadı (assertion başarısızlığı).", base, confidence="medium",
                       limitations=[_LIMIT_ASSERTION])
    if top is None:
        return _result(CLASS_INCONCLUSIVE, "J-ERROR-NO-TYPE",
                       "Test hata verdi ancak istisna türü kayıtta yok; sınıf belirlenemedi.", base, confidence=None,
                       review=True)
    return _result(CLASS_UNKNOWN, "J-ERROR-UNRECOGNIZED",
                   "Test beklenmeyen bir istisnayla hata verdi; bu istisna türü için kural yok.",
                   base + chain_evidence, confidence=None, review=True)


# --- HTTP / iş sonucu ---
def _classify_http_core(record: TestRecord) -> Classification:
    """Gözlem ile beklenen davranışın karşılaştırması (beklentinin kaynağından ve doğrulama durumundan bağımsız)."""
    if record.transport_error is not None and record.status_code is not None:
        return _result(CLASS_INCONCLUSIVE, "H-CONFLICT-TRANSPORT-STATUS",
                       "Hem taşıma hatası hem HTTP durum kodu kayıtlı; gözlem çelişkili.",
                       _ev(record, "transport_error", "status_code"), confidence=None, review=True)
    if record.transport_error == ERROR_TIMEOUT:
        return _result(CLASS_TIMEOUT, "H-TIMEOUT", "İstemci zaman aşımı kaydedildi; HTTP yanıtı alınamadı.",
                       _ev(record, "transport_error", "error_message"), confidence="high",
                       limitations=[_LIMIT_TIMEOUT])
    if record.transport_error is not None:
        return _result(CLASS_TRANSPORT_FAILURE, "H-TRANSPORT", "Taşıma hatası kaydedildi; HTTP yanıtı alınamadı.",
                       _ev(record, "transport_error", "error_message"), confidence="high",
                       limitations=[_LIMIT_TRANSPORT])
    if record.status_code is None:
        return _result(CLASS_INCONCLUSIVE, "H-NO-OBSERVATION", "Kayıtta ne HTTP yanıtı ne taşıma hatası var.",
                       _ev(record, "test_outcome", "business_outcome"), confidence=None, review=True)

    observed = _ev(record, "status_code", "business_outcome")
    parsing = [w for w in record.warnings if w.startswith("response_")]
    if parsing:  # yanıt ayrıştırıcısının kuralı ve uyarıları (gövde içeriği değil)
        observed.append(Evidence("response_parsing", parsing))
    expected = record.expected_result
    if expected is None or not expected.is_defined:
        warnings = ["expected_result_unknown"]
        if record.status_code >= 500:
            warnings.append("server_error_status_observed")
        if record.business_outcome and _norm_outcome(record.business_outcome) in NEGATIVE_BUSINESS_OUTCOMES:
            warnings.append("negative_business_outcome_observed")
        return _result(CLASS_INCONCLUSIVE, "H-NO-EXPECTATION",
                       "Beklenen sonuç bilinmiyor; gözlenen yanıt kesin PASS ya da hata olarak yorumlanmadı.",
                       observed, confidence=None, review=True, warnings=warnings)

    evidence = observed + _ev(record, "expected_result")
    mismatches: list[Evidence] = []
    if expected.expected_transport in ERROR_TYPES:  # taşıma hatası bekleniyordu, ama HTTP yanıtı alındı
        mismatches.append(Evidence("transport", "response", source="rule",
                                   note=f"beklenen {expected.expected_transport}"))
    status_checked = bool(expected.status_codes)
    if status_checked and record.status_code not in expected.status_codes:
        mismatches.append(Evidence("status_code", record.status_code, source="rule",
                                   note=f"beklenen {list(expected.status_codes)}"))
    business_checked = bool(expected.business_outcomes)
    unknown_token = False
    if business_checked:
        if record.business_outcome is None:
            return _result(CLASS_INCONCLUSIVE, "H-BUSINESS-MISSING",
                           "İş sonucu bekleniyor ama yanıt gövdesinden iş sonucu kayıtta yok.", evidence,
                           confidence=None, review=True, warnings=["business_outcome_missing"])
        wanted = {_norm_outcome(v) for v in expected.business_outcomes}
        got = _norm_outcome(record.business_outcome)
        if got not in wanted:
            unknown_token = got not in KNOWN_BUSINESS_OUTCOMES
            mismatches.append(Evidence("business_outcome", record.business_outcome, source="rule",
                                       note=f"beklenen {sorted(wanted)}"))

    if mismatches:
        rule = {"status_code": "H-STATUS-MISMATCH", "business_outcome": "H-BUSINESS-MISMATCH",
                "transport": "H-TRANSPORT-MISMATCH"}[mismatches[0].field]
        if len(mismatches) == 2:
            rule = "H-STATUS-AND-BUSINESS-MISMATCH"
        warnings, limitations, review, confidence = [], [], False, "high"
        if unknown_token:
            warnings.append("unrecognized_business_outcome")
            review, confidence = True, "medium"
        if record.status_code in GATEWAY_STATUSES:
            warnings.append("gateway_status")
            limitations.append("502/503/504 bir ağ geçidi veya altyapı bileşeninden de dönebilir.")
            review = True
        if record.test_outcome == OUTCOME_PASS:
            warnings.append("source_outcome_differs")
        return _result(CLASS_APPLICATION_FAILURE, rule, "Gözlenen yanıt açıkça tanımlı beklentiyi karşılamadı.",
                       evidence + mismatches, confidence=confidence, review=review, warnings=warnings,
                       limitations=limitations)

    # Beklenti karşılandı. Kaynak FAIL/ERROR diyorsa PASS'a çevrilmez.
    if record.test_outcome in (OUTCOME_FAIL, OUTCOME_ERROR):
        return _result(CLASS_INCONCLUSIVE, "H-CONFLICT-SOURCE-OUTCOME",
                       "Gözlenen yanıt beklentiyle uyumlu, ancak kaynak testi başarısız raporladı.",
                       evidence + _ev(record, "test_outcome"), confidence=None, review=True)
    if business_checked:
        return _result(CLASS_PASS, "H-EXPECTED-MATCH",
                       "Gözlenen durum kodu ve iş sonucu beklentiyle uyumlu." if status_checked
                       else "Gözlenen iş sonucu beklentiyle uyumlu.", evidence, confidence="high")
    if record.business_outcome and _norm_outcome(record.business_outcome) in NEGATIVE_BUSINESS_OUTCOMES:
        return _result(CLASS_INCONCLUSIVE, "H-STATUS-OK-NEGATIVE-BODY",
                       "Durum kodu beklenen ama yanıt gövdesi olumsuz bir iş sonucu bildiriyor; iş sonucu için "
                       "beklenti tanımlı değil.", evidence, confidence=None, review=True,
                       warnings=["business_expectation_missing"])
    # 2xx + gövdeden doğrulanmış iş sonucu yok: durum kodu tuttu diye sessizce PASS sayılmaz (rules-v3). Beklenen
    # 3xx/4xx/5xx'te kanıt durum kodudur.
    gap = _status_ok_body_gap(record) if 200 <= record.status_code < 300 else None
    if gap is not None:
        rule, reason, code = gap
        return _result(CLASS_INCONCLUSIVE, rule, reason, evidence, confidence=None, review=True,
                       warnings=[code, "business_expectation_missing"], limitations=[_LIMIT_STATUS_ONLY])
    if not status_checked:  # yalnızca "yanıt alınır" bekleniyordu
        return _result(CLASS_PASS, "H-TRANSPORT-MATCH",
                       "Testin tanımlı beklentisi (yalnızca HTTP yanıtı alınması) karşılandı; durum kodu ve iş sonucu "
                       "doğrulanmadı.", evidence, confidence="medium", warnings=["business_outcome_not_checked"],
                       limitations=[_LIMIT_STATUS_ONLY])
    return _result(CLASS_PASS, "H-STATUS-MATCH",
                   "Testin tanımlı beklentisi (yalnızca durum kodu) karşılandı; iş sonucu doğrulanmadı.", evidence,
                   confidence="medium", warnings=["business_outcome_not_checked"], limitations=[_LIMIT_STATUS_ONLY])


_DECISIVE_CLASSES = (CLASS_PASS, CLASS_APPLICATION_FAILURE)
_SCOPE_DATASETS = {SCOPE_REAL: {DATASET_REAL}, SCOPE_SYNTHETIC: {DATASET_SYNTHETIC, DATASET_FIXTURE}}
_MATCH_WARNINGS = ("expectation_not_found", "expectation_conflict", "expectation_deprecated_only",
                   "expectation_no_scenario_id")
_LIMIT_UNVERIFIED = ("Beklenti doğrulanmış değil veya kapsamı bu kayıtla eşleşmiyor; beklenen ile gözlenen arasındaki "
                     "karşılaştırma yalnızca bilgi olarak verildi (`comparison`), kesin teşhis olarak kullanılmadı.")


def _classify_http(record: TestRecord) -> Classification:
    """HTTP kararı + beklenti sözleşmesi (N7): kaynak, doğrulama durumu ve kapsam kararın kesinliğini belirler.

    * Birden fazla etkin beklenti (`expectation_conflict`) → INCONCLUSIVE (E-EXPECTATION-CONFLICT); hiçbiri seçilmez.
    * Sözleşme beklentisi DRAFT/REVIEWED ise PASS/APPLICATION_FAILURE kararı INCONCLUSIVE'e çevrilir
      (E-UNVERIFIED-EXPECTATION); karşılaştırmanın sonucu `comparison` kanıtında kalır.
    * VERIFIED beklentinin kapsamı kaydın veri türüyle eşleşmezse (gerçek ↔ sentetik/fikstür) ya da veri türü
      bilinmiyorsa aynı şekilde kesin karar verilmez (E-SCOPE-MISMATCH / E-SCOPE-UNCONFIRMED).
    * Eski biçim ve senaryo expected_status beklentileri doğrulama durumu taşımaz; karar önceki gibi verilir ve
      `expectation_verification_unspecified` uyarısı eklenir.
    Zaman aşımı ve taşıma hataları gözlemdir; beklentiden bağımsız olarak TIMEOUT / TRANSPORT_FAILURE kalır.
    """
    match_warnings = [w for w in record.warnings if w in _MATCH_WARNINGS]
    if "expectation_conflict" in match_warnings and record.transport_error is None and record.status_code is not None:
        return _result(CLASS_INCONCLUSIVE, "E-EXPECTATION-CONFLICT",
                       "Bu senaryo için birden fazla etkin beklenti var; hiçbiri seçilmedi.",
                       _ev(record, "scenario_id", "status_code", "business_outcome"), confidence=None, review=True,
                       warnings=["expectation_conflict"])
    base = _classify_http_core(record)
    expected = record.expected_result
    provenance = expected.provenance if expected is not None else None
    evidence, warnings, limitations = [], [*base.warnings, *match_warnings], list(base.limitations)
    if provenance is not None:
        evidence.append(Evidence("expectation", provenance.to_dict()))
    if expected is not None and expected.expected_test_outcome and expected.expected_test_outcome != record.test_outcome:
        warnings.append("test_outcome_differs_from_expectation")  # yalnızca kanıt; kaynak sonucu değişmez
        evidence.append(Evidence("test_outcome", record.test_outcome, source="rule",
                                 note=f"beklenen {expected.expected_test_outcome}"))
    if expected is not None and record.transport_error is not None:
        # Durum kodu veya iş sonucu beklentisi, bir HTTP yanıtı alınacağını ima eder.
        wanted = expected.expected_transport or ("response" if expected.status_codes or expected.business_outcomes
                                                 else None)
        if wanted is not None:
            warnings.append("transport_matches_expectation" if wanted == record.transport_error
                            else "transport_differs_from_expectation")
    gate: tuple[str, str, str] | None = None
    if provenance is not None and provenance.source == EXPECTATION_SOURCE_REGISTRY:
        if provenance.evidence_issues:
            warnings.append("expectation_evidence_issues")
        if not provenance.is_verified:
            gate = ("E-UNVERIFIED-EXPECTATION", f"Beklenti doğrulanmamış ({provenance.verification_status}); "
                    "karşılaştırma sonucu kesin teşhis olarak kullanılmadı.", "expectation_unverified")
        elif record.dataset_kind not in _SCOPE_DATASETS[provenance.scope]:
            rule = "E-SCOPE-UNCONFIRMED" if record.dataset_kind == DATASET_UNKNOWN else "E-SCOPE-MISMATCH"
            gate = (rule, f"Beklenti '{provenance.scope}' kapsamında doğrulandı; kaydın veri türü "
                    f"({record.dataset_kind}) bu kapsamla eşleşmiyor veya doğrulanamıyor.",
                    "expectation_scope_mismatch")
        else:
            limitations.append(f"Beklenti yalnızca '{provenance.scope}' kapsamında ve kayıtlı kanıtlarla doğrulandı; "
                               "bu kapsamın dışındaki davranışlar için genelleme yapılmaz.")
    elif provenance is not None:
        warnings.append("expectation_verification_unspecified")
    if gate is not None and base.classification in _DECISIVE_CLASSES:
        rule, reason, code = gate
        comparison = Evidence("comparison", {"would_be": base.classification, "rule": base.rule_ids[0]}, source="rule")
        return Classification(
            classification=CLASS_INCONCLUSIVE, rule_ids=(rule, *base.rule_ids), reason=reason,
            evidence=(*base.evidence, *evidence, comparison), confidence=None, requires_review=True,
            warnings=tuple(dict.fromkeys([*warnings, code])), limitations=(*limitations, _LIMIT_UNVERIFIED),
            classifier_version=CLASSIFIER_VERSION)
    if gate is not None:
        warnings.append(gate[2])
    return dataclasses.replace(base, evidence=(*base.evidence, *evidence), warnings=tuple(dict.fromkeys(warnings)),
                               limitations=tuple(limitations))


_LIMIT_JUNIT_EXPECTATION = ("JUnit kararı kaynak test sonucuna dayanır; beklenti sözleşmesi bu kararı değiştirmez, "
                            "yalnızca kanıt olarak eklenir.")
_LIMIT_NOT_OBSERVABLE = ("JUnit kaydı HTTP durum kodu, iş sonucu veya taşıma bilgisi içermez; beklentinin bu alanları "
                         "karşılaştırılamadı.")


def _classify_junit_with_expectation(record: TestRecord) -> Classification:
    """JUnit kararı (J-* kuralları) + beklenti sözleşmesi bilgisi (N8).

    Karar her zaman kaynak test sonucundan gelir; beklenti onu değiştirmez (kaynak FAIL PASS olmaz, SKIPPED başarı
    sayılmaz). Beklenti eşleşmişse `expectation` (kaynak, sürüm, doğrulama durumu) ve `expectation_comparison`
    (alan bazında: match | differs | not_observable | not_specified) kanıtları eklenir. Doğrulanmamış beklenti,
    kapsam uyuşmazlığı ve çelişkili eşleşme uyarıyla işaretlenir; çelişkili eşleşme incelemeye düşer.
    """
    base = _classify_junit(record)
    match_warnings = [w for w in record.warnings if w in _MATCH_WARNINGS]
    expected = record.expected_result
    if expected is None and not match_warnings:
        return base
    # Senaryo kimliği özelliği geçersiz veya çelişkiliyse eşleştirme yapılamadı: neden kararda da görünür.
    scenario_issues = [w for w in record.warnings if w in ("scenario_id_invalid", "scenario_id_conflict")]
    warnings = [*base.warnings, *match_warnings, *scenario_issues]
    limitations, evidence = list(base.limitations), []
    review = base.requires_review or "expectation_conflict" in match_warnings or bool(scenario_issues)
    if expected is not None:
        provenance = expected.provenance
        if provenance is not None:
            evidence.append(Evidence("expectation", provenance.to_dict()))
        if expected.expected_test_outcome is None:
            outcome_cmp = "not_specified"
        elif expected.expected_test_outcome == record.test_outcome:
            outcome_cmp = "match"
            warnings.append("test_outcome_matches_expectation")
        else:
            outcome_cmp = "differs"
            warnings.append("test_outcome_differs_from_expectation")
        comparison = {
            "test_outcome": outcome_cmp,
            "http_status": "not_observable" if expected.status_codes else "not_specified",
            "business_outcome": "not_observable" if expected.business_outcomes else "not_specified",
            "transport": "not_observable" if expected.expected_transport else "not_specified",
        }
        evidence.append(Evidence("expectation_comparison", comparison, source="rule",
                                 note=f"kaynak {record.test_outcome}, beklenen "
                                      f"{expected.expected_test_outcome or 'belirtilmemiş'}"))
        if "not_observable" in comparison.values():
            warnings.append("expectation_not_observable_in_junit")
            limitations.append(_LIMIT_NOT_OBSERVABLE)
        if provenance is not None and provenance.source == EXPECTATION_SOURCE_REGISTRY:
            if provenance.evidence_issues:
                warnings.append("expectation_evidence_issues")
            if not provenance.is_verified:
                warnings.append("expectation_unverified")
            elif record.dataset_kind not in _SCOPE_DATASETS[provenance.scope]:
                warnings.append("expectation_scope_mismatch")
        elif provenance is not None:
            warnings.append("expectation_verification_unspecified")
        limitations.append(_LIMIT_JUNIT_EXPECTATION)
    return dataclasses.replace(base, evidence=(*base.evidence, *evidence), warnings=tuple(dict.fromkeys(warnings)),
                               limitations=tuple(dict.fromkeys(limitations)), requires_review=review)


def classify_record(record: TestRecord) -> Classification:
    """Tek kaydı sınıflandırır. Kaydı değiştirmez; sonuç `record.with_analysis(...)` ile eklenebilir."""
    quality = _quality_rule(record)
    if quality is not None:
        return quality
    if record.source_type == SOURCE_JUNIT_XML:
        return _classify_junit_with_expectation(record)
    return _classify_http(record)


def classify_records(records: Iterable[TestRecord]) -> list[TestRecord]:
    return [record.with_analysis(classify_record(record)) for record in records]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def build_junit_document(
    reports: Sequence[JUnitReport],
    errors: Sequence[JUnitReportError] = (),
    *,
    now: Callable[[], str] = _utc_now_iso,
) -> dict[str, Any]:
    """Ayrıştırılmış raporların kayıtlarını sınıflandırır ve makine okunur belge üretir.

    `content_sha256`, `generated_at` dışındaki içeriğin özetidir (aynı girdiler → aynı özet).
    """
    return build_classification_document(
        [r for report in reports for r in report.records],
        sources=[report.to_dict() for report in reports],
        file_errors=[error.to_dict() for error in errors],
        summary_extra={"files_parsed": len(reports), "files_rejected": len(errors)},
        now=now,
    )


def build_classification_document(
    records: Iterable[TestRecord],
    *,
    sources: Sequence[dict[str, Any]],
    file_errors: Sequence[dict[str, Any]] = (),
    summary_extra: dict[str, Any] | None = None,
    content_extra: dict[str, Any] | None = None,
    notes_extra: Sequence[str] = (),
    now: Callable[[], str] = _utc_now_iso,
) -> dict[str, Any]:
    """Kayıtları sınıflandırır ve ortak belge biçimini üretir (JUnit raporları ve Lab çalıştırmaları için aynı).

    `content_extra` belgeye ek üst düzey alanlar ekler (ör. toplu analizde `duplicate_reports`); `content_sha256`
    bu alanları da kapsar.
    """
    records = classify_records(records)
    by_class = Counter(r.analysis.classification for r in records)
    content = {
        "classifier_version": CLASSIFIER_VERSION,
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "sources": list(sources),
        "file_errors": list(file_errors),
        "summary": {
            "records": len(records),
            "by_classification": {c: by_class.get(c, 0) for c in CLASSES},
            "by_test_outcome": dict(sorted(Counter(r.test_outcome for r in records).items())),
            "requires_review": sum(r.analysis.requires_review for r in records),
            **(summary_extra or {}),
        },
        "notes": [
            "Sınıflandırma kural tabanlıdır; makine öğrenmesi modeli kullanılmaz. confidence olasılık değildir; "
            "kararın dayandığı kanıtın türünü gösterir. Kurallar gerçek HGS2 hata örnekleriyle doğrulanmadı.",
            "test_outcome kaynağın kararıdır; analysis.classification analiz motorunun kararıdır.",
            "Gecikme anomalisi (F5 Robust Z-score) bu belgede değerlendirilmez; ayrı bir eksendir.",
            "dataset_kind alanı kaydın gerçek sistem, sentetik deney veya fikstür olduğunu belirtir; sentetik ve "
            "fikstür sonuçları gerçek HGS2 doğruluğu hakkında bilgi vermez.",
            *notes_extra,
        ],
        **(content_extra or {}),
        "records": [r.to_dict() for r in records],
    }
    return {
        "format": DOCUMENT_FORMAT,
        "document_schema_version": DOCUMENT_SCHEMA_VERSION,
        "generated_at": now(),
        "content_sha256": hashlib.sha256(_canonical(content)).hexdigest(),
        "classification": content,
    }
