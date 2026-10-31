"""`synthetic run --telemetry` entegrasyon testi: yerel sentetik sunucu (yalnızca 127.0.0.1) + gerçek telemetri.

`pytest -m integration` ile seçilir. Hedef koruması değiştirilmeden uygulanır; 127.0.0.1 dışına her bağlantı girişimi
bağlantı kurulmadan reddedilir ve testi başarısız kılar. Telemetri yalnızca işletim sistemi sayaçlarını okur.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest
from local_http_server import install_network_guard

from hgs2_lab import execution
from hgs2_lab.cli import EXIT_OK, main
from hgs2_lab.reader import load_run

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked:
        sock.close()
    assert attempts == []


@pytest.fixture(autouse=True)
def fixed_code_info(monkeypatch):
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})


def write_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "manifest_version": 1, "experiment_id": "it-tele", "experiment_type": "fault_injection",
        "dataset_kind": "synthetic", "seed": 5, "timeout_seconds": 0.5,
        "scenarios": [
            {"name": "ok", "warmup_repetitions": 1, "repetitions": 4, "fault": {"type": "none"}},
            {"name": "slow", "repetitions": 4, "fault": {"type": "fixed_delay", "delay_ms": 60}},
            {"name": "drop", "repetitions": 1, "fault": {"type": "connection_drop"}},
        ],
    }), encoding="utf-8")
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_synthetic_run_with_telemetry_end_to_end(tmp_path, capsys):
    results_dir = tmp_path / "res"
    argv = ["synthetic", "run", "--manifest", str(write_manifest(tmp_path)), "--results-dir", str(results_dir),
            "--run-id", "tele-1", "--telemetry", "--telemetry-interval-ms", "100"]
    assert main(argv) == EXIT_OK
    out = capsys.readouterr().out
    assert "deney geçerli: evet" in out and "telemetri:" in out

    doc = read_json(results_dir / "telemetry" / "tele-1.telemetry.json")
    assert doc["dataset_kind"] == "synthetic" and doc["run_id"] == "tele-1"
    assert doc["result_files"] == [{"name": n, "sha256": hashlib.sha256((results_dir / n).read_bytes()).hexdigest()}
                                   for n in ("tele-1.json", "tele-1.csv")]
    summary = doc["summary"]
    assert summary["sampler_stopped_cleanly"] is True and summary["probe_errors"] == {}
    assert summary["by_trigger"]["periodic"] >= 2  # 4 × 60 ms bekleme: en az 240 ms

    # Zaman ekseni: saat çapasıyla aynı monotonik saat; örnekler tüm istekleri kapsar.
    stored = load_run(results_dir, "tele-1")
    assert doc["clock"]["offset_available"] is True
    assert stored.clock.monotonic_source == doc["clock"]["monotonic_source"] == "time.perf_counter_ns"
    samples = doc["samples"]
    last = stored.results[-1]
    assert samples[0]["offset_ms"] <= stored.results[0].offset_ms
    assert samples[-1]["offset_ms"] >= last.offset_ms + last.elapsed_ms
    assert all(a["monotonic_ns"] < b["monotonic_ns"] for a, b in zip(samples, samples[1:]))

    if sys.platform == "win32":
        assert {k for k, v in doc["metrics"].items() if not v["available"]} <= {"disk_system"}
        tcp = [s["values"]["net_tcp_system"] for s in (samples[0], samples[-1])]
        assert tcp[1]["active_opens"] - tcp[0]["active_opens"] >= 1  # loopback bağlantıları TCP sayaçlarında görünür

    # Sonuç dosyaları, etiketler ve analiz telemetriden bağımsız kalır.
    assert "telemetry" not in stored.metadata
    labels = read_json(results_dir / "synthetic" / "tele-1.labels.json")
    assert labels["verdict"]["valid"] is True and "telemetry" not in json.dumps(labels)
    assert main(["analyze", "--results-dir", str(results_dir), "--run-id", "tele-1"]) == EXIT_OK
