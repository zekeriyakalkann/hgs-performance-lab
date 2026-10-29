"""Kaydedilmiş çalıştırmanın sınıflandırılması: execute_run (sahte taşıyıcı) → sonuç dosyaları + metadata
`response_parsing` → result_analysis → `results classify` CLI (ağ yok).
"""

import hashlib
import json
import socket

import pytest

from hgs2_lab import execution
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.config import LabConfig, RunLimits
from hgs2_lab.execution import execute_run
from hgs2_lab.reader import load_run
from hgs2_lab.records import TestRecord
from hgs2_lab.result_analysis import (
    ExpectationsError,
    build_run_document,
    parse_expectations,
    records_from_run,
    resolve_dataset_kind,
)
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import TransportConnectionError, TransportResponse, TransportTimeout

KART, OGR = "KART-SENTETIK-111", "OGR-SENTETIK-222"
TEXT = "text/plain;charset=UTF-8"
BODIES = {
    "kabul": (200, b"ONAYLANDI", TEXT),
    "ret-beklenen": (200, b"REDDEDILDI", TEXT),
    "ret-beklenmeyen": (200, b"REDDEDILDI", TEXT),
    "bilinmeyen": (200, b"REDDEDILDI", TEXT),
    "bos": (200, b"", TEXT),
    "bozuk-json": (200, b'{"business_outcome": "REDD', "application/json"),
    "json-alan": (200, json.dumps({"business_outcome": "REDDEDILDI", "kartNo": KART, "ogrenciNo": OGR}).encode(),
                  "application/json"),
    "sunucu-hatasi": (500, b"HATA", TEXT),
    "zaman-asimi": TransportTimeout(f"Read timed out kartNo={KART}"),
    "kopma": TransportConnectionError("Remote end closed connection without response"),
}
EXPECTATIONS = {
    "expectations_version": 1,
    "scenarios": {
        "kabul": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"], "description": "geçerli kart"},
        "ret-beklenen": {"status_codes": [200], "business_outcomes": ["REDDEDILDI"], "description": "pasif cihaz"},
        "ret-beklenmeyen": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
        "bos": {"business_outcomes": ["ONAYLANDI"]},
        "bozuk-json": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
        "json-alan": {"business_outcomes": ["REDDEDILDI"]},
        "sunucu-hatasi": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
        "zaman-asimi": {"status_codes": [200]},
        "kopma": {"status_codes": [200]},
        "olmayan-senaryo": {"status_codes": [200]},
    },
}
# senaryo → (kaynak sonuç, iş sonucu, sınıf, kural)
EXPECTED = {
    "kabul": ("PASS", "ONAYLANDI", "PASS", "H-EXPECTED-MATCH"),
    "ret-beklenen": ("PASS", "REDDEDILDI", "PASS", "H-EXPECTED-MATCH"),
    "ret-beklenmeyen": ("PASS", "REDDEDILDI", "APPLICATION_FAILURE", "H-BUSINESS-MISMATCH"),
    "bilinmeyen": ("PASS", "REDDEDILDI", "INCONCLUSIVE", "H-NO-EXPECTATION"),
    "bos": ("PASS", None, "INCONCLUSIVE", "H-BUSINESS-MISSING"),
    "bozuk-json": ("PASS", None, "INCONCLUSIVE", "H-BUSINESS-MISSING"),
    "json-alan": ("PASS", "REDDEDILDI", "PASS", "H-EXPECTED-MATCH"),
    "sunucu-hatasi": ("FAIL", "HATA", "APPLICATION_FAILURE", "H-STATUS-AND-BUSINESS-MISMATCH"),
    "zaman-asimi": ("ERROR", None, "TIMEOUT", "H-TIMEOUT"),
    "kopma": ("ERROR", None, "TRANSPORT_FAILURE", "H-TRANSPORT"),
    # rules-v3 (N12, F-1): boş 200 + yalnızca durum kodu beklentisi PASS değil; olumlu gövdeyle PASS (medium) kalır.
    "durum-beklentisi": ("PASS", None, "INCONCLUSIVE", "H-STATUS-OK-EMPTY-BODY"),
    "durum-ve-govde": ("PASS", "ONAYLANDI", "PASS", "H-STATUS-MATCH"),
}
STATUS_ONLY_SCENARIOS = ("durum-beklentisi", "durum-ve-govde")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})


class FakeTransport:
    def send(self, scenario, url, timeout_seconds):
        if scenario.name == "durum-beklentisi":
            return TransportResponse(200, 0, 1.0, body=b"", content_type=None)
        if scenario.name == "durum-ve-govde":
            return TransportResponse(200, 9, 1.0, body=b"ONAYLANDI", content_type=TEXT)
        outcome = BODIES[scenario.name]
        if isinstance(outcome, Exception):
            raise outcome
        status, body, ctype = outcome
        return TransportResponse(status, len(body), 1.0, body=body, content_type=ctype)

    def close(self):
        pass


class Clock:
    def __init__(self):
        self.ns = 1_000

    def __call__(self):
        self.ns += 1_000_000
        return self.ns


def make_run(tmp_path, run_id="run-n6", names=None, warmup=1, dataset_kind="measurement", synthetic=None):
    names = names or [*BODIES, *STATUS_ONLY_SCENARIOS]
    scenarios = [Scenario(name=n, method="POST", path=f"/api/{n}", warmup_repetitions=warmup,
                          expected_status=(200,) if n in STATUS_ONLY_SCENARIOS else ())
                 for n in names]
    config = LabConfig(base_url="http://127.0.0.1:8080", output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json", timeout_seconds=5.0,
                       limits=RunLimits(max_consecutive_transport_errors=100, max_error_rate=1.0))
    outcome = execute_run(config, scenarios, config_path=None, run_id=run_id, resolver=lambda h, p: ["127.0.0.1"],
                          transport_factory=FakeTransport, clock=Clock(), now=lambda: "2026-10-26T00:00:00+00:00",
                          sleep=lambda s: None, wall_clock=lambda: 1_767_225_600_000_000_000,
                          dataset_kind=dataset_kind, synthetic=synthetic)
    assert outcome.status == "completed", outcome.message
    return tmp_path / "results"


def write_expectations(tmp_path, data=EXPECTATIONS):
    path = tmp_path / "expectations.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_saved_run_has_business_outcome_and_parsing_metadata(tmp_path):
    results = make_run(tmp_path)
    run = load_run(results, "run-n6")
    measured = {r.scenario: r for r in run.results if not r.warmup}
    assert measured["ret-beklenen"].business_outcome == "REDDEDILDI"
    assert measured["bozuk-json"].business_outcome is None and measured["zaman-asimi"].business_outcome is None
    section = run.metadata["response_parsing"]
    assert section["parser_version"] == "response-parser-v2" and section["max_parse_bytes"] == 4096
    assert section["recognized_business_outcomes"] == ["HATA", "KAYDEDILDI", "NONE", "OK", "ONAYLANDI", "READY",
                                                       "REDDEDILDI", "SCAN_CARD", "SCAN_FP", "SCAN_SCHOOL_NO",
                                                       "WAITING"]
    with_response = [r.seq for r in run.results if r.status_code is not None]
    assert [e["seq"] for e in section["requests"]] == with_response  # her yanıt için bir özet; yanıtsız yok
    assert sum(section["rules"].values()) == len(with_response)
    for name in ("results/run-n6.json", "results/run-n6.csv"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert KART not in text and OGR not in text  # gövde dosyalara yazılmaz


def test_records_and_document_from_saved_run(tmp_path):
    run = load_run(make_run(tmp_path), "run-n6")
    expectations = parse_expectations(EXPECTATIONS)
    document = build_run_document(run, dataset_kind="fixture", expectations=expectations,
                                  expectations_source={"file": "expectations.json", "sha256": "0" * 64},
                                  now=lambda: "2026-10-26T00:00:00+00:00")
    content = document["classification"]
    records = {r["scenario_id"]: r for r in content["records"]}
    assert set(records) == set(EXPECTED)  # yalnızca ölçüm istekleri
    for name, (source, business, cls, rule) in EXPECTED.items():
        r = records[name]
        assert (r["test_outcome"], r["business_outcome"], r["analysis"]["classification"],
                r["analysis"]["rule_ids"]) == (source, business, cls, [rule]), name
        assert r["analysis"]["reason"] and r["source_type"] == "lab_result" and r["dataset_kind"] == "fixture"
        assert TestRecord.from_dict(r).to_dict() == r
    assert records["bozuk-json"]["data_quality_status"] == "partial"
    assert "response_malformed_json" in records["bozuk-json"]["warnings"]
    assert "response_rule:R-EMPTY-BODY" in records["bos"]["warnings"]
    assert records["durum-beklentisi"]["expected_result"]["description"].startswith("senaryonun expected_status")
    assert "response_body_empty" in records["durum-beklentisi"]["analysis"]["warnings"]
    assert "business_outcome_not_checked" in records["durum-ve-govde"]["analysis"]["warnings"]
    assert records["bilinmeyen"]["analysis"]["requires_review"] is True
    parsing_evidence = [e for e in records["ret-beklenen"]["analysis"]["evidence"] if e["field"] == "response_parsing"]
    assert parsing_evidence == [{"field": "response_parsing", "value": ["response_rule:R-TEXT-TOKEN"],
                                 "source": "record", "note": None}]
    source = content["sources"][0]
    assert source["warmup_requests_skipped"] == len(EXPECTED)
    assert source["unused_expectations"] == ["olmayan-senaryo"]
    assert source["expected_result_sources"] == {"expectation_registry": 0, "expectations_file": 9,
                                                 "scenario_expected_status": 2, "none": 1}
    assert source["response_parser"] == {"parser_version": "response-parser-v2", "max_parse_bytes": 4096}
    blob = json.dumps(document, ensure_ascii=False)
    assert KART not in blob and OGR not in blob and str(tmp_path) not in blob


def test_document_is_deterministic(tmp_path):
    run = load_run(make_run(tmp_path), "run-n6")
    kwargs = dict(dataset_kind="fixture", expectations=parse_expectations(EXPECTATIONS), now=lambda: "x")
    assert build_run_document(run, **kwargs) == build_run_document(run, **kwargs)


def test_cli_results_classify_end_to_end(tmp_path, capsys):
    results = make_run(tmp_path)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in results.iterdir()}
    out = tmp_path / "out" / "run-n6.classification.json"
    args = ["results", "classify", "--run-id", "run-n6", "--results-dir", str(results), "--output", str(out),
            "--expectations", str(write_expectations(tmp_path))]
    assert main(args) == EXIT_OK
    captured = capsys.readouterr()
    assert "APPLICATION_FAILURE=2" in captured.out and f"ısınma {len(EXPECTED)} atlandı" in captured.out
    assert "olmayan-senaryo" in captured.err  # kullanılmayan beklenti açıkça bildirilir
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["classification"]["summary"]["records"] == len(EXPECTED)
    assert document["classification"]["records"][0]["dataset_kind"] == "unknown"  # ölçüm: tür bilinmiyor
    assert document["classification"]["sources"][0]["expectations"]["file"] == "expectations.json"
    for text in (captured.out, captured.err, out.read_text(encoding="utf-8")):
        assert KART not in text and OGR not in text
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in results.iterdir()} == before  # salt okunur
    assert main(args) == EXIT_STORAGE_ERROR  # üzerine yazılmaz


def test_cli_without_expectations_is_inconclusive_except_explicit_status_with_parsed_body(tmp_path, capsys):
    results = make_run(tmp_path)
    out = tmp_path / "c.json"
    assert main(["results", "classify", "--run-id", "run-n6", "--results-dir", str(results), "--output", str(out),
                 "--dataset-kind", "fixture"]) == EXIT_OK
    records = json.loads(out.read_text(encoding="utf-8"))["classification"]["records"]
    decided = {r["scenario_id"]: r["analysis"]["classification"] for r in records}
    assert decided.pop("durum-ve-govde") == "PASS"  # durum kodu beklentisi + ayrıştırılmış olumlu gövde
    assert decided.pop("zaman-asimi") == "TIMEOUT" and decided.pop("kopma") == "TRANSPORT_FAILURE"
    assert set(decided.values()) == {"INCONCLUSIVE"}  # beklenti yoksa kesin karar yok


@pytest.mark.parametrize(
    "data, match",
    [
        ([], "kökü"),
        ({"expectations_version": 2, "scenarios": {"a": {"status_codes": [200]}}}, "expectations_version"),
        ({"expectations_version": True, "scenarios": {"a": {"status_codes": [200]}}}, "expectations_version"),
        ({"expectations_version": 1, "scenarios": {}}, "scenarios"),
        ({"expectations_version": 1, "scenarios": {"a": {}}}, "en az bir"),
        ({"expectations_version": 1, "scenarios": {"a": {"status_codes": [200], "x": 1}}}, "bilinmeyen"),
        ({"expectations_version": 1, "scenarios": {"a": {"status_codes": "200"}}}, "liste"),
        ({"expectations_version": 1, "scenarios": {"a": {"status_codes": [99]}}}, "status_codes"),
        ({"expectations_version": 1, "scenarios": {"a": []}}, "nesne"),
        ({"expectations_version": 1, "scenarios": {"a": {"status_codes": [200]}}, "ek": 1}, "bilinmeyen"),
    ],
)
def test_expectations_validation(data, match):
    with pytest.raises(ExpectationsError, match=match):
        parse_expectations(data)


def test_cli_rejects_bad_expectations_and_missing_run(tmp_path, capsys):
    results = make_run(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    base = ["results", "classify", "--results-dir", str(results), "--output", str(tmp_path / "c.json")]
    assert main(base + ["--run-id", "run-n6", "--expectations", str(bad)]) == EXIT_ERROR
    assert main(base + ["--run-id", "yok"]) == EXIT_ERROR
    assert not (tmp_path / "c.json").exists()


def test_dataset_kind_resolution(tmp_path):
    synthetic_meta = {"experiment_id": "e1", "seed": 1, "manifest_sha256": "0" * 64, "plan_sha256": "0" * 64,
                      "plan_algorithm_version": 1, "generator_version": "0.1.0",
                      "created_at_utc": "2026-10-26T00:00:00+00:00"}
    results = make_run(tmp_path, names=["kabul"], dataset_kind="synthetic", synthetic=synthetic_meta)
    run = load_run(results, "run-n6")
    assert resolve_dataset_kind(run, None) == "synthetic"
    with pytest.raises(ValueError, match="Sentetik"):
        resolve_dataset_kind(run, "real")
    measurement = load_run(make_run(tmp_path / "m", names=["kabul"]), "run-n6")
    assert resolve_dataset_kind(measurement, None) == "unknown"
    assert resolve_dataset_kind(measurement, "real") == "real"


def _rewrite_metadata(results, run_id, change):
    path = results / f"{run_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_old_files_without_parsing_metadata_are_flagged(tmp_path):
    results = make_run(tmp_path, names=["kabul"])
    _rewrite_metadata(results, "run-n6", lambda d: d.pop("response_parsing"))
    records, info = records_from_run(load_run(results, "run-n6"), dataset_kind="fixture")
    assert info["response_parsing_available"] is False
    assert "response_parsing_unavailable" in records[0].warnings


def test_inconsistent_parsing_metadata_marks_record_invalid(tmp_path):
    results = make_run(tmp_path, names=["kabul"], warmup=0)

    def tamper(data):
        data["response_parsing"]["requests"][0]["business_outcome"] = "REDDEDILDI"

    _rewrite_metadata(results, "run-n6", tamper)
    run = load_run(results, "run-n6")
    document = build_run_document(run, dataset_kind="fixture", expectations=parse_expectations(EXPECTATIONS))
    [record] = document["classification"]["records"]
    assert record["data_quality_status"] == "invalid" and "response_parsing_inconsistent" in record["warnings"]
    assert record["analysis"]["classification"] == "INVALID_TEST_DATA"


def test_malformed_parsing_entry_is_flagged_not_trusted(tmp_path):
    results = make_run(tmp_path, names=["kabul"], warmup=0)
    _rewrite_metadata(results, "run-n6", lambda d: d["response_parsing"]["requests"][0].update(rule_id="R-HACK"))
    records, _ = records_from_run(load_run(results, "run-n6"), dataset_kind="fixture")
    assert "response_parsing_invalid" in records[0].warnings


# --- rules-v3 (N12, F-1): ayrıştırma özeti eksik/bozuk olan 2xx, sonuç dosyasında iş sonucu yazılı olsa bile PASS olmaz ---
@pytest.mark.parametrize(
    "change, warning",
    [
        (lambda d: d.pop("response_parsing"), "response_parsing_unavailable"),
        (lambda d: d["response_parsing"].update(requests=[]), "response_parsing_missing"),
        (lambda d: d["response_parsing"]["requests"][0].update(rule_id="R-HACK"), "response_parsing_invalid"),
    ],
)
def test_status_only_200_without_trustworthy_parsing_summary_is_inconclusive(tmp_path, change, warning):
    results = make_run(tmp_path, names=["durum-ve-govde"], warmup=0)
    _rewrite_metadata(results, "run-n6", change)
    document = build_run_document(load_run(results, "run-n6"), dataset_kind="fixture")
    [record] = document["classification"]["records"]
    assert record["business_outcome"] == "ONAYLANDI" and warning in record["warnings"]
    assert record["expected_result"]["status_codes"] == [200]  # senaryonun expected_status listesi
    assert (record["analysis"]["classification"], record["analysis"]["rule_ids"]) == (
        "INCONCLUSIVE", ["H-STATUS-OK-BODY-UNVERIFIED"])


def test_status_only_200_with_intact_parsing_summary_keeps_limited_pass(tmp_path):
    results = make_run(tmp_path, names=["durum-ve-govde"], warmup=0)
    [record] = build_run_document(load_run(results, "run-n6"), dataset_kind="fixture")["classification"]["records"]
    assert (record["analysis"]["classification"], record["analysis"]["rule_ids"], record["analysis"]["confidence"]) == (
        "PASS", ["H-STATUS-MATCH"], "medium")
