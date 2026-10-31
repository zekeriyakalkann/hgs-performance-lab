"""Birleşik test kaydı (`TestRecord`): farklı kaynaklardan gelen test sonuçlarının ortak modeli (ağ yok).

Kaynaklar: JUnit/Surefire XML raporları (`junit_report.py`) ve Lab'in kendi istek sonuçları (`RawResult`,
`record_from_raw_result`). Kayıt üç ayrı bilgi katmanını birbirinden ayırır ve karıştırmaz:

1. **Kaynağın söylediği** (`test_outcome`): JUnit'in PASS/FAIL/ERROR/SKIPPED kararı ya da Lab'in HTTP durum
   denetimi. Analiz motoru bu alanı değiştirmez.
2. **Etiket** (`label`, `label_source`): insan veya deney tasarımından gelen ground truth. Model/kural tahmini
   asla buraya yazılmaz.
3. **Analiz** (`analysis`): sınıflandırıcının kararı, gerekçesi, kanıtları ve güven düzeyi (`classify.py`).

Bilinmeyen değerler `None` ile temsil edilir; kaynakta olmayan bir değer uydurulmaz. Maskeleme sınırı modelin
kendisidir: serbest metin alanları ve kanıt değerleri kurulum sırasında `sanitize` kurallarından geçer, bu yüzden
hiçbir `TestRecord` örneği (ve onun JSON'u) maskelenmemiş hassas değer taşımaz. Kaynak dosya yalnızca adıyla
anılır (yerel yol yazılmaz).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .models import ERROR_TYPES, RawResult
from .response_parser import STATE_MALFORMED_JSON, STATE_UNDECODABLE, ParsedResponse
from .sanitize import sanitize_data, sanitize_text

RECORD_SCHEMA_VERSION = 2  # 2: expected_result'a beklenen kaynak sonucu, taşıma ve provenance eklendi

# Kaynak türü
SOURCE_JUNIT_XML = "junit_xml"
SOURCE_LAB_RESULT = "lab_result"
SOURCE_TYPES = frozenset({SOURCE_JUNIT_XML, SOURCE_LAB_RESULT})

# Veri türü: gerçek sistem çıktısı, sentetik deney, test fikstürü ya da bilinmiyor. Karıştırılmaz.
DATASET_REAL = "real"
DATASET_SYNTHETIC = "synthetic"
DATASET_FIXTURE = "fixture"
DATASET_UNKNOWN = "unknown"
DATASET_KINDS = frozenset({DATASET_REAL, DATASET_SYNTHETIC, DATASET_FIXTURE, DATASET_UNKNOWN})

# Kaynağın kendi test sonucu (analiz sonucu değildir)
OUTCOME_PASS = "PASS"
OUTCOME_FAIL = "FAIL"
OUTCOME_ERROR = "ERROR"
OUTCOME_SKIPPED = "SKIPPED"
OUTCOME_UNKNOWN = "UNKNOWN"
TEST_OUTCOMES = frozenset({OUTCOME_PASS, OUTCOME_FAIL, OUTCOME_ERROR, OUTCOME_SKIPPED, OUTCOME_UNKNOWN})

# Veri kalitesi: valid = kullanılabilir; partial = bazı alanlar eksik/geçersiz (uyarılarda);
# contradictory = kaynak kendi içinde çelişkili; invalid = kayıt anlamlandırılamaz.
QUALITY_VALID = "valid"
QUALITY_PARTIAL = "partial"
QUALITY_CONTRADICTORY = "contradictory"
QUALITY_INVALID = "invalid"
QUALITY_STATUSES = frozenset({QUALITY_VALID, QUALITY_PARTIAL, QUALITY_CONTRADICTORY, QUALITY_INVALID})

LABEL_SOURCES = frozenset({"synthetic_plan", "human_review"})

# Beklenti doğrulama durumu (expectations.py). Yalnızca VERIFIED doğrulanmış sayılır; DRAFT ve REVIEWED kesin teşhis
# gerekçesi olamaz; DEPRECATED eşleştirmede kullanılmaz.
EXPECTATION_DRAFT = "DRAFT"
EXPECTATION_REVIEWED = "REVIEWED"
EXPECTATION_VERIFIED = "VERIFIED"
EXPECTATION_DEPRECATED = "DEPRECATED"
EXPECTATION_STATUSES = frozenset({EXPECTATION_DRAFT, EXPECTATION_REVIEWED, EXPECTATION_VERIFIED,
                                  EXPECTATION_DEPRECATED})
# Beklentinin geçerli olduğu kapsam: Lab'in sentetik ortamı ya da gerçek hedef sistem. Karıştırılmaz.
SCOPE_SYNTHETIC = "synthetic"
SCOPE_REAL = "real"
EXPECTATION_SCOPES = frozenset({SCOPE_SYNTHETIC, SCOPE_REAL})
# Beklentinin kaynağı
EXPECTATION_SOURCE_REGISTRY = "expectation_registry"  # sürümlü sözleşme (expectations_version 2)
EXPECTATION_SOURCE_FILE_V1 = "expectations_file_v1"  # eski biçim; doğrulama durumu yok
EXPECTATION_SOURCE_SCENARIO = "scenario_expected_status"  # senaryonun açık expected_status listesi
EXPECTATION_SOURCES = frozenset({EXPECTATION_SOURCE_REGISTRY, EXPECTATION_SOURCE_FILE_V1, EXPECTATION_SOURCE_SCENARIO})
# Beklenen taşıma davranışı: HTTP yanıtı ya da belirli bir taşıma hatası
TRANSPORT_RESPONSE = "response"
EXPECTED_TRANSPORTS = frozenset({TRANSPORT_RESPONSE, *ERROR_TYPES})

# Analiz sınıfları (classify.py)
CLASS_PASS = "PASS"
CLASS_APPLICATION_FAILURE = "APPLICATION_FAILURE"
CLASS_TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
CLASS_TIMEOUT = "TIMEOUT"
CLASS_TEST_INFRASTRUCTURE_FAILURE = "TEST_INFRASTRUCTURE_FAILURE"
CLASS_INVALID_TEST_DATA = "INVALID_TEST_DATA"
CLASS_INCONCLUSIVE = "INCONCLUSIVE"  # kanıt yetersiz veya çelişkili; daha fazla bilgiyle karar verilebilir
CLASS_UNKNOWN = "UNKNOWN"  # sistemin bu kayıt türü için kuralı yok
CLASSES = (
    CLASS_PASS, CLASS_APPLICATION_FAILURE, CLASS_TRANSPORT_FAILURE, CLASS_TIMEOUT,
    CLASS_TEST_INFRASTRUCTURE_FAILURE, CLASS_INVALID_TEST_DATA, CLASS_INCONCLUSIVE, CLASS_UNKNOWN,
)
# Kural tabanlı güven düzeyi: olasılık DEĞİLDİR (bkz. classify.py). Kesin karar verilmeyen sınıflarda None.
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Senaryo kimliği biçimi (beklenti sözleşmesi ve JUnit `hgs2_lab.scenario_id` özelliğiyle aynı).
SCENARIO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_CODE_RE = re.compile(r"^[a-z0-9_]+(:[A-Za-z0-9_.,=-]+)?$")


class RecordError(ValueError):
    """Geçersiz TestRecord. Mesajlar alan adlarını ve türleri içerir, alan değerlerini içermez."""


def _optional_text(obj: Any, name: str) -> None:
    value = getattr(obj, name)
    if value is not None and (not isinstance(value, str) or not value):
        raise RecordError(f"{name} boş olmayan metin ya da null olmalı (alınan: {type(value).__name__})")


def _one_of(value: Any, allowed: frozenset[str], name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or value not in allowed:
        raise RecordError(f"{name} şu değerlerden biri olmalı: {', '.join(sorted(allowed))}")


def _codes(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise RecordError(f"{name} metin listesi olmalı (alınan: {type(value).__name__})")
    items = tuple(value)
    for item in items:
        if not isinstance(item, str) or not _CODE_RE.match(item):
            raise RecordError(f"{name} öğeleri küçük harfli kod olmalı (ör. 'duration_missing')")
    return items


def _texts(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise RecordError(f"{name} metin listesi olmalı (alınan: {type(value).__name__})")
    items = tuple(value)
    if not all(isinstance(item, str) and item for item in items):
        raise RecordError(f"{name} öğeleri boş olmayan metin olmalı")
    return tuple(sanitize_text(item) for item in items)


def _set(obj: Any, name: str, value: Any) -> None:
    object.__setattr__(obj, name, value)


@dataclass(frozen=True)
class ExpectationProvenance:
    """Beklentinin nereden geldiği ve ne kadar doğrulandığı. Beklenen davranıştan (ExpectedResult) ayrıdır."""

    source: str  # EXPECTATION_SOURCES
    expectation_id: str | None = None
    version: int | None = None
    verification_status: str | None = None  # None: kaynak doğrulama durumu taşımıyor (eski biçimler)
    scope: str | None = None
    evidence_ids: tuple[str, ...] = ()
    evidence_issues: tuple[str, ...] = ()  # kanıt yeterliliği değerlendirmesinin bulguları (kod listesi)

    def __post_init__(self) -> None:
        _one_of(self.source, EXPECTATION_SOURCES, "provenance.source")
        if self.expectation_id is not None and (not isinstance(self.expectation_id, str)
                                                or not _ID_RE.match(self.expectation_id)):
            raise RecordError("provenance.expectation_id geçerli bir kimlik olmalı")
        if self.version is not None and (isinstance(self.version, bool) or not isinstance(self.version, int)
                                         or self.version < 1):
            raise RecordError("provenance.version 1 veya daha büyük tam sayı olmalı")
        _one_of(self.verification_status, EXPECTATION_STATUSES, "provenance.verification_status", optional=True)
        _one_of(self.scope, EXPECTATION_SCOPES, "provenance.scope", optional=True)
        if isinstance(self.evidence_ids, str) or not isinstance(self.evidence_ids, Sequence) \
                or not all(isinstance(i, str) and _ID_RE.match(i) for i in self.evidence_ids):
            raise RecordError("provenance.evidence_ids kimlik listesi olmalı")
        if self.source == EXPECTATION_SOURCE_REGISTRY and (self.expectation_id is None or self.version is None
                                                           or self.verification_status is None or self.scope is None):
            raise RecordError("Sözleşme beklentisinde kimlik, sürüm, doğrulama durumu ve kapsam zorunlu")
        _set(self, "evidence_ids", tuple(self.evidence_ids))
        _set(self, "evidence_issues", _codes(self.evidence_issues, "provenance.evidence_issues"))

    @property
    def is_verified(self) -> bool:
        return self.verification_status == EXPECTATION_VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "expectation_id": self.expectation_id, "version": self.version,
                "verification_status": self.verification_status, "scope": self.scope,
                "evidence_ids": list(self.evidence_ids), "evidence_issues": list(self.evidence_issues)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExpectationProvenance":
        keys = {"source", "expectation_id", "version", "verification_status", "scope", "evidence_ids",
                "evidence_issues"}
        _check_keys(data, keys, {"source"}, "provenance")
        return cls(source=data["source"], expectation_id=data.get("expectation_id"), version=data.get("version"),
                   verification_status=data.get("verification_status"), scope=data.get("scope"),
                   evidence_ids=tuple(data.get("evidence_ids", ())),
                   evidence_issues=tuple(data.get("evidence_issues", ())))


@dataclass(frozen=True)
class ExpectedResult:
    """Testin beklenen sonucu. Boş (hiçbir beklenti tanımlı değil) ise beklenen sonuç bilinmiyor demektir.

    `expected_test_outcome` yalnızca kanıt olarak karşılaştırılır; kaynak sonucunu değiştirmez ve tek başına karar
    üretmez. `expected_transport` bir taşıma hatası ise HTTP durum kodu veya iş sonucu beklentisiyle birlikte
    verilemez (çelişki). Bir HTTP durum kodunun hangi iş sonucuna karşılık geldiği varsayılmaz.
    """

    status_codes: tuple[int, ...] = ()
    business_outcomes: tuple[str, ...] = ()  # ör. ("ONAYLANDI",) ya da negatif testte ("REDDEDILDI",)
    description: str | None = None
    expected_test_outcome: str | None = None  # PASS | FAIL | ERROR | SKIPPED
    expected_transport: str | None = None  # response | timeout | connection_error | transport_error
    provenance: ExpectationProvenance | None = None

    def __post_init__(self) -> None:
        if isinstance(self.status_codes, (str, bytes)) or not isinstance(self.status_codes, Sequence):
            raise RecordError("expected_result.status_codes tam sayı listesi olmalı")
        codes = tuple(self.status_codes)
        for code in codes:
            if isinstance(code, bool) or not isinstance(code, int) or not 100 <= code <= 599:
                raise RecordError("expected_result.status_codes öğeleri 100-599 aralığında tam sayı olmalı")
        if isinstance(self.business_outcomes, (str, bytes)) or not isinstance(self.business_outcomes, Sequence):
            raise RecordError("expected_result.business_outcomes metin listesi olmalı")
        outcomes = tuple(self.business_outcomes)
        if not all(isinstance(item, str) and item.strip() for item in outcomes):
            raise RecordError("expected_result.business_outcomes öğeleri boş olmayan metin olmalı")
        _optional_text(self, "description")
        _one_of(self.expected_test_outcome, TEST_OUTCOMES - {OUTCOME_UNKNOWN}, "expected_result.expected_test_outcome",
                optional=True)
        _one_of(self.expected_transport, EXPECTED_TRANSPORTS, "expected_result.expected_transport", optional=True)
        if self.provenance is not None and not isinstance(self.provenance, ExpectationProvenance):
            raise RecordError("expected_result.provenance ExpectationProvenance ya da null olmalı")
        if self.expected_transport in ERROR_TYPES:
            if codes or outcomes:
                raise RecordError("Taşıma hatası beklenirken HTTP durum kodu veya iş sonucu beklenemez (çelişki)")
            if self.expected_test_outcome == OUTCOME_PASS:
                raise RecordError("Taşıma hatası beklenirken kaynak sonucu PASS beklenemez (çelişki)")
        if len(set(codes)) != len(codes) or len({o.strip().upper() for o in outcomes}) != len(outcomes):
            raise RecordError("expected_result listelerinde yinelenen değer var")
        _set(self, "status_codes", codes)
        _set(self, "business_outcomes", tuple(sanitize_text(item) for item in outcomes))
        if self.description is not None:
            _set(self, "description", sanitize_text(self.description))

    @property
    def is_defined(self) -> bool:
        """Karar verdirebilecek bir beklenti var mı? (`expected_test_outcome` yalnızca kanıttır, sayılmaz.)"""
        return bool(self.status_codes or self.business_outcomes or self.expected_transport)

    def to_dict(self) -> dict[str, Any]:
        return {"status_codes": list(self.status_codes), "business_outcomes": list(self.business_outcomes),
                "description": self.description, "expected_test_outcome": self.expected_test_outcome,
                "expected_transport": self.expected_transport,
                "provenance": self.provenance.to_dict() if self.provenance is not None else None}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExpectedResult":
        keys = {"status_codes", "business_outcomes", "description", "expected_test_outcome", "expected_transport",
                "provenance"}
        _check_keys(data, keys, set(), "expected_result")  # kayıt şeması 1'in üç alanlı biçimi de kabul edilir
        provenance = data.get("provenance")
        if provenance is not None and not isinstance(provenance, Mapping):
            raise RecordError("expected_result.provenance nesne ya da null olmalı")
        return cls(status_codes=tuple(data.get("status_codes", ())),
                   business_outcomes=tuple(data.get("business_outcomes", ())),
                   description=data.get("description"), expected_test_outcome=data.get("expected_test_outcome"),
                   expected_transport=data.get("expected_transport"),
                   provenance=ExpectationProvenance.from_dict(provenance) if provenance is not None else None)


@dataclass(frozen=True)
class Evidence:
    """Bir kararı destekleyen tek kanıt: hangi alan, hangi (maskeli) değer, nereden geldiği."""

    field: str  # ör. "status_code", "expected_result.business_outcomes", "exception_type"
    value: Any  # JSON uyumlu; metinler maskelenir
    source: str = "record"  # "record" = kaydın kendisi, "rule" = kuralın türettiği bilgi
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.field, str) or not self.field:
            raise RecordError("evidence.field boş olmayan metin olmalı")
        if self.source not in ("record", "rule"):
            raise RecordError("evidence.source 'record' veya 'rule' olmalı")
        _optional_text(self, "note")
        try:
            value = sanitize_data(self.value)
        except TypeError as exc:
            raise RecordError(f"evidence.value JSON uyumlu olmalı: {exc}") from None
        _set(self, "value", value)
        if self.note is not None:
            _set(self, "note", sanitize_text(self.note))

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "value": self.value, "source": self.source, "note": self.note}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Evidence":
        _check_keys(data, {"field", "value", "source", "note"}, {"field", "value"}, "evidence")
        return cls(field=data["field"], value=data["value"], source=data.get("source", "record"),
                   note=data.get("note"))


@dataclass(frozen=True)
class Classification:
    """Sınıflandırıcının kararı. Kaynak test sonucundan (`TestRecord.test_outcome`) ayrıdır."""

    classification: str
    rule_ids: tuple[str, ...]
    reason: str
    evidence: tuple[Evidence, ...] = ()
    confidence: str | None = None  # "high" | "medium" | "low" | None; olasılık değildir
    requires_review: bool = False
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    classifier_version: str = "rules-v1"

    def __post_init__(self) -> None:
        _one_of(self.classification, frozenset(CLASSES), "classification")
        rule_ids = _texts(self.rule_ids, "rule_ids")
        if not rule_ids:
            raise RecordError("rule_ids en az bir kural içermeli")
        if not isinstance(self.reason, str) or not self.reason:
            raise RecordError("reason boş olmayan metin olmalı")
        if isinstance(self.evidence, (str, bytes)) or not isinstance(self.evidence, Sequence) \
                or not all(isinstance(e, Evidence) for e in self.evidence):
            raise RecordError("evidence Evidence listesi olmalı")
        _one_of(self.confidence, CONFIDENCE_LEVELS, "confidence", optional=True)
        if self.classification in (CLASS_INCONCLUSIVE, CLASS_UNKNOWN) and self.confidence is not None:
            raise RecordError(f"{self.classification} kararında confidence null olmalı (kesin karar yok)")
        if not isinstance(self.requires_review, bool):
            raise RecordError("requires_review bool olmalı")
        _optional_text(self, "classifier_version")
        _set(self, "rule_ids", rule_ids)
        _set(self, "reason", sanitize_text(self.reason))
        _set(self, "evidence", tuple(self.evidence))
        _set(self, "warnings", _codes(self.warnings, "warnings"))
        _set(self, "limitations", _texts(self.limitations, "limitations"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification, "rule_ids": list(self.rule_ids), "reason": self.reason,
            "evidence": [e.to_dict() for e in self.evidence], "confidence": self.confidence,
            "requires_review": self.requires_review, "warnings": list(self.warnings),
            "limitations": list(self.limitations), "classifier_version": self.classifier_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Classification":
        keys = {"classification", "rule_ids", "reason", "evidence", "confidence", "requires_review", "warnings",
                "limitations", "classifier_version"}
        _check_keys(data, keys, {"classification", "rule_ids", "reason"}, "analysis")
        evidence = data.get("evidence", [])
        if not isinstance(evidence, list) or not all(isinstance(e, Mapping) for e in evidence):
            raise RecordError("analysis.evidence nesne listesi olmalı")
        return cls(
            classification=data["classification"], rule_ids=tuple(data["rule_ids"]), reason=data["reason"],
            evidence=tuple(Evidence.from_dict(e) for e in evidence), confidence=data.get("confidence"),
            requires_review=data.get("requires_review", False), warnings=tuple(data.get("warnings", ())),
            limitations=tuple(data.get("limitations", ())),
            classifier_version=data.get("classifier_version", "rules-v1"),
        )


_TEXT_FIELDS = ("test_id", "test_name", "suite_name", "scenario_id", "business_outcome", "exception_type",
                "error_message", "stack_trace")


@dataclass(frozen=True)
class TestRecord:
    """Tek bir test sonucu. Yalnızca `record_id`, `source_type`, `dataset_kind` ve `test_outcome` zorunludur."""

    __test__ = False  # pytest bu sınıfı test sınıfı sanmasın

    record_id: str
    source_type: str
    dataset_kind: str
    test_outcome: str  # kaynağın kararı; analiz sonucu değil
    # kimlik ve kaynak
    run_id: str | None = None
    source_file: str | None = None  # yalnızca dosya adı
    source_sha256: str | None = None
    test_id: str | None = None
    test_name: str | None = None
    suite_name: str | None = None
    scenario_id: str | None = None
    timestamp: str | None = None
    # beklenen ve gözlenen
    expected_result: ExpectedResult | None = None  # None: beklenen sonuç bilinmiyor
    status_code: int | None = None
    business_outcome: str | None = None  # yanıt gövdesindeki iş sonucu (ör. REDDEDILDI); kaynakta yoksa None
    duration_ms: float | None = None
    transport_error: str | None = None  # timeout | connection_error | transport_error
    # hata bilgileri
    exception_type: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    # etiket ve veri kalitesi
    label: str | None = None
    label_source: str | None = None
    data_quality_status: str = QUALITY_VALID
    warnings: tuple[str, ...] = ()
    # analiz
    analysis: Classification | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not _ID_RE.match(self.record_id):
            raise RecordError("record_id harf/rakamla başlamalı; yalnızca harf, rakam, '.', '_', ':', '-' içermeli "
                              "(en çok 128 karakter)")
        _one_of(self.source_type, SOURCE_TYPES, "source_type")
        _one_of(self.dataset_kind, DATASET_KINDS, "dataset_kind")
        _one_of(self.test_outcome, TEST_OUTCOMES, "test_outcome")
        _one_of(self.data_quality_status, QUALITY_STATUSES, "data_quality_status")
        for name in ("run_id", "source_file", "source_sha256", "timestamp", "label", "label_source",
                     *_TEXT_FIELDS):
            _optional_text(self, name)
        if self.source_file is not None and ("/" in self.source_file or "\\" in self.source_file):
            raise RecordError("source_file yalnızca dosya adı olmalı (yol içermemeli)")
        if self.source_sha256 is not None and not _SHA256_RE.match(self.source_sha256):
            raise RecordError("source_sha256 64 karakterlik küçük harfli onaltılık özet olmalı")
        if self.expected_result is not None and not isinstance(self.expected_result, ExpectedResult):
            raise RecordError("expected_result ExpectedResult ya da null olmalı")
        if self.status_code is not None and (isinstance(self.status_code, bool) or not isinstance(self.status_code, int)
                                             or not 100 <= self.status_code <= 599):
            raise RecordError("status_code 100-599 aralığında tam sayı ya da null olmalı")
        if self.duration_ms is not None:
            if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, (int, float)) \
                    or not math.isfinite(self.duration_ms) or self.duration_ms < 0:
                raise RecordError("duration_ms sonlu ve negatif olmayan bir sayı ya da null olmalı")
            _set(self, "duration_ms", float(self.duration_ms))
        _one_of(self.transport_error, ERROR_TYPES, "transport_error", optional=True)
        if (self.label is None) != (self.label_source is None):
            raise RecordError("label ve label_source birlikte dolu ya da birlikte null olmalı")
        _one_of(self.label_source, LABEL_SOURCES, "label_source", optional=True)
        if self.analysis is not None and not isinstance(self.analysis, Classification):
            raise RecordError("analysis Classification ya da null olmalı")
        _set(self, "warnings", _codes(self.warnings, "warnings"))
        for name in _TEXT_FIELDS:  # maskeleme sınırı
            value = getattr(self, name)
            if value is not None:
                _set(self, name, sanitize_text(value))

    def with_analysis(self, analysis: Classification) -> "TestRecord":
        """Analiz sonucu eklenmiş kopya; kaynak alanlar (test_outcome dahil) değişmez."""
        return dataclasses.replace(self, analysis=analysis)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if isinstance(value, (ExpectedResult, Classification)):
                value = value.to_dict()
            elif isinstance(value, tuple):
                value = list(value)
            data[f.name] = value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TestRecord":
        """`to_dict` çıktısından yeniden kurar. Bilinmeyen anahtar reddedilir; eksik isteğe bağlı alan varsayılanı alır."""
        names = {f.name for f in dataclasses.fields(cls)}
        _check_keys(data, names, {"record_id", "source_type", "dataset_kind", "test_outcome"}, "record")
        values = dict(data)
        if values.get("expected_result") is not None:
            if not isinstance(values["expected_result"], Mapping):
                raise RecordError("expected_result nesne ya da null olmalı")
            values["expected_result"] = ExpectedResult.from_dict(values["expected_result"])
        if values.get("analysis") is not None:
            if not isinstance(values["analysis"], Mapping):
                raise RecordError("analysis nesne ya da null olmalı")
            values["analysis"] = Classification.from_dict(values["analysis"])
        if "warnings" in values:
            values["warnings"] = _codes(values["warnings"], "warnings")
        return cls(**values)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "TestRecord":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RecordError(f"Geçerli JSON değil (satır {exc.lineno}, sütun {exc.colno})") from None
        if not isinstance(data, Mapping):
            raise RecordError("JSON kökü nesne olmalı")
        return cls.from_dict(data)


def _check_keys(data: Mapping[str, Any], allowed: set[str], required: set[str], what: str) -> None:
    if not isinstance(data, Mapping):
        raise RecordError(f"{what} nesne olmalı")
    unknown = sorted(str(k) for k in data if k not in allowed)
    missing = sorted(required - set(data))
    if unknown or missing:
        raise RecordError(f"{what}: bilinmeyen anahtar(lar) {unknown}, eksik zorunlu anahtar(lar) {missing}")


def make_record_id(*parts: object) -> str:
    """Parçalardan deterministik kayıt kimliği (`r-` + SHA-256'nın ilk 24 hanesi)."""
    joined = "\x1f".join(str(p) for p in parts)
    return "r-" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def record_from_raw_result(
    result: RawResult,
    *,
    dataset_kind: str,
    expected: ExpectedResult | None = None,
    source_file: str | None = None,
    parsed: ParsedResponse | None = None,
) -> TestRecord:
    """Lab'in istek sonucunu (`RawResult`) TestRecord'a dönüştürür.

    `test_outcome`, Lab'in kendi HTTP durum denetimidir (`http_ok`: durum kodu senaryonun `expected_status`
    listesinde mi): PASS/FAIL; taşıma hatasında ERROR. Beklenen sonuç (`expected`) RawResult'ta yoktur; çağıran
    vermezse None kalır ve sınıflandırıcı kesin karar vermez.

    `parsed`: aynı isteğin yanıt ayrıştırma özeti (response_parser.py). Verilirse kuralı ve uyarıları kaydın
    `warnings` alanına `response_rule:<kural>` ve `response_<uyarı>` olarak eklenir; gövde ayrıştırılamadıysa
    (bozuk JSON, çözülemeyen metin) veya durum kodu geçersizse kalite `partial` olur. Özetteki iş sonucu ve durum
    kodu sonuç kaydıyla uyuşmalıdır.
    """
    if result.error_type is not None:
        outcome = OUTCOME_ERROR
    else:
        outcome = OUTCOME_PASS if result.http_ok else OUTCOME_FAIL
    warnings = ["warmup_request"] if result.warmup else []
    quality = QUALITY_VALID
    if parsed is not None:
        if not isinstance(parsed, ParsedResponse):
            raise RecordError("parsed ParsedResponse ya da null olmalı")
        if parsed.business_outcome != result.business_outcome:
            raise RecordError("Yanıt ayrıştırma özetindeki iş sonucu sonuç kaydıyla uyuşmuyor")
        if result.status_code is not None and parsed.status_code not in (None, result.status_code):
            raise RecordError("Yanıt ayrıştırma özetindeki durum kodu sonuç kaydıyla uyuşmuyor")
        warnings.append(f"response_rule:{parsed.rule_id}")
        warnings.extend(f"response_{w}" for w in parsed.warnings)
        if parsed.body_state in (STATE_MALFORMED_JSON, STATE_UNDECODABLE) or "invalid_status_code" in parsed.warnings:
            quality = QUALITY_PARTIAL
    return TestRecord(
        record_id=make_record_id(SOURCE_LAB_RESULT, result.run_id, result.seq),
        source_type=SOURCE_LAB_RESULT,
        dataset_kind=dataset_kind,
        test_outcome=outcome,
        run_id=result.run_id,
        source_file=source_file,
        test_id=f"{result.run_id}#{result.seq}",
        test_name=f"{result.scenario}#{result.iteration}",
        scenario_id=result.scenario,
        timestamp=result.started_at,
        expected_result=expected,
        status_code=result.status_code,
        business_outcome=result.business_outcome,
        duration_ms=result.duration_ms,
        transport_error=result.error_type,
        error_message=result.error,
        data_quality_status=quality,
        warnings=tuple(warnings),
    )

