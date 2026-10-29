"""Uçtan uca çevrimdışı hat: JUnit fikstürü → junit_report → TestRecord → classify → JSON belge → `junit classify` CLI.

Her testte soket bağlantısı ve ad çözümlemesi engellenir; fikstürler sentetiktir.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from hgs2_lab.classify import DOCUMENT_FORMAT, build_junit_document
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.junit_report import parse_junit_reports
from hgs2_lab.records import CLASSES, DATASET_FIXTURE, TestRecord

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "junit"
SYNTHETIC_SECRETS = ("KART-SENTETIK-111", "OGR-SENTETIK-222", "PARMAK-SENTETIK-333", "FAKE-TOKEN-444",
                     "FAKE-PASS-555", "FAKE-COOKIE-666", "FAKE-DB-PASS-777", "FAKE-PROP-PASS-999",
                     "FAKE-SYSOUT-LINE", "FAKE-SYSERR-LINE", "FakeUser")
GOOD = ["all-pass.xml", "failure.xml", "error-context.xml", "skipped.xml", "multi-suite.xml", "sensitive.xml",
        "optional-missing.xml", "conflicting.xml", "empty-suite.xml"]
BAD = ["empty.xml", "malformed.xml", "xxe.xml", "not-junit.xml"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def fixed_now():
    return "2026-10-26T00:00:00+00:00"


def build(names):
    reports, errors = parse_junit_reports([FIXTURES / n for n in names], dataset_kind=DATASET_FIXTURE)
    return build_junit_document(reports, errors, now=fixed_now)


def test_end_to_end_document_from_fixtures():
    document = build(GOOD + BAD)
    assert document["format"] == DOCUMENT_FORMAT
    content = document["classification"]
    summary = content["summary"]
    assert summary["files_parsed"] == len(GOOD) and summary["files_rejected"] == len(BAD)
    assert sorted(e["source_file"] for e in content["file_errors"]) == sorted(BAD)
    assert summary["records"] == len(content["records"]) == 20
    assert set(summary["by_classification"]) == set(CLASSES) and sum(summary["by_classification"].values()) == 20
    assert summary["by_test_outcome"] == {"ERROR": 4, "FAIL": 5, "PASS": 9, "SKIPPED": 1, "UNKNOWN": 1}
    by_name = {(r["source_file"], r["test_name"]): r for r in content["records"]}
    expected = {
        ("all-pass.xml", "kartOkutOnaylanir"): ("PASS", "PASS"),
        ("failure.xml", "kartOkutGecerliKart"): ("FAIL", "APPLICATION_FAILURE"),
        ("error-context.xml", "contextLoads"): ("ERROR", "TEST_INFRASTRUCTURE_FAILURE"),
        ("skipped.xml", "cihazPasifIken"): ("SKIPPED", "INCONCLUSIVE"),
        ("multi-suite.xml", "uzakServisYavas"): ("ERROR", "TIMEOUT"),
        ("multi-suite.xml", "logYaz"): ("ERROR", "UNKNOWN"),
        ("multi-suite.xml", "logOku"): ("ERROR", "INCONCLUSIVE"),
        ("conflicting.xml", "hemFailureHemSkipped"): ("UNKNOWN", "INCONCLUSIVE"),
    }
    for key, (source, analysed) in expected.items():
        assert (by_name[key]["test_outcome"], by_name[key]["analysis"]["classification"]) == (source, analysed)
    for record in content["records"]:  # her kararın gerekçesi ve kuralı var; kayıt modeline geri yüklenebilir
        assert record["analysis"]["rule_ids"] and record["analysis"]["reason"]
        assert TestRecord.from_dict(record).to_dict() == record


def test_document_contains_no_sensitive_values_or_local_paths():
    text = json.dumps(build(GOOD + BAD), ensure_ascii=False)
    for secret in SYNTHETIC_SECRETS:
        assert secret not in text
    assert str(FIXTURES) not in text and str(ROOT) not in text


def test_document_is_deterministic():
    first, second = build(GOOD), build(GOOD)
    assert first == second
    assert first["content_sha256"] != build(GOOD[:-1])["content_sha256"]


def test_document_states_f5_separation_and_rule_based_nature():
    notes = " ".join(build(["all-pass.xml"])["classification"]["notes"])
    assert "F5" in notes and "olasılık değildir" in notes and "gerçek HGS2" in notes


def test_cli_writes_document_and_reports_rejected_files(tmp_path, capsys):
    out = tmp_path / "out" / "classification.json"
    args = ["junit", "classify", "--dataset-kind", "fixture", "--output", str(out)]
    for name in ("all-pass.xml", "sensitive.xml", "malformed.xml"):
        args += ["--report", str(FIXTURES / name)]
    assert main(args) == EXIT_ERROR  # belge yazıldı, ama bir rapor reddedildi
    captured = capsys.readouterr()
    assert "malformed.xml: malformed_xml" in captured.err
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["classification"]["summary"]["records"] == 4
    assert document["classification"]["records"][0]["dataset_kind"] == "fixture"
    for secret in SYNTHETIC_SECRETS:
        assert secret not in captured.out + captured.err + out.read_text(encoding="utf-8")


def test_cli_success_and_no_overwrite(tmp_path, capsys):
    out = tmp_path / "c.json"
    args = ["junit", "classify", "--report", str(FIXTURES / "failure.xml"), "--output", str(out)]
    assert main(args) == EXIT_OK
    assert "APPLICATION_FAILURE=1" in capsys.readouterr().out
    before = hashlib.sha256(out.read_bytes()).hexdigest()
    assert main(args) == EXIT_STORAGE_ERROR  # üzerine yazılmaz
    assert hashlib.sha256(out.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c.json"]  # geçici dosya kalmaz


def test_cli_default_dataset_kind_is_unknown_and_inputs_unchanged(tmp_path):
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURES.iterdir()}
    out = tmp_path / "c.json"
    assert main(["junit", "classify", "--report", str(FIXTURES / "all-pass.xml"), "--output", str(out)]) == EXIT_OK
    assert json.loads(out.read_text(encoding="utf-8"))["classification"]["records"][0]["dataset_kind"] == "unknown"
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURES.iterdir()} == digest


def test_cli_rejects_invalid_dataset_kind(tmp_path):
    with pytest.raises(SystemExit) as info:
        main(["junit", "classify", "--report", "x.xml", "--output", str(tmp_path / "c.json"), "--dataset-kind", "x"])
    assert info.value.code == 2


def test_analysis_modules_do_not_import_network_code():
    code = (
        "import sys; import hgs2_lab.records, hgs2_lab.junit_report, hgs2_lab.classify; "
        "bad = sorted(m for m in ('requests', 'urllib3', 'socket', 'http.client', 'socketserver', "
        "'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.synthetic_server', 'hgs2_lab.telemetry', "
        "'hgs2_lab.robust_z', 'hgs2_lab.detection') if m in sys.modules); print(bad)"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"  # ağ kodu yok; F5 dedektörüne de bağımlı değil
