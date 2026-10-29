"""N10 uçtan uca kabul: JUnit raporu → N3 → TestRecord → senaryo çözümlemesi → N7 registry → N4 → JSON → readiness.

Bütün girdiler sentetiktir; hiçbir test gerçek HGS2'ye, veritabanına veya ağa erişmez (soketler engelli).
"""

import json
import os
import random
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from hgs2_lab import readiness
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.junit_analysis import build_junit_analysis_document, parse_reports
from hgs2_lab.readiness import BLOCKED, READY, READY_WITH_WARNINGS, run_readiness
from hgs2_lab.records import CLASSES
from hgs2_lab.result_analysis import load_expectations
from hgs2_lab.scenario_mapping import load_mapping

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
MAP_DIR = FIX / "scenario-mapping"
REPORT, MAPPING, REGISTRY = MAP_DIR / "n10-report.xml", MAP_DIR / "n10-mapping.json", MAP_DIR / "n10-registry.json"
UNLABELED, READY_MAP = MAP_DIR / "ready-unlabeled.xml", MAP_DIR / "ready-mapping.json"
READY_XML, READY_REG = FIX / "readiness" / "ready.xml", FIX / "readiness" / "ready-registry.json"
BATCH_A = FIX / "junit-n8" / "batch-a.xml"
SECRETS = ("KART-SENTETIK-111", "OGR-SENTETIK-222", "FAKE-PASS-555", "FAKE-TOKEN-903", "FAKE-SUITE-PASS-901",
           "FAKE-CASE-PASS-902")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def analyse(reports=(REPORT,), *, mapping=MAPPING, registry=REGISTRY, dataset_kind="synthetic"):
    parsed, errors, duplicates, given = parse_reports(reports, dataset_kind=dataset_kind)
    expectations, source = load_expectations(registry) if registry else (None, None)
    return build_junit_analysis_document(parsed, errors, duplicates=duplicates, files_given=given,
                                         expectations=expectations, expectations_source=source,
                                         scenario_mapping=load_mapping(mapping) if mapping else None,
                                         now=lambda: "2026-10-29T00:00:00+00:00")


def by_name(document):
    return {t["test_name"]: t for t in document["classification"]["scenario_trace"]}


def records_by_name(document):
    return {r["test_name"]: r for r in document["classification"]["records"]}


def statuses(document):
    return {c["id"]: c["status"] for c in document["checks"]}


# --- E. uçtan uca akış ---
def test_end_to_end_resolved_record_keeps_every_layer():
    document = analyse()
    content = document["classification"]
    assert content["summary"]["records"] == len(content["scenario_trace"]) == 17
    t = by_name(document)["yalnizEsleme"]
    # 1-2. rapor okundu ve kayıt oluşturuldu (kaynak referansı yalnızca dosya adı + SHA-256)
    assert t["source_file"] == "n10-report.xml" and len(t["source_sha256"]) == 64
    assert t["test_id"] == "com.example.lab.EslemeTests#yalnizEsleme" and t["source_test_outcome"] == "PASS"
    # 3. senaryo kimliği eşleme dosyasından belirlendi
    assert t["scenario"]["status"] == "mapping" and t["scenario"]["scenario_id"] == "esleme-dogrulanmis"
    assert t["scenario"]["sources"] == ["mapping_file"] and t["scenario"]["mapping_ids"] == ["map-yalniz"]
    # 4-5. beklenti bulundu; doğrulama durumu ve kapsam denetlendi
    e = t["expectation"]
    assert (e["match_status"], e["expectation_id"], e["version"], e["verification_status"], e["scope"],
            e["scope_compatible"]) == ("matched", "exp-n10-dogrulanmis", 2, "VERIFIED", "synthetic", True)
    assert t["decision_basis"] == "verified_expectation_in_scope"
    assert (t["outcome_vs_expectation"], t["expectation_assessment"]) == ("match", "consistent")
    # 6. N4 sonucu
    assert t["classification"]["classification"] == "PASS" and t["classification"]["rule_ids"] == ["J-PASS"]
    record = records_by_name(document)["yalnizEsleme"]
    assert record["scenario_id"] == "esleme-dogrulanmis" and "scenario_resolution:mapping" in record["warnings"]
    assert record["expected_result"]["provenance"]["expectation_id"] == "exp-n10-dogrulanmis"
    # 7. JSON
    json.dumps(document, allow_nan=False)
    assert content["scenario_mapping"]["file"] == "n10-mapping.json"
    assert content["scenario_mapping"]["mapping"]["mapping_set_id"] == "lab-esleme-n10"


def test_end_to_end_summary_counters_are_consistent():
    summary = analyse()["classification"]["summary"]
    resolution = summary["scenario_resolution"]
    assert resolution["mapping_requested"] is True
    assert sum(resolution["by_status"].values()) == sum(resolution["by_outcome"].values()) == summary["records"]
    assert resolution["by_outcome"] == {"ambiguous": 2, "conflict": 2, "not_found": 2, "resolved": 11}
    assert resolution["requires_review"] == 4
    assert resolution["by_expectation_assessment"] == {"consistent": 3, "inconsistent": 2, "undetermined": 12}
    assert sum(summary["expectation_matching"]["by_match_status"].values()) == summary["records"]
    assert summary["expectation_matching"]["records_with_scenario_id"] == 11
    assert sum(summary["by_classification"][c] for c in CLASSES) == summary["records"]
    for key in ("scenario_resolution.by_status", "scenario_resolution.by_decision_basis"):
        assert key in summary["counter_definitions"]


def test_end_to_end_conflicting_mapping_is_not_resolved_and_needs_review():
    t = by_name(analyse())
    for name, status in (("metaEslemeCelisiyor", "metadata_mapping_conflict"), ("ikiliEsleme", "mapping_conflict")):
        entry = t[name]
        assert (entry["scenario"]["status"], entry["scenario"]["outcome"], entry["scenario"]["scenario_id"]) == \
            (status, "conflict", None)
        # Her iki adayın da VERIFIED beklentisi var; hiçbiri seçilmedi
        assert entry["expectation"]["match_status"] == "no_scenario_id" and entry["expectation"]["expectation_id"] is None
        assert entry["decision_basis"] == "no_scenario_id" and entry["expectation_assessment"] == "undetermined"
        assert entry["requires_review"] and f"scenario_{status}" in entry["review_reasons"]
        assert entry["classification"]["requires_review"]  # N4 mevcut sözleşmesiyle (scenario_id_conflict)
        assert "scenario_id_conflict" in entry["classification"]["warnings"]
    assert t["metaEslemeCelisiyor"]["scenario"]["candidate_scenario_ids"] == ["celiski-esleme", "celiski-meta"]


def test_end_to_end_ambiguous_mapping_is_not_resolved():
    t = by_name(analyse())
    for name, status in (("sinifsiz", "identifier_missing"), ("gecersizMetadata", "metadata_invalid")):
        assert (t[name]["scenario"]["status"], t[name]["scenario"]["outcome"], t[name]["scenario"]["scenario_id"]) == \
            (status, "ambiguous", None)
        assert t[name]["requires_review"] and t[name]["expectation_assessment"] == "undetermined"
    # sınıfsız kaydın eşleme kaydı var ama suite adından tanımlayıcı türetilmedi
    assert t["sinifsiz"]["scenario"]["mapping_ids"] == []


def test_not_found_states_are_distinguished():
    t = by_name(analyse())
    assert t["eslemesiYok"]["scenario"]["status"] == "not_mapped"
    assert t["emekliEsleme"]["scenario"]["status"] == "deprecated_only"
    assert t["emekliEsleme"]["scenario"]["deprecated_mapping_ids"] == ["map-emekli"]
    assert not t["eslemesiYok"]["requires_review"] and t["eslemesiYok"]["classification"]["classification"] == "PASS"
    # Kimliği çözülen ama registry'de olmayan senaryo
    assert t["kayitsizSenaryo"]["expectation"]["match_status"] == "not_found"
    assert t["kayitsizSenaryo"]["decision_basis"] == "expectation_not_found"


def test_metadata_only_and_agreement_paths():
    t = by_name(analyse())
    assert t["yalnizMetadata"]["scenario"]["sources"] == ["testcase_property"]
    assert t["metaVeEslemeAyni"]["scenario"]["sources"] == ["testcase_property", "mapping_file"]
    assert t["metaVeEslemeAyni"]["expectation_assessment"] == "consistent"


def test_without_mapping_file_metadata_still_works_and_records_are_unchanged():
    with_trace = analyse(mapping=None)
    content = with_trace["classification"]
    assert content["scenario_mapping"] is None and content["summary"]["scenario_resolution"]["mapping_requested"] is False
    t = by_name(with_trace)
    assert t["metaVeEslemeAyni"]["scenario"]["status"] == "metadata"
    assert t["yalnizEsleme"]["scenario"]["status"] == "no_source"
    assert t["gecersizMetadata"]["scenario"]["status"] == "metadata_invalid"
    assert not any(w.startswith("scenario_resolution:") for r in content["records"] for w in r["warnings"])


# --- D. beklenti entegrasyonu ---
def test_verified_expectation_with_fail_source_is_inconsistent_and_never_pass():
    t = by_name(analyse())
    for name in ("eslemeBeklentiFail", "hassasMesaj"):
        assert t[name]["source_test_outcome"] == "FAIL"
        assert t[name]["classification"]["classification"] == "APPLICATION_FAILURE"
        assert (t[name]["outcome_vs_expectation"], t[name]["expectation_assessment"]) == ("differs", "inconsistent")
        assert "test_outcome_differs_from_expectation" in t[name]["classification"]["warnings"]
    assert records_by_name(analyse())["eslemeBeklentiFail"]["test_outcome"] == "FAIL"


def test_skipped_is_not_success_even_with_verified_expectation():
    t = by_name(analyse())["atlanan"]
    assert t["decision_basis"] == "verified_expectation_in_scope"
    assert t["classification"]["classification"] == "INCONCLUSIVE"
    assert (t["outcome_vs_expectation"], t["expectation_assessment"]) == ("differs", "undetermined")


@pytest.mark.parametrize("name, status", [("taslakBeklenti", "DRAFT"), ("incelenmisBeklenti", "REVIEWED")])
def test_draft_and_reviewed_expectations_are_not_decisive(name, status):
    t = by_name(analyse())[name]
    assert t["expectation"]["verification_status"] == status and t["decision_basis"] == "expectation_unverified"
    assert t["expectation_assessment"] == "undetermined"
    assert "expectation_unverified" in t["classification"]["warnings"]
    assert t["classification"]["classification"] == "PASS"  # kaynak sonucun kendisi; beklenti kararı değiştirmez


def test_verified_synthetic_expectation_is_not_used_for_real_or_unknown_records():
    real = by_name(analyse(dataset_kind="real"))["yalnizEsleme"]
    assert real["expectation"]["scope_compatible"] is False and real["decision_basis"] == "expectation_scope_mismatch"
    assert real["expectation_assessment"] == "undetermined"
    assert "expectation_scope_mismatch" in real["classification"]["warnings"]
    unknown = by_name(analyse(dataset_kind="unknown"))["yalnizEsleme"]
    assert unknown["expectation"]["scope_compatible"] is None
    assert unknown["decision_basis"] == "expectation_scope_unconfirmed"


def test_multiple_active_expectations_are_not_chosen():
    t = by_name(analyse())["cakisanBeklenti"]
    assert t["expectation"]["match_status"] == "conflict" and t["expectation"]["expectation_id"] is None
    assert t["expectation"]["candidate_ids"] == ["exp-n10-cakisan-a", "exp-n10-cakisan-b"]
    assert t["decision_basis"] == "expectation_conflict" and t["requires_review"]


def test_expectation_with_unobservable_fields_is_not_comparable():
    t = by_name(analyse())["httpBeklentisi"]
    assert t["decision_basis"] == "expectation_not_comparable" and t["expectation_assessment"] == "undetermined"
    assert t["outcome_vs_expectation"] is None
    assert "expectation_not_observable_in_junit" in t["classification"]["warnings"]


def test_no_expectations_given():
    t = by_name(analyse(registry=None))["yalnizEsleme"]
    assert t["expectation"]["match_status"] == "not_requested" and t["decision_basis"] == "no_expectations"


def test_registry_scenario_mismatch_is_not_found():
    t = by_name(analyse())["kayitsizSenaryo"]
    assert t["scenario"]["outcome"] == "resolved" and t["expectation"]["match_status"] == "not_found"


# --- determinizm ---
def test_repeated_analysis_is_identical():
    assert analyse()["content_sha256"] == analyse()["content_sha256"]


def test_file_order_and_mapping_order_do_not_change_per_record_results(tmp_path):
    data = json.loads(MAPPING.read_text(encoding="utf-8"))
    random.Random(3).shuffle(data["mappings"])
    shuffled = tmp_path / "karisik.json"
    shuffled.write_text(json.dumps(data), encoding="utf-8")
    first = analyse([REPORT, BATCH_A])
    second = analyse([BATCH_A, REPORT], mapping=shuffled)
    def per_record(doc):
        return {t["record_id"]: t for t in doc["classification"]["scenario_trace"]}

    assert per_record(first) == per_record(second)
    s1, s2 = first["classification"]["summary"], second["classification"]["summary"]
    for name in ("by_classification", "by_test_outcome", "scenario_resolution", "expectation_matching"):
        assert s1[name] == s2[name]
    assert first["classification"]["scenario_mapping"]["mapping"]["content_sha256"] == \
        second["classification"]["scenario_mapping"]["mapping"]["content_sha256"]


# --- readiness ---
def test_readiness_with_mapping_only_report_is_ready_in_synthetic_scope():
    without = run_readiness([UNLABELED], expectations_path=READY_REG, scope="synthetic")
    assert without["status"] == BLOCKED and statuses(without)["A3-scenario-id-coverage"] == "fail"
    doc = run_readiness([UNLABELED], expectations_path=READY_REG, scope="synthetic", mapping_path=READY_MAP)
    s = statuses(doc)
    assert doc["status"] == READY and doc["warnings"] == [] and doc["blocking"] == []
    assert s["A3-scenario-id-coverage"] == s["A6-scenario-mapping"] == s["C5-mapping-safety"] == "pass"
    assert s["B4-scenario-coverage"] == "pass"
    assert doc["scenario_mapping_source"]["file"] == "ready-mapping.json"
    assert "doğru çalıştığını" in doc["statement"]


def test_readiness_real_scope_stays_blocked_with_mapping():
    doc = run_readiness([UNLABELED], expectations_path=READY_REG, scope="real", mapping_path=READY_MAP)
    assert doc["status"] == BLOCKED and statuses(doc)["A3-scenario-id-coverage"] == "pass"
    assert {"B3-verified-in-scope", "B4-scenario-coverage"} <= set(doc["blocking"])


def test_readiness_without_mapping_keeps_n9_check_set():
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic")
    assert "A6-scenario-mapping" not in statuses(doc) and "C5-mapping-safety" not in statuses(doc)
    assert doc["scenario_mapping_source"] is None and doc["status"] == READY


def test_readiness_reports_metadata_and_mapping_agreement(tmp_path):
    agree = tmp_path / "ayni.json"
    agree.write_text(json.dumps({"scenario_mapping_version": 1, "mappings": [
        {"mapping_id": "m1", "test_class": "com.example.lab.HazirTests", "test_name": "kartPasifCihaz",
         "scenario_id": "hazir-kart-pasif", "status": "ACTIVE"}]}), encoding="utf-8")
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic", mapping_path=agree)
    assert doc["status"] == READY
    a3 = next(c for c in doc["checks"] if c["id"] == "A3-scenario-id-coverage")
    assert a3["details"]["by_resolution_status"] == {"metadata": 1, "metadata_and_mapping": 1}


def test_readiness_flags_conflicts_and_ambiguity():
    doc = run_readiness([REPORT], expectations_path=REGISTRY, scope="synthetic", mapping_path=MAPPING)
    s = statuses(doc)
    assert doc["status"] == READY_WITH_WARNINGS and doc["blocking"] == []
    assert s["A4-scenario-id-quality"] == s["A6-scenario-mapping"] == s["A3-scenario-id-coverage"] == "warn"
    a4 = next(c for c in doc["checks"] if c["id"] == "A4-scenario-id-quality")["details"]
    assert a4 == {"scenario_id_invalid": 1, "metadata_mapping_conflict": 1, "mapping_conflict": 1,
                  "identifier_missing": 1}
    a6 = next(c for c in doc["checks"] if c["id"] == "A6-scenario-mapping")["details"]
    assert a6["conflicts"] == {"com.example.lab.EslemeTests#ikiliEsleme": ["map-ikili-a", "map-ikili-b"]}
    # map-sinifsiz: rapordaki kaydın classname'i yok; tanımlayıcı suite adından türetilmediği için karşılıksız kalır
    assert a6["active_entries_not_in_reports"] == ["map-baska-rapor", "map-sinifsiz"]
    d1 = next(c for c in doc["checks"] if c["id"] == "D1-pipeline")
    assert d1["status"] == "pass" and d1["details"]["by_resolution_outcome"]["conflict"] == 2
    assert s["B2-conflicts"] == "warn"  # birden fazla etkin beklenti (N7)


@pytest.mark.parametrize("content", ["", "{bozuk", '{"scenario_mapping_version": 2, "mappings": []}',
                                     '{"scenario_mapping_version": 1, "mappings": [{"mapping_id": "x"}]}'])
def test_readiness_blocks_on_invalid_mapping_file(tmp_path, content):
    bad = tmp_path / "bozuk-esleme.json"
    bad.write_text(content, encoding="utf-8")
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic", mapping_path=bad)
    assert doc["status"] == BLOCKED and statuses(doc)["A6-scenario-mapping"] == "fail"
    assert "A6-scenario-mapping" in doc["blocking"] and str(tmp_path) not in json.dumps(doc)


def test_readiness_missing_mapping_file_blocks(tmp_path):
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic", mapping_path=tmp_path / "yok.json")
    assert statuses(doc)["A6-scenario-mapping"] == "fail" and str(tmp_path) not in json.dumps(doc)


def test_readiness_only_draft_or_reviewed_expectations_block(tmp_path):
    for status, evidence in (("DRAFT", []), ("REVIEWED", ["ev"])):
        registry = tmp_path / f"{status}.json"
        registry.write_text(json.dumps({"expectations_version": 2, "evidence": [
            {"evidence_id": "ev", "source_type": "manual_review", "source_ref": "N10-X", "supports": ["test_outcome"]}],
            "expectations": [{"expectation_id": f"e-{i}", "version": 1, "scenario_id": sid, "status": status,
                              "scope": "synthetic", "expected_test_outcome": "PASS", "evidence_ids": evidence}
                             for i, sid in enumerate(("hazir-kart-pasif", "hazir-numara-gecerli"))]}),
            encoding="utf-8")
        doc = run_readiness([UNLABELED], expectations_path=registry, scope="synthetic", mapping_path=READY_MAP)
        assert doc["status"] == BLOCKED and statuses(doc)["B3-verified-in-scope"] == "fail"
        assert doc["expectations"]["in_scope_by_status"] == {status: 2}
        d1 = next(c for c in doc["checks"] if c["id"] == "D1-pipeline")
        assert d1["details"]["by_decision_basis"] == {"expectation_unverified": 2}


def test_readiness_mapping_selftest_detects_broken_resolution(monkeypatch):
    from hgs2_lab import scenario_mapping

    original = scenario_mapping.resolve_scenario

    def prefer_metadata(record, mapping=None):  # sessiz öncelik kuralı: yakalanmalı
        resolution = original(record, mapping)
        if resolution.status == "metadata_mapping_conflict":
            return scenario_mapping.ScenarioResolution("metadata", record.scenario_id, resolution.test_key,
                                                       record.scenario_id, mapping_requested=True)
        return resolution

    monkeypatch.setattr(scenario_mapping, "resolve_scenario", prefer_metadata)
    doc = run_readiness([UNLABELED], expectations_path=READY_REG, scope="synthetic", mapping_path=READY_MAP)
    assert statuses(doc)["C5-mapping-safety"] == "fail" and doc["status"] == BLOCKED


# --- CLI ---
def test_cli_junit_classify_with_mapping(tmp_path, capsys):
    out = tmp_path / "analiz.json"
    code = main(["junit", "classify", "--report", str(REPORT), "--scenario-map", str(MAPPING), "--expectations",
                 str(REGISTRY), "--dataset-kind", "synthetic", "--output", str(out)])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "senaryo çözümlemesi:" in captured.out and "mapping=9" in captured.out
    assert "farklı senaryolara eşlenmiş testler (seçilmedi): 1" in captured.err
    document = json.loads(out.read_text(encoding="utf-8"))
    assert len(document["classification"]["scenario_trace"]) == 17
    assert main(["junit", "classify", "--report", str(REPORT), "--scenario-map", str(MAPPING), "--output",
                 str(out)]) == EXIT_STORAGE_ERROR


def test_cli_invalid_mapping_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "bozuk.json"
    bad.write_text('{"scenario_mapping_version": 1, "mappings": [{"mapping_id": "m1", "test_class": "c", '
                   '"test_name": "password=FAKE-PASS-555", "scenario_id": "s", "status": "ACTIVE"}]}', encoding="utf-8")
    out = tmp_path / "analiz.json"
    assert main(["junit", "classify", "--report", str(REPORT), "--scenario-map", str(bad), "--output",
                 str(out)]) == EXIT_ERROR
    captured = capsys.readouterr()
    assert not out.exists() and "Eşleme dosyası kullanılamadı" in captured.err
    assert "FAKE-PASS-555" not in captured.out + captured.err and str(tmp_path) not in captured.err


def test_cli_scenario_map_validate(tmp_path, capsys):
    assert main(["scenario-map", "validate", "--file", str(MAPPING)]) == EXIT_OK
    captured = capsys.readouterr()
    assert "Geçerli: n10-mapping.json" in captured.out and "ACTIVE=16, DEPRECATED=1" in captured.out
    assert "ikiliEsleme' farklı senaryolara eşlenmiş: map-ikili-a, map-ikili-b" in captured.err
    bad = tmp_path / "v2.json"
    bad.write_text('{"scenario_mapping_version": 2, "mappings": []}', encoding="utf-8")
    assert main(["scenario-map", "validate", "--file", str(bad)]) == EXIT_ERROR
    captured = capsys.readouterr()
    assert "Desteklenmeyen eşleme sürümü" in captured.err and str(tmp_path) not in captured.err


def test_cli_readiness_with_mapping(capsys):
    code = main(["readiness", "check", "--report", str(UNLABELED), "--expectations", str(READY_REG), "--scope",
                 "synthetic", "--scenario-map", str(READY_MAP)])
    out = capsys.readouterr().out
    assert code == EXIT_OK and "READY" in out and "A6-scenario-mapping" in out and "C5-mapping-safety" in out
    assert main(["readiness", "check", "--report", str(UNLABELED), "--expectations", str(READY_REG),
                 "--scenario-map", str(READY_MAP)]) == EXIT_ERROR  # varsayılan gerçek kapsam: BLOCKED


# --- F. güvenlik ---
def test_no_sensitive_values_in_analysis_json_or_reasons():
    document = analyse()
    blob = json.dumps(document, ensure_ascii=False)
    for secret in SECRETS:
        assert secret not in blob
    assert str(FIX) not in blob and str(ROOT) not in blob
    assert "***REDACTED***" in json.dumps(records_by_name(document)["hassasMesaj"], ensure_ascii=False)


def test_no_sensitive_values_in_readiness_or_cli_output(tmp_path, capsys):
    doc = run_readiness([REPORT], expectations_path=REGISTRY, scope="synthetic", mapping_path=MAPPING)
    blob = json.dumps(doc, ensure_ascii=False)
    out = tmp_path / "hazirlik.json"
    main(["readiness", "check", "--report", str(REPORT), "--expectations", str(REGISTRY), "--scope", "synthetic",
          "--scenario-map", str(MAPPING), "--output", str(out)])
    main(["junit", "classify", "--report", str(REPORT), "--scenario-map", str(MAPPING), "--expectations",
          str(REGISTRY), "--output", str(tmp_path / "a.json")])
    captured = capsys.readouterr()
    for text in (blob, captured.out + captured.err, out.read_text(encoding="utf-8"),
                 (tmp_path / "a.json").read_text(encoding="utf-8")):
        for secret in SECRETS:
            assert secret not in text
        assert "CANARY" not in text and str(FIX) not in text


def test_mapping_error_messages_do_not_leak_values_or_paths(tmp_path):
    bad = tmp_path / "gizli.json"
    bad.write_text(json.dumps({"scenario_mapping_version": 1, "mappings": [
        {"mapping_id": "m1", "test_class": "c", "test_name": "t", "scenario_id": "ogrenciNo=OGR-SENTETIK-222",
         "status": "ACTIVE", "evidence_ref": "C:\\Users\\Sahte\\token=FAKE-TOKEN-903.md"}]}), encoding="utf-8")
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic", mapping_path=bad)
    blob = json.dumps(doc, ensure_ascii=False)
    assert "OGR-SENTETIK-222" not in blob and "FAKE-TOKEN-903" not in blob and "Sahte" not in blob
    assert str(tmp_path) not in blob


def test_mapping_module_does_not_import_network_code():
    code = ("import sys; import hgs2_lab.scenario_mapping, hgs2_lab.junit_analysis; bad = sorted(m for m in ("
            "'requests', 'urllib3', 'socket', 'http.client', 'hgs2_lab.http_transport', 'hgs2_lab.execution', "
            "'hgs2_lab.robust_z', 'hgs2_lab.detection', 'hgs2_lab.telemetry') if m in sys.modules); print(bad)")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                          check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"
