"""Beklenti sözleşmesi ve registry (`expectations_version: 2`): senaryonun beklenen davranışı, dayandığı kanıt
referansları, doğrulama durumu ve test kayıtlarıyla deterministik eşleştirme (ağ yok).

Dosya biçimi (JSON; bilinmeyen anahtarlar her düzeyde reddedilir):

    {"expectations_version": 2,
     "registry_id": "hgs2-auth",                      # isteğe bağlı
     "evidence": [{"evidence_id": "ev-1", "source_type": "approved_business_rule",
                   "source_ref": "IS-KURALI-12", "location": "madde 3", "supports": ["business_outcome"],
                   "review_status": "REVIEWED", "relation": "supports", "source_version": "v4",
                   "description": "..."}],
     "expectations": [{"expectation_id": "exp-kart-pasif", "version": 1, "scenario_id": "kart-pasif-cihaz",
                       "endpoint_id": "POST /api/auth/kart-okut", "status": "VERIFIED", "scope": "real",
                       "expected_http_status": [200], "expected_business_outcome": ["REDDEDILDI"],
                       "expected_test_outcome": "PASS", "expected_transport": "response",
                       "evidence_ids": ["ev-1"], "description": "..."}]}

Doğrulama durumu (records.EXPECTATION_STATUSES): DRAFT (taslak), REVIEWED (incelendi, doğrulama kapsamı sınırlı),
VERIFIED (belirtilen kapsamda kanıtla desteklenir), DEPRECATED (eşleştirmede kullanılmaz). Yalnızca VERIFIED
doğrulanmış sayılır; VERIFIED da gerçek dünyanın tamamında doğruluk iddiası değildir.

Kanıt yeterliliği (deterministik, `assess_evidence`): VERIFIED için beklenen her alan (http_status,
business_outcome, transport, test_outcome) en az bir İNCELENMİŞ (`review_status = REVIEWED`), `relation = supports`
ve kapsama uygun kaynak türündeki kanıtla desteklenmeli; o alanı çürüten incelenmiş kanıt olmamalı. Gerçek kapsamda
(`scope = real`) kaynak kod incelemesi ve sentetik fikstür doğrulayıcı kaynak sayılmaz (kaynak koddan çıkarılan
varsayım onaylanmış iş kuralı değildir; sentetik fikstür gerçek davranışı doğrulamaz). REVIEWED en az bir kanıt
referansı ister. Bu koşulları sağlamayan bir dosya bütünüyle reddedilir; kısmen geçerli registry üretilmez.

Aynı `scenario_id` için birden fazla etkin (DEPRECATED olmayan) beklenti dosyayı geçersiz kılmaz; registry bunu
`conflicts` altında raporlar ve o senaryo için eşleştirme `conflict` döner: tek bir beklenti seçilmez.
Eşleştirme yalnızca kayıttaki `scenario_id` ile birebir yapılır; `endpoint_id` açıklayıcıdır, eşleştirmede
kullanılmaz (kayıtlarda güvenilir bir uç kimliği yoktur).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .records import (
    EXPECTATION_DEPRECATED,
    EXPECTATION_REVIEWED,
    EXPECTATION_SCOPES,
    EXPECTATION_SOURCE_REGISTRY,
    EXPECTATION_STATUSES,
    EXPECTATION_VERIFIED,
    EXPECTED_TRANSPORTS,
    OUTCOME_UNKNOWN,
    SCOPE_REAL,
    SCOPE_SYNTHETIC,
    TEST_OUTCOMES,
    ExpectationProvenance,
    ExpectedResult,
    RecordError,
)
from .response_parser import RECOGNIZED_BUSINESS_OUTCOMES
from .sanitize import sanitize_text

EXPECTATIONS_VERSION = 2

SOURCE_EXISTING_TEST = "existing_test"
SOURCE_CODE_REVIEW = "source_code_review"
SOURCE_OFFICIAL_DOC = "official_documentation"
SOURCE_BUSINESS_RULE = "approved_business_rule"
SOURCE_SYNTHETIC_FIXTURE = "synthetic_fixture"
SOURCE_MANUAL_REVIEW = "manual_review"
SOURCE_UNKNOWN = "unknown"
EVIDENCE_SOURCE_TYPES = frozenset({SOURCE_EXISTING_TEST, SOURCE_CODE_REVIEW, SOURCE_OFFICIAL_DOC, SOURCE_BUSINESS_RULE,
                                   SOURCE_SYNTHETIC_FIXTURE, SOURCE_MANUAL_REVIEW, SOURCE_UNKNOWN})
# Kapsam başına doğrulayıcı (VERIFIED'i gerekçelendirebilen) kaynak türleri
VERIFYING_SOURCES = {
    SCOPE_REAL: frozenset({SOURCE_EXISTING_TEST, SOURCE_OFFICIAL_DOC, SOURCE_BUSINESS_RULE, SOURCE_MANUAL_REVIEW}),
    SCOPE_SYNTHETIC: frozenset({SOURCE_SYNTHETIC_FIXTURE, SOURCE_EXISTING_TEST, SOURCE_OFFICIAL_DOC,
                                SOURCE_MANUAL_REVIEW}),
}
REVIEW_UNREVIEWED = "UNREVIEWED"
REVIEW_REVIEWED = "REVIEWED"
REVIEW_STATUSES = frozenset({REVIEW_UNREVIEWED, REVIEW_REVIEWED})
RELATION_SUPPORTS = "supports"
RELATION_CONTRADICTS = "contradicts"
RELATIONS = frozenset({RELATION_SUPPORTS, RELATION_CONTRADICTS})
FIELD_HTTP_STATUS = "http_status"
FIELD_BUSINESS_OUTCOME = "business_outcome"
FIELD_TEST_OUTCOME = "test_outcome"
FIELD_TRANSPORT = "transport"
EVIDENCE_FIELDS = frozenset({FIELD_HTTP_STATUS, FIELD_BUSINESS_OUTCOME, FIELD_TEST_OUTCOME, FIELD_TRANSPORT})

MATCH_MATCHED = "matched"
MATCH_NOT_FOUND = "not_found"
MATCH_CONFLICT = "conflict"
MATCH_DEPRECATED_ONLY = "deprecated_only"
MATCH_NO_SCENARIO = "no_scenario_id"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Yerel mutlak yollar (kullanıcı adı sızdırır) kaynak referansı olarak kabul edilmez.
_LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|root|var|tmp)/)|^~[\\/]")
_MAX_REF, _MAX_LOCATION, _MAX_DESCRIPTION = 300, 200, 500


class ExpectationsError(ValueError):
    """Beklenti dosyası okunamadı veya geçersiz. `issues` tüm bulguları (alan yolu + açıklama) taşır; değer içermez."""

    def __init__(self, message: str, issues: Sequence[str] = ()) -> None:
        self.issues = tuple(issues) or (message,)
        super().__init__(message if not issues else f"{message}: " + "; ".join(self.issues))


def _check_keys(data: Any, allowed: set[str], required: set[str], where: str, issues: list[str]) -> bool:
    if not isinstance(data, dict):
        issues.append(f"{where}: nesne olmalı")
        return False
    unknown = sorted(str(k) for k in data if k not in allowed)
    missing = sorted(required - set(data))
    if unknown:
        issues.append(f"{where}: bilinmeyen anahtar(lar) {unknown}")
    if missing:
        issues.append(f"{where}: eksik zorunlu anahtar(lar) {missing}")
    return not unknown and not missing


def _id(value: Any, where: str, issues: list[str]) -> bool:
    if not isinstance(value, str) or not _ID_RE.match(value):
        issues.append(f"{where}: harf/rakamla başlayan, yalnızca harf, rakam, '.', '_', '-' içeren kimlik olmalı "
                      "(en çok 64)")
        return False
    return True


def _text(value: Any, where: str, limit: int, issues: list[str], *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        issues.append(f"{where}: boş olmayan, en çok {limit} karakterlik metin olmalı")
        return None
    return sanitize_text(value)


@dataclass(frozen=True)
class EvidenceReference:
    """Bir beklentinin dayandığı kaynağa güvenli başvuru. İçerik kopyalanmaz; kimlik, konum ve kapsam tutulur.

    Bir referansın varlığı içeriğin incelendiği anlamına gelmez: bunu `review_status = REVIEWED` söyler.
    """

    evidence_id: str
    source_type: str
    source_ref: str  # kaynağın tanımlayıcısı (belge kodu, test adı, depo içi göreli dosya); mutlak yerel yol değil
    supports: tuple[str, ...]  # bu kanıtın ilgili olduğu beklenti alanları
    review_status: str = REVIEW_UNREVIEWED
    relation: str = RELATION_SUPPORTS  # supports | contradicts
    location: str | None = None  # bölüm, test adı, satır aralığı vb.
    source_version: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "source_type": self.source_type, "source_ref": self.source_ref,
                "supports": list(self.supports), "review_status": self.review_status, "relation": self.relation,
                "location": self.location, "source_version": self.source_version, "description": self.description}


@dataclass(frozen=True)
class ScenarioExpectation:
    expectation_id: str
    version: int
    scenario_id: str
    status: str
    scope: str
    expected: ExpectedResult  # beklenen davranış (provenance olmadan)
    evidence_ids: tuple[str, ...] = ()
    endpoint_id: str | None = None
    description: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status != EXPECTATION_DEPRECATED

    def expected_fields(self) -> tuple[str, ...]:
        e = self.expected
        fields = []
        if e.status_codes:
            fields.append(FIELD_HTTP_STATUS)
        if e.business_outcomes:
            fields.append(FIELD_BUSINESS_OUTCOME)
        if e.expected_transport:
            fields.append(FIELD_TRANSPORT)
        if e.expected_test_outcome:
            fields.append(FIELD_TEST_OUTCOME)
        return tuple(fields)

    def to_dict(self) -> dict[str, Any]:
        e = self.expected
        return {"expectation_id": self.expectation_id, "version": self.version, "scenario_id": self.scenario_id,
                "endpoint_id": self.endpoint_id, "status": self.status, "scope": self.scope,
                "expected_http_status": list(e.status_codes) or None,
                "expected_business_outcome": list(e.business_outcomes) or None,
                "expected_test_outcome": e.expected_test_outcome, "expected_transport": e.expected_transport,
                "evidence_ids": list(self.evidence_ids), "description": self.description}


def assess_evidence(expectation: ScenarioExpectation, evidence: Mapping[str, EvidenceReference]) -> tuple[str, ...]:
    """Kanıt yeterliliği bulguları (sıralı kod listesi). VERIFIED için `verification_blockers` boş olmalıdır."""
    issues: list[str] = []
    refs = [evidence[i] for i in expectation.evidence_ids if i in evidence]
    if not refs:
        issues.append("no_evidence")
    if refs and not any(r.review_status == REVIEW_REVIEWED for r in refs):
        issues.append("evidence_unreviewed")
    verifying = VERIFYING_SOURCES[expectation.scope]
    for ref in refs:
        if ref.source_type == SOURCE_UNKNOWN:
            issues.append(f"unknown_source:{ref.evidence_id}")
        elif ref.relation == RELATION_SUPPORTS and ref.source_type not in verifying:
            issues.append(f"non_verifying_source:{ref.evidence_id}")
        if ref.relation == RELATION_CONTRADICTS:
            issues.append(f"contradicting_evidence:{ref.evidence_id}")
    for field in expectation.expected_fields():
        if not any(r.review_status == REVIEW_REVIEWED and r.relation == RELATION_SUPPORTS
                   and r.source_type in verifying and field in r.supports for r in refs):
            issues.append(f"field_not_verified:{field}")
        if any(r.review_status == REVIEW_REVIEWED and r.relation == RELATION_CONTRADICTS and field in r.supports
               for r in refs):
            issues.append(f"field_contradicted:{field}")
    return tuple(sorted(set(issues)))


def verification_blockers(issues: Sequence[str]) -> list[str]:
    """VERIFIED durumunu engelleyen bulgular."""
    return [i for i in issues if i in ("no_evidence", "evidence_unreviewed")
            or i.startswith(("field_not_verified:", "field_contradicted:"))]


@dataclass(frozen=True)
class ExpectationMatch:
    status: str  # matched | not_found | conflict | deprecated_only | no_scenario_id
    expected: ExpectedResult | None  # yalnızca matched: provenance eklenmiş beklenti
    candidate_ids: tuple[str, ...] = ()

    @property
    def warning(self) -> str | None:
        return None if self.status == MATCH_MATCHED else f"expectation_{self.status}"


@dataclass(frozen=True)
class ExpectationRegistry:
    expectations: tuple[ScenarioExpectation, ...]  # (scenario_id, expectation_id) sırasıyla
    evidence: Mapping[str, EvidenceReference]
    assessments: Mapping[str, tuple[str, ...]]  # expectation_id → kanıt yeterliliği bulguları
    registry_id: str | None = None
    source: Mapping[str, Any] | None = None  # dosya adı + SHA-256 (yol değil)

    @property
    def conflicts(self) -> dict[str, list[str]]:
        """scenario_id → aynı senaryo için etkin beklenti kimlikleri (birden fazlaysa)."""
        by_scenario: dict[str, list[str]] = {}
        for exp in self.expectations:
            if exp.is_active:
                by_scenario.setdefault(exp.scenario_id, []).append(exp.expectation_id)
        return {k: v for k, v in by_scenario.items() if len(v) > 1}

    @property
    def unused_evidence(self) -> list[str]:
        used = {i for e in self.expectations for i in e.evidence_ids}
        return sorted(set(self.evidence) - used)

    def to_dict(self) -> dict[str, Any]:
        return {"expectations_version": EXPECTATIONS_VERSION, "registry_id": self.registry_id,
                "evidence": [self.evidence[k].to_dict() for k in sorted(self.evidence)],
                "expectations": [e.to_dict() for e in self.expectations]}

    @property
    def content_sha256(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, Any]:
        statuses = {s: sum(e.status == s for e in self.expectations) for s in sorted(EXPECTATION_STATUSES)}
        return {"registry_id": self.registry_id, "expectations_version": EXPECTATIONS_VERSION,
                "content_sha256": self.content_sha256, "source": dict(self.source) if self.source else None,
                "expectations": len(self.expectations), "by_status": statuses,
                "scenarios": len({e.scenario_id for e in self.expectations}), "evidence": len(self.evidence),
                "conflicts": self.conflicts, "unused_evidence": self.unused_evidence}

    def lookup(self, scenario_id: str) -> list[ScenarioExpectation]:
        return [e for e in self.expectations if e.scenario_id == scenario_id]

    def match(self, scenario_id: str | None) -> ExpectationMatch:
        """Kayıttaki senaryo kimliğiyle birebir eşleştirme. Belirsizlikte hiçbir beklenti seçilmez."""
        if not scenario_id:
            return ExpectationMatch(MATCH_NO_SCENARIO, None)
        candidates = self.lookup(scenario_id)
        active = [e for e in candidates if e.is_active]
        ids = tuple(e.expectation_id for e in candidates)
        if not candidates:
            return ExpectationMatch(MATCH_NOT_FOUND, None)
        if not active:
            return ExpectationMatch(MATCH_DEPRECATED_ONLY, None, ids)
        if len(active) > 1:
            return ExpectationMatch(MATCH_CONFLICT, None, tuple(e.expectation_id for e in active))
        exp = active[0]
        provenance = ExpectationProvenance(
            source=EXPECTATION_SOURCE_REGISTRY, expectation_id=exp.expectation_id, version=exp.version,
            verification_status=exp.status, scope=exp.scope, evidence_ids=exp.evidence_ids,
            evidence_issues=self.assessments.get(exp.expectation_id, ()))
        e = exp.expected
        expected = ExpectedResult(status_codes=e.status_codes, business_outcomes=e.business_outcomes,
                                  description=exp.description, expected_test_outcome=e.expected_test_outcome,
                                  expected_transport=e.expected_transport, provenance=provenance)
        return ExpectationMatch(MATCH_MATCHED, expected, ids)


_EVIDENCE_KEYS = {"evidence_id", "source_type", "source_ref", "supports", "review_status", "relation", "location",
                  "source_version", "description"}
_EXPECTATION_KEYS = {"expectation_id", "version", "scenario_id", "endpoint_id", "status", "scope",
                     "expected_http_status", "expected_business_outcome", "expected_test_outcome",
                     "expected_transport", "evidence_ids", "description"}


def _parse_evidence(item: Any, where: str, issues: list[str]) -> EvidenceReference | None:
    if not _check_keys(item, _EVIDENCE_KEYS, {"evidence_id", "source_type", "source_ref", "supports"}, where,
                       issues):
        return None
    before = len(issues)
    _id(item["evidence_id"], f"{where}.evidence_id", issues)
    if item["source_type"] not in EVIDENCE_SOURCE_TYPES:
        issues.append(f"{where}.source_type: şunlardan biri olmalı: {', '.join(sorted(EVIDENCE_SOURCE_TYPES))}")
    ref = _text(item["source_ref"], f"{where}.source_ref", _MAX_REF, issues, required=True)
    if isinstance(item["source_ref"], str) and _LOCAL_PATH_RE.match(item["source_ref"].strip()):
        issues.append(f"{where}.source_ref: mutlak yerel yol kullanılamaz (göreli kaynak tanımlayıcısı verin)")
    supports = item["supports"]
    if not isinstance(supports, list) or not supports or not all(s in EVIDENCE_FIELDS for s in supports) \
            or len(set(supports)) != len(supports):
        issues.append(f"{where}.supports: {', '.join(sorted(EVIDENCE_FIELDS))} değerlerinden oluşan, tekrarsız, "
                      "boş olmayan liste olmalı")
    review = item.get("review_status", REVIEW_UNREVIEWED)
    if review not in REVIEW_STATUSES:
        issues.append(f"{where}.review_status: UNREVIEWED veya REVIEWED olmalı")
    relation = item.get("relation", RELATION_SUPPORTS)
    if relation not in RELATIONS:
        issues.append(f"{where}.relation: supports veya contradicts olmalı")
    location = _text(item.get("location"), f"{where}.location", _MAX_LOCATION, issues)
    version = _text(item.get("source_version"), f"{where}.source_version", 100, issues)
    description = _text(item.get("description"), f"{where}.description", _MAX_DESCRIPTION, issues)
    if len(issues) > before:
        return None
    return EvidenceReference(evidence_id=item["evidence_id"], source_type=item["source_type"], source_ref=ref,
                             supports=tuple(sorted(supports)), review_status=review, relation=relation,
                             location=location, source_version=version, description=description)


def _parse_expectation(item: Any, where: str, issues: list[str]) -> ScenarioExpectation | None:
    if not _check_keys(item, _EXPECTATION_KEYS, {"expectation_id", "version", "scenario_id", "status", "scope"},
                       where, issues):
        return None
    before = len(issues)
    _id(item["expectation_id"], f"{where}.expectation_id", issues)
    _id(item["scenario_id"], f"{where}.scenario_id", issues)
    version = item["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        issues.append(f"{where}.version: 1 veya daha büyük tam sayı olmalı")
    if item["status"] not in EXPECTATION_STATUSES:
        issues.append(f"{where}.status: şunlardan biri olmalı: {', '.join(sorted(EXPECTATION_STATUSES))}")
    if item["scope"] not in EXPECTATION_SCOPES:
        issues.append(f"{where}.scope: synthetic veya real olmalı")
    endpoint = _text(item.get("endpoint_id"), f"{where}.endpoint_id", 200, issues)
    description = _text(item.get("description"), f"{where}.description", _MAX_DESCRIPTION, issues)
    statuses = item.get("expected_http_status")
    outcomes = item.get("expected_business_outcome")
    for key, value in (("expected_http_status", statuses), ("expected_business_outcome", outcomes)):
        if value is not None and (not isinstance(value, list) or not value):
            issues.append(f"{where}.{key}: boş olmayan liste ya da null (bilinmiyor) olmalı")
    if isinstance(outcomes, list) and not all(isinstance(o, str) and o.strip().upper() in RECOGNIZED_BUSINESS_OUTCOMES
                                              for o in outcomes):
        issues.append(f"{where}.expected_business_outcome: yalnızca yanıt ayrıştırıcısının tanıdığı değerler: "
                      f"{', '.join(sorted(RECOGNIZED_BUSINESS_OUTCOMES))}")
    test_outcome = item.get("expected_test_outcome")
    if test_outcome is not None and test_outcome not in TEST_OUTCOMES - {OUTCOME_UNKNOWN}:
        issues.append(f"{where}.expected_test_outcome: PASS, FAIL, ERROR veya SKIPPED olmalı")
    transport = item.get("expected_transport")
    if transport is not None and transport not in EXPECTED_TRANSPORTS:
        issues.append(f"{where}.expected_transport: şunlardan biri olmalı: {', '.join(sorted(EXPECTED_TRANSPORTS))}")
    evidence_ids = item.get("evidence_ids", [])
    if not isinstance(evidence_ids, list) or len(set(map(str, evidence_ids))) != len(evidence_ids):
        issues.append(f"{where}.evidence_ids: tekrarsız kimlik listesi olmalı")
        evidence_ids = []
    for n, eid in enumerate(evidence_ids):
        _id(eid, f"{where}.evidence_ids[{n}]", issues)
    if len(issues) > before:
        return None
    try:
        expected = ExpectedResult(status_codes=tuple(statuses or ()),
                                  business_outcomes=tuple(o.strip().upper() for o in outcomes or ()),
                                  expected_test_outcome=test_outcome, expected_transport=transport)
    except RecordError as exc:
        issues.append(f"{where}: {exc}")
        return None
    if not expected.is_defined and expected.expected_test_outcome is None:
        issues.append(f"{where}: en az bir beklenen alan gerekli (expected_http_status, expected_business_outcome, "
                      "expected_transport veya expected_test_outcome); bilinmeyen alanlar null bırakılır")
        return None
    return ScenarioExpectation(expectation_id=item["expectation_id"], version=version,
                               scenario_id=item["scenario_id"], status=item["status"], scope=item["scope"],
                               expected=expected, evidence_ids=tuple(evidence_ids), endpoint_id=endpoint,
                               description=description)


def parse_registry(data: Any, *, source: Mapping[str, Any] | None = None) -> ExpectationRegistry:
    """Sözleşmeyi doğrular. Tek bir hata bile varsa tüm dosya reddedilir (ExpectationsError, tüm bulgularla)."""
    issues: list[str] = []
    if not _check_keys(data, {"expectations_version", "registry_id", "evidence", "expectations"},
                       {"expectations_version", "expectations"}, "kök", issues):
        raise ExpectationsError("Beklenti dosyası geçersiz", issues)
    if data["expectations_version"] != EXPECTATIONS_VERSION or isinstance(data["expectations_version"], bool):
        raise ExpectationsError(f"expectations_version {EXPECTATIONS_VERSION} olmalı")
    registry_id = data.get("registry_id")
    if registry_id is not None:
        _id(registry_id, "registry_id", issues)
    raw_evidence = data.get("evidence", [])
    raw_expectations = data["expectations"]
    if not isinstance(raw_evidence, list):
        issues.append("evidence: liste olmalı")
        raw_evidence = []
    if not isinstance(raw_expectations, list) or not raw_expectations:
        issues.append("expectations: boş olmayan liste olmalı")
        raw_expectations = []

    evidence: dict[str, EvidenceReference] = {}
    for n, item in enumerate(raw_evidence):
        ref = _parse_evidence(item, f"evidence[{n}]", issues)
        if ref is not None:
            if ref.evidence_id in evidence:
                issues.append(f"evidence[{n}].evidence_id: yinelenen kimlik")
            evidence[ref.evidence_id] = ref
    expectations: list[ScenarioExpectation] = []
    seen: set[str] = set()
    for n, item in enumerate(raw_expectations):
        exp = _parse_expectation(item, f"expectations[{n}]", issues)
        if exp is None:
            continue
        if exp.expectation_id in seen:
            issues.append(f"expectations[{n}].expectation_id: yinelenen kimlik")
        seen.add(exp.expectation_id)
        for eid in exp.evidence_ids:
            if eid not in evidence:
                issues.append(f"expectations[{n}].evidence_ids: tanımsız kanıt kimliği")
        expectations.append(exp)
    for exp in expectations:
        if exp.status == EXPECTATION_REVIEWED and not exp.evidence_ids:
            issues.append(f"beklenti {exp.expectation_id}: REVIEWED en az bir kanıt referansı gerektirir")
    if issues:
        raise ExpectationsError("Beklenti dosyası geçersiz", issues)

    assessments = {e.expectation_id: assess_evidence(e, evidence) for e in expectations}
    for exp in expectations:
        blockers = verification_blockers(assessments[exp.expectation_id])
        if exp.status == EXPECTATION_VERIFIED and blockers:
            issues.append(f"beklenti {exp.expectation_id}: VERIFIED kanıtla gerekçelendirilemiyor ({', '.join(blockers)})")
    if issues:
        raise ExpectationsError("Beklenti dosyası geçersiz", issues)
    ordered = tuple(sorted(expectations, key=lambda e: (e.scenario_id, e.expectation_id)))
    return ExpectationRegistry(expectations=ordered, evidence=dict(sorted(evidence.items())), assessments=assessments,
                               registry_id=registry_id, source=source)


def load_registry(path: str | Path) -> ExpectationRegistry:
    """Dosyayı yalnızca okur. Hata mesajları dosyanın yalnızca adını içerir."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ExpectationsError(f"Beklenti dosyası bulunamadı: {path.name}") from None
    except OSError as exc:
        raise ExpectationsError(f"Beklenti dosyası okunamadı: {path.name} ({type(exc).__name__})") from None
    if not raw.strip():
        raise ExpectationsError(f"Beklenti dosyası boş: {path.name}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        where = f" (satır {exc.lineno}, sütun {exc.colno})" if isinstance(exc, json.JSONDecodeError) else ""
        raise ExpectationsError(f"Beklenti dosyası geçerli UTF-8 JSON değil: {path.name}{where}") from None
    return parse_registry(data, source={"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
