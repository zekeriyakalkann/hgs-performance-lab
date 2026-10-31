"""N9: gerçek entegrasyon hazırlık denetimi — rapor envanteri, beklenti hazırlığı, önkoşullar, CLI (ağ yok).

Bütün girdiler sentetiktir; hiçbir test hedef sisteme, veritabanına veya ağa erişmez (soketler engelli).
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from hgs2_lab import readiness
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.expectations import load_registry
from hgs2_lab.junit_report import parse_junit_bytes, parse_junit_report
from hgs2_lab.readiness import (
    BLOCKED,
    READY,
    READY_WITH_WARNINGS,
    expectation_readiness,
    inventory_junit_report,
    run_readiness,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
READY_XML, READY_REG = FIX / "readiness" / "ready.xml", FIX / "readiness" / "ready-registry.json"
BATCH_A, JUNIT_REG = FIX / "junit-n8" / "batch-a.xml", FIX / "expectations" / "junit-registry.json"
SECRETS = ("KART-SENTETIK-111", "FAKE-SUITE-PASS-901", "FAKE-CASE-PASS-902", "FAKE-TOKEN-903", "FAKE-PROP-PASS-999",
           "FAKE-SYSOUT-LINE", "FAKE-DB-PASS-777")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def statuses(document):
    return {c["id"]: c["status"] for c in document["checks"]}


# --- rapor envanteri ---
def test_inventory_of_all_pass_report_with_withheld_sections():
    inv = inventory_junit_report(parse_junit_report(FIX / "junit" / "all-pass.xml"))
    f = inv["fields"]
    assert (inv["records"], inv["suites"], inv["by_test_outcome"]) == (2, 1, {"PASS": 2})
    assert f["test_name"]["status"] == f["test_class"]["status"] == f["duration"]["status"] == "available"
    assert f["error_type"]["status"] == f["stack_trace"]["status"] == "not_applicable"
    assert f["properties"]["status"] == "withheld_for_security"
    assert f["system_out"]["status"] == f["system_err"]["status"] == "present_not_parsed"
    assert f["scenario_id"]["status"] == "missing"
    for name in ("expected_result", "observed_http_status", "observed_business_outcome"):
        assert f[name]["status"] == "not_in_format"
    assert "FAKE" not in json.dumps(inv)  # değer yok, yalnızca durum ve sayılar


def test_inventory_partial_and_error_fields():
    report = parse_junit_report(FIX / "junit" / "optional-missing.xml")
    f = inventory_junit_report(report)["fields"]
    assert f["duration"]["status"] == "partial" and f["duration"]["records_with_value"] == 2
    assert f["test_name"]["status"] == "partial"
    assert f["error_message"]["status"] == "missing"  # FAIL kaydında message özniteliği yok
    assert f["error_type"]["status"] == "available"  # iz metninden
    assert f["system_out"]["status"] == "missing" and f["properties"]["status"] == "missing"
    f = inventory_junit_report(parse_junit_report(BATCH_A))["fields"]
    assert f["scenario_id"]["status"] == "partial" and f["scenario_id"]["records_with_value"] == 9
    assert "geçersiz 1, çelişkili 1" in f["scenario_id"]["note"]


def test_inventory_of_empty_suite():
    inv = inventory_junit_report(parse_junit_report(FIX / "junit" / "empty-suite.xml"))
    assert inv["records"] == 0 and inv["fields"]["test_name"]["status"] == "not_applicable"


# --- beklenti hazırlığı (N7 bulgularının gerçek-kapsam özeti) ---
def test_expectation_readiness_real_scope_has_no_verified_expectations():
    real = expectation_readiness(load_registry(FIX / "expectations" / "hgs2-draft-example.json"), "real")
    assert (real["in_scope_active"], real["verified_in_scope"], real["in_scope_by_status"]) == (1, 0, {"DRAFT": 1})
    [item] = real["checklist"]
    assert item["expectation_id"] == "hgs2-kart-pasif-cihaz" and item["version"] == 1
    assert item["behaviour_defined"] == ["expected_http_status", "expected_business_outcome"]
    assert item["unspecified_fields"] == ["expected_transport", "expected_test_outcome"]
    assert "non_verifying_source:ev-hgs2-authcontroller" in item["evidence_issues"]
    assert "evidence_unreviewed" in item["verification_blockers"] and not item["conflicting"]


def test_expectation_readiness_synthetic_scope_counts_conflicts_and_deprecated():
    ready = expectation_readiness(load_registry(JUNIT_REG), "synthetic")
    assert ready["deprecated"] == 1 and ready["in_scope_active"] == 7 and ready["verified_in_scope"] == 4
    assert ready["conflicts"] == {"cakisan": ["exp-j-cakisan-a", "exp-j-cakisan-b"]}
    assert {c["expectation_id"] for c in ready["checklist"] if c["conflicting"]} == {"exp-j-cakisan-a",
                                                                                     "exp-j-cakisan-b"}
    assert expectation_readiness(load_registry(JUNIT_REG), "real")["in_scope_active"] == 0


# --- önkoşul denetimi ---
def test_all_prerequisites_met_is_ready():
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic")
    assert doc["status"] == READY and doc["blocking"] == [] and doc["warnings"] == []
    assert set(statuses(doc)) == {"A1-reports-readable", "A2-source-outcomes", "A3-scenario-id-coverage",
                                  "A4-scenario-id-quality", "A5-parser-quality", "B1-registry", "B2-conflicts",
                                  "B3-verified-in-scope", "B4-scenario-coverage", "B5-evidence", "C1-masking",
                                  "C2-xml-safety", "C3-metadata-withheld", "C4-offline", "D1-pipeline"}
    assert "doğru çalıştığını" in doc["statement"]


def test_warnings_without_blockers():
    doc = run_readiness([BATCH_A], expectations_path=JUNIT_REG, scope="synthetic")
    assert doc["status"] == READY_WITH_WARNINGS and doc["blocking"] == []
    s = statuses(doc)
    assert s["A3-scenario-id-coverage"] == s["A4-scenario-id-quality"] == s["B2-conflicts"] == "warn"
    assert s["B3-verified-in-scope"] == "warn" and s["B4-scenario-coverage"] == "warn"


def test_real_scope_without_verified_expectations_is_blocked():
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="real")
    assert doc["status"] == BLOCKED
    assert {"B3-verified-in-scope", "B4-scenario-coverage"} <= set(doc["blocking"])


@pytest.mark.parametrize("expectations", [None, "yok.json"])
def test_missing_registry_blocks(expectations, tmp_path):
    path = None if expectations is None else tmp_path / expectations
    doc = run_readiness([READY_XML], expectations_path=path, scope="synthetic")
    assert doc["status"] == BLOCKED and statuses(doc)["B1-registry"] == "fail"
    assert str(tmp_path) not in json.dumps(doc)


def test_invalid_and_legacy_registry_block(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"expectations_version": 2, "expectations": [{"expectation_id": "x"}]}', encoding="utf-8")
    doc = run_readiness([READY_XML], expectations_path=bad, scope="synthetic")
    assert statuses(doc)["B1-registry"] == "fail" and doc["status"] == BLOCKED
    assert any("eksik zorunlu" in i for c in doc["checks"] if c["id"] == "B1-registry" for i in c["details"]["issues"])
    v1 = tmp_path / "v1.json"
    v1.write_text('{"expectations_version": 1, "scenarios": {"a": {"status_codes": [200]}}}', encoding="utf-8")
    assert statuses(run_readiness([READY_XML], expectations_path=v1, scope="synthetic"))["B1-registry"] == "fail"


def test_insufficient_report_metadata_blocks():
    doc = run_readiness([FIX / "junit" / "all-pass.xml"], expectations_path=READY_REG, scope="synthetic")
    s = statuses(doc)
    assert s["A3-scenario-id-coverage"] == "fail" and s["B4-scenario-coverage"] == "fail" and doc["status"] == BLOCKED


def test_unreadable_or_empty_reports_block():
    doc = run_readiness([FIX / "junit" / "malformed.xml", FIX / "junit" / "yok.xml"], expectations_path=READY_REG,
                        scope="synthetic")
    s = statuses(doc)
    assert s["A1-reports-readable"] == s["A2-source-outcomes"] == s["D1-pipeline"] == "fail"
    assert [e["code"] for e in doc["file_errors"]] == ["malformed_xml", "not_found"]
    empty = run_readiness([FIX / "junit" / "empty-suite.xml"], expectations_path=READY_REG, scope="synthetic")
    assert statuses(empty)["A2-source-outcomes"] == "fail"
    partial = run_readiness([READY_XML, FIX / "junit" / "malformed.xml"], expectations_path=READY_REG,
                            scope="synthetic")
    assert statuses(partial)["A1-reports-readable"] == "warn" and partial["status"] == READY_WITH_WARNINGS


def test_security_selftests_pass_and_detect_failures(monkeypatch):
    doc = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic")
    s = statuses(doc)
    assert s["C1-masking"] == s["C2-xml-safety"] == s["C3-metadata-withheld"] == s["C4-offline"] == "pass"
    monkeypatch.setattr(readiness, "sanitize_text", lambda text: text)  # maskeleme devre dışı → yakalanmalı
    broken = run_readiness([READY_XML], expectations_path=READY_REG, scope="synthetic")
    assert statuses(broken)["C1-masking"] == "fail" and broken["status"] == BLOCKED


def test_readiness_document_contains_no_sensitive_values():
    reports = [BATCH_A, FIX / "junit" / "all-pass.xml", FIX / "junit" / "sensitive.xml", FIX / "junit" / "error-context.xml"]
    blob = json.dumps(run_readiness(reports, expectations_path=JUNIT_REG, scope="synthetic"), ensure_ascii=False)
    for secret in SECRETS:
        assert secret not in blob
    assert "CANARY" not in blob  # öz-test değerleri de rapora yazılmaz
    assert str(FIX) not in blob


def test_scenario_id_contract_is_not_derived_from_names():
    data = (b'<testsuite name="hazir-kart-pasif"><testcase name="hazir-kart-pasif" classname="hazir-kart-pasif"/>'
            b'</testsuite>')
    assert parse_junit_bytes(data, source_file="x.xml").records[0].scenario_id is None


# --- CLI ---
def test_cli_ready_and_output_without_overwrite(tmp_path, capsys):
    out = tmp_path / "hazirlik.json"
    args = ["readiness", "check", "--report", str(READY_XML), "--expectations", str(READY_REG), "--scope", "synthetic",
            "--output", str(out)]
    assert main(args) == EXIT_OK
    assert "READY" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == READY
    assert main(args) == EXIT_STORAGE_ERROR


def test_cli_blocked_exit_code_and_default_real_scope(capsys):
    assert main(["readiness", "check", "--report", str(READY_XML), "--expectations", str(READY_REG)]) == EXIT_ERROR
    out = capsys.readouterr().out
    assert "Hazırlık (real kapsamı): BLOCKED" in out and "[fail]" in out


def test_cli_output_contains_no_sensitive_values(capsys):
    main(["readiness", "check", "--report", str(BATCH_A), "--report", str(FIX / "junit" / "sensitive.xml"),
          "--expectations", str(JUNIT_REG), "--scope", "synthetic"])
    captured = capsys.readouterr()
    for secret in SECRETS:
        assert secret not in captured.out + captured.err


def test_readiness_module_does_not_import_network_code():
    code = ("import sys; import hgs2_lab.readiness, hgs2_lab.ingestion; bad = sorted(m for m in ('requests', "
            "'urllib3', 'socket', 'http.client', 'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.robust_z', "
            "'hgs2_lab.detection', 'hgs2_lab.telemetry') if m in sys.modules); print(bad)")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                          check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"
