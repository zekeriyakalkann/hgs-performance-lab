"""N8: toplu JUnit analizi — N3 ayrıştırıcı → TestRecord → açık senaryo kimliği → N7 registry → N4 → JSON.

Ağ yok; fikstürler sentetik (`tests/fixtures/junit-n8/`, `tests/fixtures/expectations/junit-registry.json`).
"""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from hgs2_lab.classify import classify_record
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.expectations import ExpectationsError, parse_registry
from hgs2_lab.junit_analysis import (
    COUNTER_DEFINITIONS,
    attach_expectations,
    build_junit_analysis_document,
    parse_reports,
)
from hgs2_lab.junit_report import SCENARIO_ID_PROPERTY, parse_junit_bytes, parse_junit_report
from hgs2_lab.records import CLASSES, TestRecord
from hgs2_lab.result_analysis import load_expectations, parse_expectations

ROOT = Path(__file__).resolve().parents[1]
N8 = Path(__file__).parent / "fixtures" / "junit-n8"
JUNIT = Path(__file__).parent / "fixtures" / "junit"
REGISTRY = Path(__file__).parent / "fixtures" / "expectations" / "junit-registry.json"
BATCH_A, BATCH_B = N8 / "batch-a.xml", N8 / "batch-b.xml"
SECRETS = ("KART-SENTETIK-111", "FAKE-SUITE-PASS-901", "FAKE-CASE-PASS-902", "FAKE-TOKEN-903")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def analyse(paths, *, registry=True, dataset_kind="fixture"):
    expectations, source = load_expectations(REGISTRY) if registry else (None, None)
    reports, errors, duplicates, given = parse_reports(paths, dataset_kind=dataset_kind)
    return build_junit_analysis_document(reports, errors, duplicates=duplicates, files_given=given,
                                         expectations=expectations, expectations_source=source,
                                         now=lambda: "2026-10-26T00:00:00+00:00")["classification"]


def by_test(content):
    return {(r["source_file"], r["test_name"]): r for r in content["records"]}


# --- N3 ayrıştırıcı: açık senaryo kimliği ---
def case_xml(props):
    return (f'<testsuite name="s"><testcase name="t" classname="c" time="0.1">{props}</testcase></testsuite>').encode()


@pytest.mark.parametrize(
    "props, scenario, warning",
    [
        (f'<properties><property name="{SCENARIO_ID_PROPERTY}" value="kart-1"/></properties>', "kart-1", None),
        (f'<properties><property name="{SCENARIO_ID_PROPERTY}"> kart-1 </property></properties>', "kart-1", None),
        ("", None, None),
        ('<properties><property name="scenario" value="kart-1"/></properties>', None, None),  # başka ad okunmaz
        (f'<properties><property name="{SCENARIO_ID_PROPERTY}" value="../x y"/></properties>', None,
         "scenario_id_invalid"),
        (f'<properties><property name="{SCENARIO_ID_PROPERTY}" value=""/></properties>', None, "scenario_id_invalid"),
        (f'<properties><property name="{SCENARIO_ID_PROPERTY}" value="a"/>'
         f'<property name="{SCENARIO_ID_PROPERTY}" value="b"/></properties>', None, "scenario_id_conflict"),
        (f'<properties><property name="{SCENARIO_ID_PROPERTY}" value="a"/></properties>'
         f'<properties><property name="{SCENARIO_ID_PROPERTY}" value="a"/></properties>', "a", "scenario_id_repeated"),
    ],
)
def test_scenario_id_property(props, scenario, warning):
    [record] = parse_junit_bytes(case_xml(props), source_file="x.xml").records
    assert record.scenario_id == scenario
    assert (warning in record.warnings) if warning else not any(w.startswith("scenario_id") for w in record.warnings)
    assert record.test_outcome == "PASS"  # kimlik sorunu kaynak sonucunu değiştirmez


def test_suite_level_property_and_test_name_are_never_used_as_scenario_id():
    data = (f'<testsuite name="kart-pasif-cihaz"><properties><property name="{SCENARIO_ID_PROPERTY}" value="kart-1"/>'
            '</properties><testcase name="kart-pasif-cihaz" classname="kart-pasif-cihaz"/></testsuite>').encode()
    [record] = parse_junit_bytes(data, source_file="x.xml").records
    assert record.scenario_id is None


def test_fixture_parse_keeps_records_and_does_not_read_other_properties():
    report = parse_junit_report(BATCH_A, dataset_kind="fixture")
    assert len(report.records) == 12 and [s.observed["tests"] for s in report.suites] == [12, 0]
    records = {r.test_name: r for r in report.records}
    assert records["kartZamanAsimi"].scenario_id == "kart-zaman-asimi"  # öğe metninden
    assert records["numaraOkut"].scenario_id is None
    assert report.suites[0].ignored_sections["properties"] == 12  # sayılır; içeriği (kimlik dışında) okunmaz
    blob = json.dumps([r.to_dict() for r in report.records] + [report.to_dict()], ensure_ascii=False)
    for secret in SECRETS:
        assert secret not in blob


# --- eşleştirme ---
def test_attach_expectations_statuses_and_record_preservation():
    registry, _ = load_expectations(REGISTRY)
    records = list(parse_junit_report(BATCH_A, dataset_kind="fixture").records)
    attached, statuses = attach_expectations(records, registry)
    assert len(attached) == len(records)  # hiçbir kayıt kaybolmaz
    assert statuses == {"matched": 5, "no_scenario_id": 3, "not_found": 2, "deprecated_only": 1, "conflict": 1}
    for before, after in zip(records, attached):
        assert after.test_outcome == before.test_outcome and after.record_id == before.record_id
    by_name = {r.test_name: r for r in attached}
    assert by_name["cakisanBeklenti"].expected_result is None and "expectation_conflict" in by_name["cakisanBeklenti"].warnings
    assert by_name["eskiSurum"].expected_result is None
    assert by_name["kartPasifCihaz"].expected_result.provenance.expectation_id == "exp-j-kart-pasif"
    assert attach_expectations(records, None) == (records, {})


def test_test_outcome_only_expectation_is_valid_contract():
    registry = parse_registry({"expectations_version": 2, "expectations": [
        {"expectation_id": "e", "version": 1, "scenario_id": "s", "status": "DRAFT", "scope": "synthetic",
         "expected_test_outcome": "PASS"}]})
    assert registry.expectations[0].expected.expected_test_outcome == "PASS"
    with pytest.raises(ExpectationsError, match="en az bir beklenen alan"):
        parse_registry({"expectations_version": 2, "expectations": [
            {"expectation_id": "e", "version": 1, "scenario_id": "s", "status": "DRAFT", "scope": "synthetic"}]})


# --- A–J ---
def test_a_pass_with_verified_expectation():
    r = by_test(analyse([BATCH_A]))[("batch-a.xml", "kartPasifCihaz")]
    a = r["analysis"]
    assert (r["test_outcome"], a["classification"], a["rule_ids"]) == ("PASS", "PASS", ["J-PASS"])
    assert r["expected_result"]["provenance"]["verification_status"] == "VERIFIED"
    assert "test_outcome_matches_expectation" in a["warnings"]
    [cmp] = [e for e in a["evidence"] if e["field"] == "expectation_comparison"]
    assert cmp["value"] == {"test_outcome": "match", "http_status": "not_specified",
                            "business_outcome": "not_specified", "transport": "not_specified"}
    assert any("genel olarak hatasız" in text for text in a["limitations"])


def test_b_fail_with_verified_expectation_is_not_turned_into_pass():
    r = by_test(analyse([BATCH_A]))[("batch-a.xml", "kartGecerli")]
    a = r["analysis"]
    assert r["test_outcome"] == "FAIL" and a["classification"] == "APPLICATION_FAILURE"
    assert a["rule_ids"] == ["J-ASSERTION"] and a["confidence"] == "medium"
    assert "test_outcome_differs_from_expectation" in a["warnings"]
    assert any("dışlanamaz" in text for text in a["limitations"])


def test_c_records_without_scenario_id_are_kept_and_not_matched():
    records = by_test(analyse([BATCH_A]))
    for name in ("numaraOkut", "gecersizKimlik", "celisenKimlik"):
        r = records[("batch-a.xml", name)]
        assert r["scenario_id"] is None and r["expected_result"] is None
        assert "expectation_no_scenario_id" in r["analysis"]["warnings"]
        assert r["analysis"]["classification"] == "PASS"  # kaynak sonucuna göre analiz sürer
    assert "scenario_id_invalid" in records[("batch-a.xml", "gecersizKimlik")]["analysis"]["warnings"]
    assert records[("batch-a.xml", "celisenKimlik")]["analysis"]["requires_review"] is True


def test_d_draft_expectation_is_not_used_for_diagnosis():
    records = by_test(analyse([BATCH_A]))
    draft = records[("batch-a.xml", "numaraTaslak")]["analysis"]
    assert draft["classification"] == "PASS" and draft["rule_ids"] == ["J-PASS"]  # karar kaynak sonuçtan
    assert "expectation_unverified" in draft["warnings"]
    timeout = records[("batch-a.xml", "kartZamanAsimi")]["analysis"]
    assert (timeout["classification"], timeout["rule_ids"]) == ("TIMEOUT", ["J-TIMEOUT-TYPE"])
    assert "expectation_unverified" in timeout["warnings"]


def test_e_conflicting_expectations_are_not_resolved():
    r = by_test(analyse([BATCH_A]))[("batch-a.xml", "cakisanBeklenti")]
    assert r["expected_result"] is None and r["analysis"]["requires_review"] is True
    assert "expectation_conflict" in r["analysis"]["warnings"]


def test_f_broken_reports_do_not_stop_the_batch():
    content = analyse([JUNIT / "malformed.xml", BATCH_A, JUNIT / "empty.xml", JUNIT / "yok.xml", JUNIT / "xxe.xml"])
    assert content["summary"]["files_parsed"] == 1 and content["summary"]["files_rejected"] == 4
    assert [(e["source_file"], e["code"]) for e in content["file_errors"]] == [
        ("malformed.xml", "malformed_xml"), ("empty.xml", "empty"), ("yok.xml", "not_found"),
        ("xxe.xml", "unsafe_xml")]
    assert content["summary"]["records"] == 12


def test_g_counters_are_consistent_with_records(tmp_path):
    copy = tmp_path / "batch-a-kopya.xml"
    shutil.copyfile(BATCH_A, copy)
    content = analyse([BATCH_A, BATCH_B, copy, JUNIT / "malformed.xml"])
    s, records = content["summary"], content["records"]
    assert s["records"] == len(records) == 14
    assert (s["files_given"], s["files_parsed"], s["files_rejected"], s["files_duplicate"]) == (4, 2, 1, 1)
    assert s["files_given"] == s["files_parsed"] + s["files_rejected"] + s["files_duplicate"]
    assert content["duplicate_reports"] == [{"source_file": "batch-a-kopya.xml", "duplicate_of": "batch-a.xml",
                                             "source_sha256": hashlib.sha256(BATCH_A.read_bytes()).hexdigest()}]
    assert s["suites"] == 3  # batch-a: 2 suite (biri boş), batch-b: 1
    assert sum(s["by_classification"].values()) == len(records) and set(s["by_classification"]) == set(CLASSES)
    for cls in CLASSES:
        assert s["by_classification"][cls] == sum(r["analysis"]["classification"] == cls for r in records)
    assert s["by_test_outcome"] == {"ERROR": 1, "FAIL": 2, "PASS": 10, "SKIPPED": 1}
    assert s["requires_review"] == sum(r["analysis"]["requires_review"] for r in records)
    m = s["expectation_matching"]
    assert m["records_with_scenario_id"] + m["records_without_scenario_id"] == len(records)
    assert m["records_with_scenario_id"] == sum(1 for r in records if r["scenario_id"])
    assert sum(m["by_match_status"].values()) == len(records)
    assert m["by_match_status"] == {"conflict": 1, "deprecated_only": 1, "matched": 6, "no_scenario_id": 4,
                                    "not_found": 2}
    assert sum(m["matched_by_verification_status"].values()) == m["by_match_status"]["matched"]
    assert m["matched_by_verification_status"] == {"DRAFT": 2, "VERIFIED": 4}
    assert sum(s["data_quality"]["by_status"].values()) == len(records)
    assert s["data_quality"]["records_with_warnings"] == sum(1 for r in records if r["warnings"])
    [dup] = s["possible_duplicate_tests"]
    assert dup["test_id"] == "com.example.lab.KartTests#kartPasifCihaz" and dup["occurrences"] == 2
    assert dup["source_files"] == ["batch-a.xml", "batch-b.xml"]  # birleştirilmez: iki kayıt da durur
    assert set(s["counter_definitions"]) == set(COUNTER_DEFINITIONS)
    inconclusive = s["by_classification"]["INCONCLUSIVE"]
    assert s["by_classification"]["PASS"] + inconclusive <= len(records)  # INCONCLUSIVE PASS'a eklenmez


def test_h_sensitive_values_never_reach_outputs(tmp_path, capsys):
    out = tmp_path / "o.json"
    assert main(["junit", "classify", "--report", str(BATCH_A), "--report", str(BATCH_B), "--expectations",
                 str(REGISTRY), "--dataset-kind", "fixture", "--output", str(out)]) == EXIT_OK
    captured = capsys.readouterr()
    blob = out.read_text(encoding="utf-8") + captured.out + captured.err
    for secret in SECRETS:
        assert secret not in blob
    hassas = by_test(json.loads(out.read_text(encoding="utf-8"))["classification"])[("batch-a.xml", "hassasMesaj")]
    assert "REDDEDILDI" in hassas["error_message"] and "***REDACTED***" in hassas["error_message"]
    assert str(N8) not in out.read_text(encoding="utf-8")


def test_i_legacy_schema_1_records_and_v1_expectations():
    legacy = {"record_id": "r-old", "source_type": "junit_xml", "dataset_kind": "fixture", "test_outcome": "FAIL",
              "scenario_id": "kart", "expected_result": {"status_codes": [200], "business_outcomes": ["OK"],
                                                         "description": None}}
    record = TestRecord.from_dict(legacy)  # kayıt şeması 1 biçimindeki expected_result
    c = classify_record(record)
    assert record.expected_result.provenance is None and c.classification == "APPLICATION_FAILURE"
    assert "expectation_not_observable_in_junit" in c.warnings
    v1 = parse_expectations({"expectations_version": 1, "scenarios": {"kart-pasif-cihaz": {"status_codes": [200]}}})
    attached, statuses = attach_expectations(list(parse_junit_report(BATCH_B).records), v1)
    assert statuses == {"matched": 1, "no_scenario_id": 1}
    c = classify_record(attached[0])
    assert "expectation_verification_unspecified" in c.warnings and c.classification == "PASS"


def test_j_invalid_or_missing_registry_stops_without_output(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["expectations"][0]["status"] = "VERIFIED"
    data["expectations"][0]["evidence_ids"] = []  # VERIFIED kanıtsız: gerekçelendirilemez
    bad.write_text(json.dumps(data), encoding="utf-8")
    for registry in (bad, tmp_path / "yok.json"):
        out = tmp_path / "o.json"
        assert main(["junit", "classify", "--report", str(BATCH_A), "--expectations", str(registry),
                     "--output", str(out)]) == EXIT_ERROR
        assert not out.exists()
        err = capsys.readouterr().err
        assert "Beklenti dosyası kullanılamadı" in err and str(tmp_path) not in err


# --- beklentisiz analiz, kapsam, CLI ---
def test_without_registry_analysis_is_explicitly_expectation_free():
    content = analyse([BATCH_A], registry=False)
    m = content["summary"]["expectation_matching"]
    assert m["requested"] is False and m["by_match_status"] == {} and m["records_with_scenario_id"] == 9
    assert any("beklentisiz analiz" in note for note in content["notes"])
    assert all(not any(w.startswith("expectation_") for w in r["warnings"]) for r in content["records"])
    assert content["expectations"] is None


def test_scope_mismatch_is_flagged_for_real_or_unknown_records():
    for kind in ("real", "unknown"):
        r = by_test(analyse([BATCH_A], dataset_kind=kind))[("batch-a.xml", "kartPasifCihaz")]
        assert "expectation_scope_mismatch" in r["analysis"]["warnings"] and r["test_outcome"] == "PASS"


def test_not_observable_expectation_fields_are_reported():
    a = by_test(analyse([BATCH_A]))[("batch-a.xml", "httpBeklentisi")]["analysis"]
    assert "expectation_not_observable_in_junit" in a["warnings"]
    [cmp] = [e["value"] for e in a["evidence"] if e["field"] == "expectation_comparison"]
    assert cmp["http_status"] == "not_observable" and cmp["business_outcome"] == "not_observable"


def test_document_is_deterministic():
    assert analyse([BATCH_A, BATCH_B]) == analyse([BATCH_A, BATCH_B])


def test_cli_batch_outputs_and_no_overwrite(tmp_path, capsys):
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in N8.iterdir()}
    out = tmp_path / "batch.json"
    args = ["junit", "classify", "--report", str(BATCH_A), "--report", str(BATCH_B), "--report", str(BATCH_A),
            "--report", str(JUNIT / "malformed.xml"), "--expectations", str(REGISTRY), "--dataset-kind", "fixture",
            "--output", str(out)]
    assert main(args) == EXIT_ERROR  # yazıldı ama bir rapor reddedildi
    captured = capsys.readouterr()
    assert "eşleşme: conflict=1" in captured.out and "malformed.xml: malformed_xml" in captured.err
    assert "yeniden işlenmedi" in captured.err and "possible_duplicate_tests" in captured.err
    assert "cakisan" in captured.err
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["classification"]["expectations"]["registry"]["registry_id"] == "lab-junit-n8"
    assert main(args) == EXIT_STORAGE_ERROR  # üzerine yazılmaz
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in N8.iterdir()} == before


def test_cli_without_expectations_keeps_previous_contract(tmp_path, capsys):
    out = tmp_path / "plain.json"
    assert main(["junit", "classify", "--report", str(JUNIT / "failure.xml"), "--output", str(out)]) == EXIT_OK
    assert "beklenti dosyası verilmedi" in capsys.readouterr().out
    summary = json.loads(out.read_text(encoding="utf-8"))["classification"]["summary"]
    assert summary["files_parsed"] == 1 and summary["by_classification"]["APPLICATION_FAILURE"] == 1


def test_junit_analysis_module_does_not_import_network_code():
    code =("import sys; import hgs2_lab.junit_analysis; bad = sorted(m for m in ('requests', 'urllib3', 'socket', "
            "'http.client', 'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.robust_z', "
            "'hgs2_lab.detection', 'hgs2_lab.telemetry') if m in sys.modules); print(bad)")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                          check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"
