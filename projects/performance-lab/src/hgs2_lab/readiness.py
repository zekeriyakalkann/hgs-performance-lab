"""Gerçek HGS2 entegrasyon hazırlığı (N9): rapor alan envanteri, beklenti hazırlığı ve önkoşul (readiness) denetimi.

Ağ yok, veritabanı yok, hedef sistem çalıştırılmaz. Denetim yalnızca verilen dosyaları ve Lab'in kendi bileşenlerini
(N1 maskeleme, N3 ayrıştırıcı, N7 registry, N8 toplu analiz, N4 sınıflandırıcı) çevrimdışı çalıştırır.

Sonuç (`status`):

* READY — bütün önkoşullar karşılandı.
* READY_WITH_WARNINGS — engelleyici eksik yok; uyarılar var (ör. bazı kayıtlarda senaryo kimliği yok).
* BLOCKED — en az bir engelleyici önkoşul eksik (ör. hiç senaryo kimliği yok, kapsamda doğrulanmış beklenti yok).

READY, hedef sistemin doğru çalıştığını ya da beklentilerin gerçek dünyada doğru olduğunu GÖSTERMEZ; yalnızca bu
denetimin tanımladığı önkoşulların karşılandığını gösterir. Dosyaların bulunması iş kurallarının doğrulanması değildir.

N10: senaryo eşleme dosyası (`scenario_mapping.py`) verilirse senaryo kimliği kapsamı (A3), kimlik kalitesi (A4) ve
beklenti örtüşmesi (B4) çözümlenen kimliklerle hesaplanır; A6 (eşleme dosyası) ve C5 (eşleme öz-testi) denetimleri
eklenir. Eşleme dosyası verilmezse denetimler N9'daki gibidir.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .expectations import ExpectationRegistry, ExpectationsError, verification_blockers
from .junit_analysis import build_junit_analysis_document, parse_reports
from .junit_report import (
    ERROR_UNSAFE_XML,
    SCENARIO_ID_PROPERTY,
    JUnitReport,
    JUnitReportError,
    parse_junit_bytes,
)
from .records import (
    CLASSES,
    DATASET_REAL,
    DATASET_SYNTHETIC,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_UNKNOWN,
    QUALITY_VALID,
    SCOPE_REAL,
)
from .result_analysis import load_expectations
from .sanitize import sanitize_text
from .scenario_mapping import (
    OUTCOME_AMBIGUOUS,
    OUTCOME_CONFLICT,
    RES_METADATA_MAPPING_CONFLICT,
    RES_MAPPING_CONFLICT,
    MappingError,
    ScenarioMapping,
    apply_scenario_mapping,
    load_mapping,
    mapping_source,
    parse_mapping,
)

READINESS_VERSION = 1
READY = "READY"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
BLOCKED = "BLOCKED"
CHECK_PASS, CHECK_WARN, CHECK_FAIL = "pass", "warn", "fail"

# Alan envanteri durumları
FIELD_AVAILABLE = "available"  # tüm ilgili kayıtlarda var ve okunuyor
FIELD_PARTIAL = "partial"  # bazı kayıtlarda var
FIELD_MISSING = "missing"  # biçimde olabilirdi ama bu raporda yok
FIELD_NOT_APPLICABLE = "not_applicable"  # ilgili kayıt yok (ör. hiç FAIL/ERROR yokken hata türü)
FIELD_PRESENT_NOT_PARSED = "present_not_parsed"  # raporda var ama ayrıştırıcı içeriğini okumuyor
FIELD_WITHHELD = "withheld_for_security"  # bilinçli olarak okunmuyor (gizli değer içerebilir)
FIELD_NOT_IN_FORMAT = "not_in_format"  # JUnit/Surefire biçiminde böyle bir alan yok

_CANARIES = ("CANARY-KART-0001", "CANARY-TOKEN-0002", "CANARY-PASS-0003", "CANARY-PROP-0004")
_XXE = (b'<?xml version="1.0"?><!DOCTYPE t [<!ENTITY x SYSTEM "file:///etc/hostname">]>'
        b'<testsuite name="x"><testcase name="&x;"/></testsuite>')
_METADATA_PROBE = (f'<testsuite name="s"><properties><property name="db.password" value="{_CANARIES[3]}"/>'
                   f'</properties><testcase name="t" classname="c"><properties>'
                   f'<property name="{SCENARIO_ID_PROPERTY}" value="kimlik-1"/>'
                   f'<property name="token" value="{_CANARIES[3]}"/></properties></testcase></testsuite>').encode()


def _field(status: str, with_value: int | None, considered: int | None, note: str) -> dict[str, Any]:
    return {"status": status, "records_with_value": with_value, "records_considered": considered, "note": note}


def _coverage(count: int, total: int, note: str, *, na_note: str | None = None) -> dict[str, Any]:
    if total == 0:
        return _field(FIELD_NOT_APPLICABLE, 0, 0, na_note or note)
    status = FIELD_AVAILABLE if count == total else (FIELD_PARTIAL if count else FIELD_MISSING)
    return _field(status, count, total, note)


def inventory_junit_report(report: JUnitReport) -> dict[str, Any]:
    """Bir raporda hangi alanların gerçekten bulunduğunu çıkarır. Değer içermez; yalnızca durum ve sayılar."""
    records = report.records
    n = len(records)
    failing = [r for r in records if r.test_outcome in (OUTCOME_FAIL, OUTCOME_ERROR)]
    ignored = Counter()
    for suite in report.suites:
        ignored.update(suite.ignored_sections)
    warnings = Counter(w for r in records for w in r.warnings)
    na = "Raporda FAIL/ERROR kaydı yok; hata alanı beklenmez."
    fields = {
        "test_class": _coverage(sum(1 for r in records if r.test_id and "#" in r.test_id), n,
                                "testcase `classname` özniteliği"),
        "test_name": _coverage(sum(1 for r in records if r.test_name), n, "testcase `name` özniteliği"),
        "source_outcome": _coverage(sum(1 for r in records if r.test_outcome != OUTCOME_UNKNOWN), n,
                                    "failure/error/skipped öğelerinden; UNKNOWN çelişkili sonuç öğesi demektir"),
        "duration": _coverage(sum(1 for r in records if r.duration_ms is not None), n,
                              f"testcase `time`; geçersiz değer {warnings['invalid_duration']}"),
        "error_type": _coverage(sum(1 for r in failing if r.exception_type), len(failing),
                                "failure/error `type` (yoksa iz metninin ilk satırı)", na_note=na),
        "error_message": _coverage(sum(1 for r in failing if r.error_message), len(failing),
                                   "failure/error `message`; maskelenir ve kırpılır", na_note=na),
        "stack_trace": _coverage(sum(1 for r in failing if r.stack_trace), len(failing),
                                 "failure/error metni; maskelenir ve kırpılır", na_note=na),
        "suite_metadata": _field(
            FIELD_AVAILABLE if report.suites else FIELD_MISSING, None, None,
            f"suite adı/süre/beyan edilen sayılar; zaman damgası {sum(1 for s in report.suites if s.timestamp)}/"
            f"{len(report.suites)} suite'te"),
        "properties": _field(
            FIELD_WITHHELD if ignored["properties"] else FIELD_MISSING, None, None,
            f"{ignored['properties']} `<properties>` bölümü; içerik okunmaz (yalnızca testcase düzeyindeki "
            f"`{SCENARIO_ID_PROPERTY}` hariç)"),
        "scenario_id": _coverage(sum(1 for r in records if r.scenario_id), n,
                                 f"testcase özelliği `{SCENARIO_ID_PROPERTY}`; geçersiz "
                                 f"{warnings['scenario_id_invalid']}, çelişkili {warnings['scenario_id_conflict']}"),
        "system_out": _field(FIELD_PRESENT_NOT_PARSED if ignored["system-out"] else FIELD_MISSING, None, None,
                             f"{ignored['system-out']} bölüm; test sırasında yakalanan log, ayrıştırılmaz"),
        "system_err": _field(FIELD_PRESENT_NOT_PARSED if ignored["system-err"] else FIELD_MISSING, None, None,
                             f"{ignored['system-err']} bölüm; ayrıştırılmaz"),
        "expected_result": _field(FIELD_NOT_IN_FORMAT, None, None,
                                  "JUnit/Surefire açık bir beklenen sonuç alanı taşımaz; beklenti registry'den gelir"),
        "observed_http_status": _field(FIELD_NOT_IN_FORMAT, None, None, "JUnit kaydında HTTP durum kodu alanı yok"),
        "observed_business_outcome": _field(FIELD_NOT_IN_FORMAT, None, None, "JUnit kaydında iş sonucu alanı yok"),
    }
    return {
        "source_file": report.source_file,
        "source_sha256": report.source_sha256,
        "suites": len(report.suites),
        "records": n,
        "by_test_outcome": dict(sorted(Counter(r.test_outcome for r in records).items())),
        "data_quality": dict(sorted(Counter(r.data_quality_status for r in records).items())),
        "fields": fields,
    }


_BEHAVIOUR_FIELDS = ("expected_http_status", "expected_business_outcome", "expected_transport", "expected_test_outcome")


def expectation_readiness(registry: ExpectationRegistry, scope: str) -> dict[str, Any]:
    """Kapsam için beklenti hazırlığı: N7 doğrulama kurallarının bulgularını gerçek-kapsam sorularına göre özetler."""
    active = [e for e in registry.expectations if e.is_active]
    in_scope = [e for e in active if e.scope == scope]
    conflicts = registry.conflicts
    checklist = []
    for exp in in_scope:
        data = exp.to_dict()
        issues = registry.assessments.get(exp.expectation_id, ())
        checklist.append({
            "expectation_id": exp.expectation_id,
            "version": exp.version,
            "scenario_id": exp.scenario_id,
            "status": exp.status,
            "behaviour_defined": [f for f in _BEHAVIOUR_FIELDS if data[f] is not None],
            "unspecified_fields": [f for f in _BEHAVIOUR_FIELDS if data[f] is None],
            "evidence_count": len(exp.evidence_ids),
            "evidence_issues": list(issues),
            "verification_blockers": verification_blockers(issues),
            "conflicting": exp.scenario_id in conflicts,
        })
    return {
        "scope": scope,
        "expectations_total": len(registry.expectations),
        "active": len(active),
        "deprecated": len(registry.expectations) - len(active),
        "in_scope_active": len(in_scope),
        "in_scope_by_status": dict(sorted(Counter(e.status for e in in_scope).items())),
        "verified_in_scope": sum(1 for e in in_scope if e.status == "VERIFIED"),
        "out_of_scope_active": len(active) - len(in_scope),
        "conflicts": conflicts,
        "checklist": checklist,
    }


def _check(checks: list, check_id: str, category: str, status: str, message: str, **details: Any) -> None:
    checks.append({"id": check_id, "category": category, "status": status, "message": message, "details": details})


def _security_selftests(checks: list) -> None:
    masked = sanitize_text(f"kartNo={_CANARIES[0]} Authorization: Bearer {_CANARIES[1]} "
                           f"jdbc:postgresql://h/db?password={_CANARIES[2]}")
    leaked = [c for c in _CANARIES[:3] if c in masked]
    _check(checks, "C1-masking", "security", CHECK_FAIL if leaked else CHECK_PASS,
           "N1 maskeleme sentetik kart, token ve bağlantı dizesi değerlerini gizliyor" if not leaked
           else "N1 maskeleme sentetik değerleri gizlemedi", leaked=len(leaked))
    try:
        parse_junit_bytes(_XXE, source_file="xxe-probe.xml")
        xxe_ok = False
    except JUnitReportError as exc:
        xxe_ok = exc.code == ERROR_UNSAFE_XML
    _check(checks, "C2-xml-safety", "security", CHECK_PASS if xxe_ok else CHECK_FAIL,
           "DOCTYPE/varlık içeren XML ayrıştırılmadan reddediliyor" if xxe_ok else "XXE denemesi reddedilmedi")
    probe = parse_junit_bytes(_METADATA_PROBE, source_file="metadata-probe.xml")
    blob = json.dumps([r.to_dict() for r in probe.records] + [probe.to_dict()], ensure_ascii=False)
    withheld = _CANARIES[3] not in blob and probe.records[0].scenario_id == "kimlik-1"
    _check(checks, "C3-metadata-withheld", "security", CHECK_PASS if withheld else CHECK_FAIL,
           "Suite/testcase özellikleri okunmuyor; yalnızca senaryo kimliği okunuyor" if withheld
           else "Hassas özellik değeri çıktıya ulaştı veya senaryo kimliği okunamadı")
    _check(checks, "C4-offline", "security", CHECK_PASS,
           "Denetim yalnızca yerel dosyaları ve Lab bileşenlerini çalıştırır; ağ, veritabanı ve hedef sistem kullanılmaz "
           "(testlerde soket erişimi engellenerek doğrulanır)")


_MAPPING_PROBE_XML = (b'<testsuite name="s"><testcase name="ayni" classname="c.P"><properties>'
                      b'<property name="hgs2_lab.scenario_id" value="ornek-a"/></properties></testcase>'
                      b'<testcase name="farkli" classname="c.P"><properties>'
                      b'<property name="hgs2_lab.scenario_id" value="ornek-a"/></properties></testcase>'
                      b'<testcase name="ikili" classname="c.P"/><testcase name="sinifsiz"/></testsuite>')


def _mapping_selftest(checks: list) -> None:
    """Eşleme mekanizmasının güvenlik özellikleri: çelişki seçilmez, ad türetilmez, hassas tanımlayıcı reddedilir."""
    def entry(mapping_id: str, name: str, scenario: str, test_class: str = "c.P") -> dict[str, str]:
        return {"mapping_id": mapping_id, "test_class": test_class, "test_name": name, "scenario_id": scenario,
                "status": "ACTIVE"}

    mapping = parse_mapping({"scenario_mapping_version": 1, "mappings": [
        entry("m1", "ayni", "ornek-a"), entry("m2", "farkli", "ornek-b"), entry("m3", "ikili", "ornek-a"),
        entry("m4", "ikili", "ornek-b"), entry("m5", "sinifsiz", "ornek-a", test_class="s")]})
    records = parse_junit_bytes(_MAPPING_PROBE_XML, source_file="mapping-probe.xml").records
    _, resolutions = apply_scenario_mapping(records, mapping)
    got = [(r.status, r.scenario_id) for r in resolutions]
    expected = [("metadata_and_mapping", "ornek-a"), (RES_METADATA_MAPPING_CONFLICT, None),
                (RES_MAPPING_CONFLICT, None), ("identifier_missing", None)]
    try:
        parse_mapping({"scenario_mapping_version": 1, "mappings": [entry("m1", f"t?token={_CANARIES[1]}", "x")]})
        leaked = True
    except MappingError as exc:
        leaked = _CANARIES[1] in str(exc)
    ok = got == expected and not leaked
    _check(checks, "C5-mapping-safety", "security", CHECK_PASS if ok else CHECK_FAIL,
           "Eşleme öz-testi: uyuşan kaynaklar kabul ediliyor; metadata/eşleme çelişkisi ve çoklu eşleme seçilmiyor; "
           "sınıfsız kayıt suite adından eşlenmiyor; hassas tanımlayıcı hata mesajına yazılmadan reddediliyor" if ok
           else "Eşleme öz-testi beklenen sonucu vermedi")


def _mapping_checks(checks: list, mapping_path: str | Path, records: list) -> ScenarioMapping | None:
    try:
        mapping = load_mapping(mapping_path)
    except MappingError as exc:
        _check(checks, "A6-scenario-mapping", "mapping", CHECK_FAIL,
               "Eşleme dosyası yüklenemedi; kısmi eşleme ile analiz yapılmaz", issues=list(exc.issues))
        return None
    keys = {r.test_id for r in records if r.test_id}
    unused = sorted(e.mapping_id for e in mapping.entries if e.is_active and e.key not in keys)
    conflicts = mapping.conflicts
    _check(checks, "A6-scenario-mapping", "mapping", CHECK_WARN if conflicts else CHECK_PASS,
           "Eşleme dosyası (sürüm 1) geçerli" + ("; aynı test için farklı senaryolara giden ACTIVE eşlemeler var "
                                                 "(seçilmez)" if conflicts else ""),
           content_sha256=mapping.content_sha256, by_status=mapping.summary()["by_status"],
           conflicts=conflicts, active_entries_not_in_reports=unused)
    return mapping


def run_readiness(
    report_paths: Sequence[str | Path],
    *,
    expectations_path: str | Path | None = None,
    scope: str = SCOPE_REAL,
    mapping_path: str | Path | None = None,
) -> dict[str, Any]:
    """Önkoşul denetimi. Dönen belge değer içermez; dosyalar yalnızca adlarıyla anılır."""
    checks: list[dict[str, Any]] = []
    dataset_kind = DATASET_REAL if scope == SCOPE_REAL else DATASET_SYNTHETIC

    # A. Rapor sözleşmesi
    reports, errors, duplicates, given = parse_reports(report_paths, dataset_kind=dataset_kind)
    records = [r for report in reports for r in report.records]
    mapping_checks: list[dict[str, Any]] = []  # A6, A5'ten sonra listelenir
    mapping = _mapping_checks(mapping_checks, mapping_path, records) if mapping_path is not None else None
    resolved_records, resolutions = apply_scenario_mapping(records, mapping)
    sources = "testcase özelliği" + (" veya eşleme dosyası" if mapping is not None else "")
    if not reports:
        _check(checks, "A1-reports-readable", "report", CHECK_FAIL, "Hiçbir rapor okunamadı", given=given,
               rejected=[e.to_dict() for e in errors])
    else:
        _check(checks, "A1-reports-readable", "report", CHECK_WARN if errors else CHECK_PASS,
               f"{len(reports)} rapor okundu, {len(errors)} reddedildi, {len(duplicates)} tekrar",
               rejected=[e.to_dict() for e in errors])
    if not records:
        _check(checks, "A2-source-outcomes", "report", CHECK_FAIL, "Okunan raporlarda test kaydı yok")
    else:
        unknown = sum(1 for r in records if r.test_outcome == OUTCOME_UNKNOWN)
        _check(checks, "A2-source-outcomes", "report", CHECK_WARN if unknown else CHECK_PASS,
               f"{len(records)} kaydın {len(records) - unknown} tanesinde kaynak sonuç belirlenebildi",
               unknown=unknown)
        with_id = sum(1 for r in resolved_records if r.scenario_id)
        status = CHECK_PASS if with_id == len(records) else (CHECK_WARN if with_id else CHECK_FAIL)
        details: dict[str, Any] = {"with_scenario_id": with_id, "records": len(records)}
        if mapping is not None:
            details["by_resolution_status"] = dict(sorted(Counter(r.status for r in resolutions).items()))
        _check(checks, "A3-scenario-id-coverage", "report", status,
               f"{with_id}/{len(records)} kayıtta açık senaryo kimliği ({sources}; `{SCENARIO_ID_PROPERTY}`) var; "
               "kimliksiz kayıt beklentiyle eşleştirilemez", **details)
        bad_ids = Counter(w for r in records for w in r.warnings if w in ("scenario_id_invalid", "scenario_id_conflict"))
        if mapping is not None:
            bad_ids.update(r.status for r in resolutions if r.outcome in (OUTCOME_AMBIGUOUS, OUTCOME_CONFLICT)
                           and r.status not in ("metadata_invalid", "metadata_conflict"))
        _check(checks, "A4-scenario-id-quality", "report", CHECK_WARN if bad_ids else CHECK_PASS,
               "Geçersiz, belirsiz veya çelişkili senaryo kimliği var (hiçbiri seçilmedi)" if bad_ids
               else "Senaryo kimliği sorunu yok", **dict(bad_ids))
        degraded = Counter(r.data_quality_status for r in records if r.data_quality_status != QUALITY_VALID)
        _check(checks, "A5-parser-quality", "report", CHECK_WARN if degraded else CHECK_PASS,
               "Bazı kayıtlar eksik/çelişkili alanlarla ayrıştırıldı (uyarılarla)" if degraded
               else "Bütün kayıtlar uyarısız veya yalnızca bilgi uyarısıyla ayrıştırıldı", **dict(degraded))
    checks.extend(mapping_checks)

    # B. Beklenti sözleşmesi
    registry: ExpectationRegistry | None = None
    expectations, source, exp_ready = None, None, None
    if expectations_path is None:
        _check(checks, "B1-registry", "expectations", CHECK_FAIL,
               "Beklenti dosyası verilmedi; beklentiye dayalı analiz yapılamaz")
    else:
        try:
            expectations, source = load_expectations(expectations_path)
        except ExpectationsError as exc:
            _check(checks, "B1-registry", "expectations", CHECK_FAIL, "Beklenti dosyası yüklenemedi",
                   issues=list(exc.issues))
        else:
            if isinstance(expectations, ExpectationRegistry):
                registry = expectations
                _check(checks, "B1-registry", "expectations", CHECK_PASS,
                       "Beklenti sözleşmesi (sürüm 2) geçerli: şema, kimlik, sürüm ve kanıt yeterliliği denetlendi",
                       content_sha256=registry.content_sha256)
            else:
                _check(checks, "B1-registry", "expectations", CHECK_FAIL,
                       "Beklenti dosyası eski biçimde (sürüm 1): doğrulama durumu ve kanıt yok")
    if registry is not None:
        exp_ready = expectation_readiness(registry, scope)
        _check(checks, "B2-conflicts", "expectations", CHECK_WARN if exp_ready["conflicts"] else CHECK_PASS,
               "Aynı senaryo için birden fazla etkin beklenti var (eşleştirilmez)" if exp_ready["conflicts"]
               else "Çelişkili etkin beklenti yok", conflicts=exp_ready["conflicts"])
        verified = exp_ready["verified_in_scope"]
        status = CHECK_FAIL if verified == 0 else (CHECK_WARN if verified < exp_ready["in_scope_active"] else CHECK_PASS)
        _check(checks, "B3-verified-in-scope", "expectations", status,
               f"'{scope}' kapsamında {exp_ready['in_scope_active']} etkin beklentiden {verified} tanesi VERIFIED; "
               "doğrulanmamış beklenti kesin teşhis gerekçesi olamaz",
               by_status=exp_ready["in_scope_by_status"], out_of_scope_active=exp_ready["out_of_scope_active"])
        report_ids = {r.scenario_id for r in resolved_records if r.scenario_id}
        covered = {e.scenario_id for e in registry.expectations if e.is_active and e.scope == scope}
        hit = len(report_ids & covered)
        status = CHECK_PASS if report_ids and hit == len(report_ids) else (CHECK_WARN if hit else CHECK_FAIL)
        _check(checks, "B4-scenario-coverage", "expectations", status,
               f"Raporlardaki {len(report_ids)} senaryo kimliğinin {hit} tanesi için '{scope}' kapsamında etkin "
               "beklenti var", missing=sorted(report_ids - covered))
        with_issues = [c["expectation_id"] for c in exp_ready["checklist"] if c["evidence_issues"]]
        _check(checks, "B5-evidence", "expectations", CHECK_WARN if with_issues else CHECK_PASS,
               "Kanıt yeterliliği bulgusu olan beklentiler var (doğrulanmamış)" if with_issues
               else "Kapsamdaki beklentilerde kanıt bulgusu yok", expectations=with_issues)

    # C. Güvenlik
    _security_selftests(checks)
    if mapping_path is not None:
        _mapping_selftest(checks)

    # D. Analiz hattı (N3 → N7 → N8 → N4 → JSON)
    if records:
        document = build_junit_analysis_document(reports, errors, duplicates=duplicates, files_given=given,
                                                 expectations=expectations, expectations_source=source,
                                                 scenario_mapping=mapping, now=lambda: "readiness")
        summary = document["classification"]["summary"]
        consistent = sum(summary["by_classification"][c] for c in CLASSES) == len(records)
        if expectations is not None:
            consistent = consistent and sum(summary["expectation_matching"]["by_match_status"].values()) == len(records)
        try:
            json.dumps(document, allow_nan=False)
            serializable = True
        except (TypeError, ValueError):
            serializable = False
        resolution = summary["scenario_resolution"]
        consistent = (consistent and sum(resolution["by_status"].values()) == len(records)
                      and len(document["classification"]["scenario_trace"]) == len(records))
        ok = consistent and serializable
        _check(checks, "D1-pipeline", "pipeline", CHECK_PASS if ok else CHECK_FAIL,
               "Ayrıştırıcı → senaryo çözümlemesi → beklenti eşleştirme → sınıflandırıcı → JSON hattı çalıştı; sayaçlar "
               "tutarlı" if ok else "Analiz hattı tutarsız sonuç üretti",
               by_match_status=summary["expectation_matching"]["by_match_status"],
               by_classification={c: v for c, v in summary["by_classification"].items() if v},
               by_resolution_outcome=resolution["by_outcome"], by_decision_basis=resolution["by_decision_basis"],
               by_expectation_assessment=resolution["by_expectation_assessment"])
    else:
        _check(checks, "D1-pipeline", "pipeline", CHECK_FAIL, "Analiz hattı çalıştırılamadı: kayıt yok")

    statuses = {c["status"] for c in checks}
    status = BLOCKED if CHECK_FAIL in statuses else (READY_WITH_WARNINGS if CHECK_WARN in statuses else READY)
    return {
        "format": "hgs2-lab-readiness",
        "readiness_version": READINESS_VERSION,
        "scope": scope,
        "status": status,
        "statement": "Bu sonuç yalnızca tanımlı entegrasyon önkoşullarının durumunu gösterir; hedef sistemin doğru "
                     "çalıştığını veya beklentilerin gerçek dünyada doğru olduğunu göstermez.",
        "blocking": [c["id"] for c in checks if c["status"] == CHECK_FAIL],
        "warnings": [c["id"] for c in checks if c["status"] == CHECK_WARN],
        "checks": checks,
        "report_inventory": [inventory_junit_report(report) for report in reports],
        "file_errors": [e.to_dict() for e in errors],
        "expectations": exp_ready,
        "expectations_source": source,
        "scenario_mapping_source": mapping_source(mapping) if mapping is not None else None,
    }


