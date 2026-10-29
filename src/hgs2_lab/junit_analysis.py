"""Toplu JUnit/Surefire analizi (N8): raporlar → N3 ayrıştırıcı → TestRecord → açık senaryo kimliği → N7 beklenti
registry'si → N4 sınıflandırıcı → tek JSON belge (ağ yok).

* Raporlar mevcut `junit_report.parse_junit_report` ile tek tek okunur; bozuk/boş/eksik dosya diğerlerini durdurmaz ve
  `file_errors` altında kod + mesajla listelenir.
* Bayt bayt aynı içerikli (aynı SHA-256) rapor ikinci kez verilirse yeniden işlenmez; `duplicate_reports` altında ilk
  kopyasıyla birlikte listelenir (aynı içerik → aynı kayıt kimlikleri; bu güvenilir bir tekilleştirmedir).
* Farklı raporlarda aynı `test_id` görülürse kayıtlar BİRLEŞTİRİLMEZ; `possible_duplicate_tests` altında raporlanır.
* Eşleştirme yalnızca kaydın açık `scenario_id` değeriyle (JUnit'te testcase özelliği `hgs2_lab.scenario_id`) birebir
  yapılır. Test, sınıf, suite veya uç adından kimlik türetilmez. Beklenti dosyası sürüm 2 (registry) ya da sürüm 1
  (senaryo → beklenti) olabilir; geçersiz/okunamayan dosya çağıran tarafından hata olarak ele alınır (bkz. cli).
* N10: isteğe bağlı senaryo eşleme dosyası (`scenario_mapping.py`) beklenti eşleştirmesinden ÖNCE uygulanır; metadata
  ile çelişki veya belirsizlik kimliği boş bırakır. Her kayıt için `scenario_trace` girdisi kaynak sonucu, senaryo
  çözümlemesini, beklenti eşleşmesini, doğrulama durumunu, kapsam uyumunu, N4 kararını ve inceleme gereksinimini ayrı
  alanlarda taşır. Eşleme dosyası verilmezse kayıtlar N8'deki gibi aynen işlenir.
"""

from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .classify import _SCOPE_DATASETS, build_classification_document, classify_records
from .expectations import MATCH_MATCHED, MATCH_NO_SCENARIO, MATCH_NOT_FOUND, ExpectationRegistry
from .junit_report import SCENARIO_ID_PROPERTY, JUnitReport, JUnitReportError, parse_junit_report
from .records import (
    DATASET_UNKNOWN,
    EXPECTATION_SOURCE_REGISTRY,
    OUTCOME_SKIPPED,
    OUTCOME_UNKNOWN,
    ExpectedResult,
    TestRecord,
)
from .scenario_mapping import (
    RESOLUTION_STATUSES,
    ScenarioMapping,
    ScenarioResolution,
    apply_scenario_mapping,
    mapping_source,
)

Expectations = Mapping[str, ExpectedResult] | ExpectationRegistry

# Kayıt başına karar dayanağı (scenario_trace.decision_basis): beklentinin kesin karşılaştırmaya uygun olup olmadığı.
BASIS_NO_SCENARIO = "no_scenario_id"
BASIS_NO_EXPECTATIONS = "no_expectations"
BASIS_UNVERIFIED = "expectation_unverified"
BASIS_VERIFICATION_UNSPECIFIED = "expectation_verification_unspecified"
BASIS_SCOPE_MISMATCH = "expectation_scope_mismatch"
BASIS_SCOPE_UNCONFIRMED = "expectation_scope_unconfirmed"
BASIS_NOT_COMPARABLE = "expectation_not_comparable"
BASIS_VERIFIED = "verified_expectation_in_scope"
# Kaynak sonuç ↔ uygun beklenti karşılaştırması. N4 kararını DEĞİŞTİRMEZ; ayrı bir eksendir.
ASSESSMENT_CONSISTENT = "consistent"
ASSESSMENT_INCONSISTENT = "inconsistent"
ASSESSMENT_UNDETERMINED = "undetermined"

COUNTER_DEFINITIONS = {
    "files_given": "Komuta verilen rapor yolu sayısı (tekrarlar dahil).",
    "files_parsed": "Başarıyla ayrıştırılan, içeriği benzersiz rapor sayısı.",
    "files_rejected": "Ayrıştırılamayan rapor sayısı (file_errors); analiz edilen raporlara dahil değildir.",
    "files_duplicate": "Daha önce verilmiş bir raporla bayt bayt aynı olduğu için yeniden işlenmeyen rapor sayısı.",
    "suites": "Ayrıştırılan raporlardaki <testsuite> sayısı (bir rapor birden çok suite içerebilir).",
    "records": "Ayrıştırılan raporlardaki testcase kaydı sayısı; her kayıt tam olarak bir sınıfa düşer.",
    "by_test_outcome": "Kaynak raporun kendi sonucu (PASS/FAIL/ERROR/SKIPPED/UNKNOWN); analiz sonucu değildir.",
    "by_classification": "N4 analiz sınıfı; INCONCLUSIVE/UNKNOWN başka sınıflara eklenmez.",
    "requires_review": "İnceleme gerektiren kayıt sayısı; başarısızlık sayısı değildir.",
    "expectation_matching.by_match_status": "Beklenti dosyası verildiyse kayıt başına eşleştirme sonucu "
                                             "(matched/not_found/conflict/deprecated_only/no_scenario_id).",
    "expectation_matching.matched_by_verification_status": "Eşleşen kayıtların beklenti doğrulama durumu; eşleşme "
                                                           "doğrulama demek değildir.",
    "data_quality.by_status": "Kayıtların veri kalitesi durumu.",
    "possible_duplicate_tests": "Aynı test_id'nin birden fazla kayıtta görülmesi; kayıtlar birleştirilmez.",
    "scenario_resolution.by_status": "Kayıt başına senaryo kimliği çözümlemesi (metadata / eşleme dosyası / ikisi; "
                                     "bulunamadı, belirsiz veya çelişkili durumlar ayrı).",
    "scenario_resolution.by_outcome": "resolved / not_found / ambiguous / conflict; belirsiz ve çelişkili kayıtlarda "
                                      "kimlik seçilmez.",
    "scenario_resolution.requires_review": "Senaryo kimliği belirsiz veya çelişkili olduğu için incelenmesi gereken "
                                           "kayıt sayısı (N4 inceleme sayacından ayrı).",
    "scenario_resolution.by_decision_basis": "Beklentinin kesin karşılaştırmaya uygunluğu (kimlik yok, beklenti yok, "
                                             "doğrulanmamış, kapsam dışı, gözlenemez, uygun).",
    "scenario_resolution.by_expectation_assessment": "Yalnızca uygun (VERIFIED + kapsamda) beklentiler için kaynak "
                                                     "sonucun beklentiyle tutarlılığı; N4 kararını değiştirmez.",
}


def parse_reports(
    paths: Iterable[str | Path], *, dataset_kind: str = DATASET_UNKNOWN
) -> tuple[list[JUnitReport], list[JUnitReportError], list[dict[str, Any]], int]:
    """(raporlar, dosya hataları, tekrar eden raporlar, verilen yol sayısı). Hiçbir dosya hatası işlemi durdurmaz."""
    reports: list[JUnitReport] = []
    errors: list[JUnitReportError] = []
    duplicates: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    given = 0
    for path in paths:
        given += 1
        try:
            report = parse_junit_report(path, dataset_kind=dataset_kind)
        except JUnitReportError as exc:
            errors.append(exc)
            continue
        if report.source_sha256 in seen:
            duplicates.append({"source_file": report.source_file, "duplicate_of": seen[report.source_sha256],
                               "source_sha256": report.source_sha256})
            continue
        seen[report.source_sha256] = report.source_file
        reports.append(report)
    return reports, errors, duplicates, given


def _match(record: TestRecord, expectations: Expectations) -> tuple[str, ExpectedResult | None, str | None]:
    """(eşleşme durumu, beklenti, kayda eklenecek uyarı)."""
    if isinstance(expectations, ExpectationRegistry):
        match = expectations.match(record.scenario_id)
        return match.status, match.expected, match.warning
    if not record.scenario_id:
        return MATCH_NO_SCENARIO, None, f"expectation_{MATCH_NO_SCENARIO}"
    if record.scenario_id in expectations:
        return MATCH_MATCHED, expectations[record.scenario_id], None
    return MATCH_NOT_FOUND, None, f"expectation_{MATCH_NOT_FOUND}"


def attach_expectations(
    records: Sequence[TestRecord], expectations: Expectations | None
) -> tuple[list[TestRecord], Counter[str]]:
    """Kayıtlara açık senaryo kimliğiyle beklenti bağlar. Eşleşmeyen kayıt korunur; yalnızca uyarı eklenir."""
    if expectations is None:
        return list(records), Counter()
    out, statuses = [], Counter()
    for record in records:
        status, expected, warning = _match(record, expectations)
        statuses[status] += 1
        if expected is not None:
            record = dataclasses.replace(record, expected_result=expected)
        elif warning is not None:
            record = dataclasses.replace(record, warnings=(*record.warnings, warning))
        out.append(record)
    return out, statuses


def _expectation_view(record: TestRecord, expectations: Expectations | None) -> dict[str, Any]:
    """Kaydın beklenti eşleşmesi, doğrulama durumu ve kapsam uyumu (N7 registry'sinin kendi eşleştirmesiyle)."""
    view: dict[str, Any] = {"match_status": "not_requested", "candidate_ids": [], "expectation_id": None,
                            "version": None, "source": None, "verification_status": None, "scope": None,
                            "scope_compatible": None, "expected_test_outcome": None}
    if expectations is None:
        return view
    if isinstance(expectations, ExpectationRegistry):
        match = expectations.match(record.scenario_id)
        view["match_status"], view["candidate_ids"] = match.status, list(match.candidate_ids)
    else:
        view["match_status"] = _match(record, expectations)[0]
    expected = record.expected_result
    if expected is not None and view["match_status"] == MATCH_MATCHED:
        view["expected_test_outcome"] = expected.expected_test_outcome
        provenance = expected.provenance
        if provenance is not None:
            view.update(expectation_id=provenance.expectation_id, version=provenance.version,
                        source=provenance.source, verification_status=provenance.verification_status,
                        scope=provenance.scope)
            if provenance.scope is not None and record.dataset_kind != DATASET_UNKNOWN:
                view["scope_compatible"] = record.dataset_kind in _SCOPE_DATASETS[provenance.scope]
    return view


def _decision_basis(record: TestRecord, view: dict[str, Any]) -> str:
    if not record.scenario_id:
        return BASIS_NO_SCENARIO
    if view["match_status"] == "not_requested":
        return BASIS_NO_EXPECTATIONS
    if view["match_status"] != MATCH_MATCHED:
        return f"expectation_{view['match_status']}"
    if view["source"] != EXPECTATION_SOURCE_REGISTRY:
        return BASIS_VERIFICATION_UNSPECIFIED
    if view["verification_status"] != "VERIFIED":
        return BASIS_UNVERIFIED
    if record.dataset_kind == DATASET_UNKNOWN:
        return BASIS_SCOPE_UNCONFIRMED
    if not view["scope_compatible"]:
        return BASIS_SCOPE_MISMATCH
    if view["expected_test_outcome"] is None:  # yalnızca HTTP/iş sonucu/taşıma: JUnit kaydında gözlenemez
        return BASIS_NOT_COMPARABLE
    return BASIS_VERIFIED


def _assessment(record: TestRecord, basis: str, expected_outcome: str | None) -> tuple[str | None, str]:
    """(kaynak sonuç karşılaştırması, değerlendirme). Çalıştırılmamış veya bilinmeyen sonuç kanıt sayılmaz."""
    comparison = None
    if expected_outcome is not None:
        comparison = "match" if expected_outcome == record.test_outcome else "differs"
    if basis != BASIS_VERIFIED:
        return comparison, ASSESSMENT_UNDETERMINED
    if comparison == "differs" and record.test_outcome in (OUTCOME_SKIPPED, OUTCOME_UNKNOWN):
        return comparison, ASSESSMENT_UNDETERMINED
    return comparison, ASSESSMENT_CONSISTENT if comparison == "match" else ASSESSMENT_INCONSISTENT


def build_scenario_trace(
    records: Sequence[TestRecord], resolutions: Sequence[ScenarioResolution], expectations: Expectations | None
) -> list[dict[str, Any]]:
    """Kayıt başına izlenebilirlik: her katman ayrı alanda; hiçbiri diğerinin yerine geçmez.

    `records` sınıflandırılmış (analysis dolu) ve beklentisi bağlanmış kayıtlardır; `resolutions` aynı sıradadır.
    """
    trace = []
    for record, resolution in zip(records, resolutions, strict=True):
        view = _expectation_view(record, expectations)
        basis = _decision_basis(record, view)
        comparison, assessment = _assessment(record, basis, view["expected_test_outcome"])
        analysis = record.analysis
        reasons = []
        if resolution.requires_review:
            reasons.append(f"scenario_{resolution.status}")
        if analysis is not None and analysis.requires_review:
            reasons.append("classifier")
        trace.append({
            "record_id": record.record_id,
            "source_file": record.source_file,
            "source_sha256": record.source_sha256,
            "test_id": record.test_id,
            "test_name": record.test_name,
            "dataset_kind": record.dataset_kind,
            "source_test_outcome": record.test_outcome,
            "scenario": resolution.to_dict(),
            "expectation": view,
            "decision_basis": basis,
            "outcome_vs_expectation": comparison,
            "expectation_assessment": assessment,
            "classification": None if analysis is None else {
                "classification": analysis.classification, "rule_ids": list(analysis.rule_ids),
                "confidence": analysis.confidence, "reason": analysis.reason,
                "requires_review": analysis.requires_review, "warnings": list(analysis.warnings)},
            "requires_review": bool(reasons),
            "review_reasons": reasons,
        })
    return trace


def _resolution_summary(trace: Sequence[dict[str, Any]], mapping_requested: bool) -> dict[str, Any]:
    statuses = Counter(t["scenario"]["status"] for t in trace)
    return {
        "mapping_requested": mapping_requested,
        "by_status": {s: statuses.get(s, 0) for s in RESOLUTION_STATUSES},
        "by_outcome": dict(sorted(Counter(t["scenario"]["outcome"] for t in trace).items())),
        "by_source": dict(sorted(Counter("+".join(t["scenario"]["sources"]) or "none" for t in trace).items())),
        "requires_review": sum(t["scenario"]["requires_review"] for t in trace),
        "by_decision_basis": dict(sorted(Counter(t["decision_basis"] for t in trace).items())),
        "by_expectation_assessment": dict(sorted(Counter(t["expectation_assessment"] for t in trace).items())),
    }


def _possible_duplicates(records: Sequence[TestRecord]) -> list[dict[str, Any]]:
    by_test: dict[str, list[TestRecord]] = defaultdict(list)
    for record in records:
        if record.test_id:
            by_test[record.test_id].append(record)
    return [{"test_id": test_id, "occurrences": len(group), "record_ids": [r.record_id for r in group],
             "source_files": sorted({r.source_file for r in group if r.source_file})}
            for test_id, group in sorted(by_test.items()) if len(group) > 1]


def build_junit_analysis_document(
    reports: Sequence[JUnitReport],
    errors: Sequence[JUnitReportError] = (),
    *,
    duplicates: Sequence[dict[str, Any]] = (),
    files_given: int | None = None,
    expectations: Expectations | None = None,
    expectations_source: dict[str, Any] | None = None,
    scenario_mapping: ScenarioMapping | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Toplu analiz belgesi. Sayaçlar yalnızca gerçekten ayrıştırılan kayıtlardan hesaplanır (COUNTER_DEFINITIONS).

    Sıra: ayrıştırma → senaryo çözümlemesi (metadata + isteğe bağlı eşleme dosyası) → beklenti eşleştirme → N4.
    """
    records = [r for report in reports for r in report.records]
    records, resolutions = apply_scenario_mapping(records, scenario_mapping)
    records, statuses = attach_expectations(records, expectations)
    trace = build_scenario_trace(classify_records(records), resolutions, expectations)
    matched_status = Counter(r.expected_result.provenance.verification_status or "unspecified"
                             for r in records if r.expected_result is not None
                             and r.expected_result.provenance is not None)
    with_scenario = sum(1 for r in records if r.scenario_id)
    summary_extra = {
        "files_given": files_given if files_given is not None else len(reports) + len(errors) + len(duplicates),
        "files_parsed": len(reports),
        "files_rejected": len(errors),
        "files_duplicate": len(duplicates),
        "suites": sum(len(report.suites) for report in reports),
        "expectation_matching": {
            "requested": expectations is not None,
            "scenario_id_property": SCENARIO_ID_PROPERTY,
            "records_with_scenario_id": with_scenario,
            "records_without_scenario_id": len(records) - with_scenario,
            "by_match_status": dict(sorted(statuses.items())),
            "matched_by_verification_status": dict(sorted(matched_status.items())),
        },
        "data_quality": {
            "by_status": dict(sorted(Counter(r.data_quality_status for r in records).items())),
            "records_with_warnings": sum(1 for r in records if r.warnings),
            "suite_warnings": sum(len(s.warnings) for report in reports for s in report.suites),
        },
        "possible_duplicate_tests": _possible_duplicates(records),
        "scenario_resolution": _resolution_summary(trace, scenario_mapping is not None),
        "counter_definitions": COUNTER_DEFINITIONS,
    }
    notes = ["Kaynak PASS sayısı uygulamanın bütün olarak başarılı olduğu anlamına gelmez; yalnızca rapordaki "
             "testlerin kendi sonucudur."]
    if expectations is None:
        notes.append("Beklenti dosyası verilmedi: kayıtlar beklentisiz analiz edildi; kararlar yalnızca kaynak test "
                     "sonucuna ve hata kanıtına dayanır.")
    if scenario_mapping is not None:
        notes.append("Senaryo kimlikleri testcase özelliği ve eşleme dosyasından çözümlendi; çelişkili veya belirsiz "
                     "kayıtlarda kimlik seçilmedi (scenario_trace). expectation_assessment yalnızca VERIFIED ve "
                     "kapsamdaki beklentiler için verilir ve N4 kararını değiştirmez.")
    kwargs = {"now": now} if now is not None else {}
    return build_classification_document(
        records, sources=[report.to_dict() for report in reports], file_errors=[e.to_dict() for e in errors],
        summary_extra=summary_extra, notes_extra=notes,
        content_extra={"duplicate_reports": list(duplicates), "expectations": expectations_source,
                       "scenario_mapping": mapping_source(scenario_mapping) if scenario_mapping is not None else None,
                       "scenario_trace": trace},
        **kwargs)
