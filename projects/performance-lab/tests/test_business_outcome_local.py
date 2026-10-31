"""N6 entegrasyon testleri: gerçek RequestsTransport + yerel loopback sunucusu → `run` → `results classify`.

Varsayılan çalıştırmada hariçtir; `pytest -m integration` ile seçilir. Sunucu yalnızca 127.0.0.1'e bind eder;
`install_network_guard` 127.0.0.1 dışındaki her bağlantıyı kurulmadan reddeder. Gövdelerdeki kişisel değerler
sentetiktir. Gerçek HGS2'ye erişilmez; HGS2 benzeri gövdeler test sunucusunda sabittir.
"""

import json

import pytest
from local_http_server import BUSINESS_SECRET, LOOPBACK, LocalHTTPServer, install_network_guard

from hgs2_lab import execution
from hgs2_lab.cli import EXIT_OK, main
from hgs2_lab.reader import load_run
from hgs2_lab.synthetic_experiment import run_synthetic_experiment

pytestmark = pytest.mark.integration

ROUTES = ["reddedildi", "onaylandi", "hata-500", "json-field", "malformed-json", "empty", "large", "html"]
EXPECTATIONS = {
    "expectations_version": 1,
    "scenarios": {
        "reddedildi": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"], "description": "geçerli kart"},
        "onaylandi": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
        "hata-500": {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
        "json-field": {"business_outcomes": ["REDDEDILDI"], "description": "pasif cihaz reddi"},
        "malformed-json": {"business_outcomes": ["ONAYLANDI"]},
        "empty": {"business_outcomes": ["ONAYLANDI"]},
        "large": {"business_outcomes": ["REDDEDILDI"]},
        "html": {"business_outcomes": ["REDDEDILDI"]},
        "stall": {"status_codes": [200]},
    },
}
# senaryo → (durum, iş sonucu, ayrıştırma kuralı, sınıf)
EXPECTED = {
    "reddedildi": (200, "REDDEDILDI", "R-TEXT-TOKEN", "APPLICATION_FAILURE"),
    "onaylandi": (200, "ONAYLANDI", "R-TEXT-TOKEN", "PASS"),
    "hata-500": (500, "HATA", "R-TEXT-TOKEN", "APPLICATION_FAILURE"),
    "json-field": (200, "REDDEDILDI", "R-JSON-FIELD", "PASS"),
    "malformed-json": (200, None, "R-MALFORMED-JSON", "INCONCLUSIVE"),
    "empty": (200, None, "R-EMPTY-BODY", "INCONCLUSIVE"),
    "large": (200, None, "R-TOO-LARGE", "INCONCLUSIVE"),
    "html": (200, None, "R-UNSUPPORTED-TYPE", "INCONCLUSIVE"),
    "stall": (None, None, None, "TIMEOUT"),
}


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked_sockets = install_network_guard(monkeypatch)
    yield attempts
    assert attempts == [], "127.0.0.1 dışına bağlantı denendi"
    for sock in blocked_sockets:
        sock.close()


@pytest.fixture(autouse=True)
def fixed_code_info(monkeypatch):
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})


@pytest.fixture
def server():
    srv = LocalHTTPServer()
    assert srv.server_address[0] == LOOPBACK
    srv.start()
    yield srv
    srv.release_stalled()
    assert srv.stop() == []
    assert srv.unexpected_errors() == []


def test_run_then_classify_with_real_transport(tmp_path, server, capsys):
    scenarios = [{"name": name, "method": "POST", "path": f"/business/{name}", "repetitions": 1} for name in ROUTES]
    scenarios.append({"name": "stall", "method": "GET", "path": "/stall-headers", "repetitions": 1})
    (tmp_path / "scenarios.json").write_text(json.dumps({"scenarios": scenarios}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"base_url": server.base_url, "timeout_seconds": 1.0, "output_dir": "results",
                                  "scenarios_file": "scenarios.json",
                                  "limits": {"max_error_rate": 1.0}}), encoding="utf-8")
    assert main(["run", "--config", str(config)]) == EXIT_OK
    [json_file] = (tmp_path / "results").glob("*.json")
    run_id = json_file.stem
    run = load_run(tmp_path / "results", run_id)
    by_name = {r.scenario: r for r in run.results}
    parsing = {e["seq"]: e for e in run.metadata["response_parsing"]["requests"]}
    for name, (status, outcome, rule, _) in EXPECTED.items():
        r = by_name[name]
        assert (r.status_code, r.business_outcome) == (status, outcome), name
        assert (parsing[r.seq]["rule_id"] if r.seq in parsing else None) == rule, name
    assert by_name["large"].response_bytes == 5010  # ölçüm gövdenin tamamını okumaya devam eder
    for path in (tmp_path / "results").iterdir():
        assert BUSINESS_SECRET not in path.read_text(encoding="utf-8")  # gövde kayda yazılmaz

    expectations = tmp_path / "expectations.json"
    expectations.write_text(json.dumps(EXPECTATIONS), encoding="utf-8")
    out = tmp_path / "n6-local.classification.json"
    capsys.readouterr()
    assert main(["results", "classify", "--run-id", run_id, "--results-dir", str(tmp_path / "results"),
                 "--expectations", str(expectations), "--output", str(out)]) == EXIT_OK
    captured = capsys.readouterr()
    records = {r["scenario_id"]: r for r in json.loads(out.read_text(encoding="utf-8"))["classification"]["records"]}
    for name, (status, outcome, rule, cls) in EXPECTED.items():
        r = records[name]
        assert (r["status_code"], r["business_outcome"], r["analysis"]["classification"]) == (status, outcome, cls)
        if rule:
            assert f"response_rule:{rule}" in r["warnings"]
    assert records["stall"]["transport_error"] == "timeout"
    assert BUSINESS_SECRET not in out.read_text(encoding="utf-8") + captured.out + captured.err


def test_synthetic_experiment_is_unchanged_and_classifiable(tmp_path, capsys):
    manifest = {
        "manifest_version": 1, "experiment_id": "n6-syn", "experiment_type": "fault_injection",
        "dataset_kind": "synthetic", "seed": 7, "timeout_seconds": 0.3,
        "limits": {"max_consecutive_transport_errors": 10},
        "scenarios": [
            {"name": "ok", "warmup_repetitions": 1, "repetitions": 3, "fault": {"type": "none"}},
            {"name": "err", "repetitions": 2, "fault": {"type": "http_error", "status": 503}},
            {"name": "drop", "repetitions": 1, "fault": {"type": "connection_drop"}},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    outcome = run_synthetic_experiment(path, results_dir=tmp_path / "res", run_id="n6-syn")
    assert outcome.valid  # F2 etiketleme ve geçerlilik değişmedi
    run = load_run(tmp_path / "res", "n6-syn")
    assert {r.business_outcome for r in run.results} == {None}  # "synthetic ok" bir iş sonucu değildir
    assert set(run.metadata["response_parsing"]["rules"]) == {"R-TEXT-UNRECOGNIZED"}
    out = tmp_path / "syn.classification.json"
    assert main(["results", "classify", "--run-id", "n6-syn", "--results-dir", str(tmp_path / "res"),
                 "--output", str(out)]) == EXIT_OK
    content = json.loads(out.read_text(encoding="utf-8"))["classification"]
    assert {r["dataset_kind"] for r in content["records"]} == {"synthetic"}
    classes = {r["scenario_id"]: r["analysis"]["classification"] for r in content["records"]}
    assert classes == {"ok": "INCONCLUSIVE", "err": "INCONCLUSIVE", "drop": "TRANSPORT_FAILURE"}
