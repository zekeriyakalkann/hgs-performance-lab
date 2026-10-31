"""Sistem telemetrisi (F4) birim testleri: sahte metrik grupları, sahte taşıyıcı ve saatler; ağ ve soket yok.

Windows'ta gerçek sayaçlar yalnızca salt okunur olarak sınanır (bağlantı kurulmaz). Zamanlama testleri yalnızca alt
sınır doğrular.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from hgs2_lab import execution
from hgs2_lab import telemetry as tm
from hgs2_lab.analysis import AnalysisParams, build_document
from hgs2_lab.cli import EXIT_OK, main
from hgs2_lab.clock import ClockAnchor
from hgs2_lab.config import LabConfig, RunLimits
from hgs2_lab.execution import STATUS_ABORTED, STATUS_COMPLETED, STATUS_INTERRUPTED, PreflightError, execute_run
from hgs2_lab.reader import load_run
from hgs2_lab.scenarios import Scenario
from hgs2_lab.storage import ResultStore
from hgs2_lab.synthetic_experiment import run_synthetic_experiment
from hgs2_lab.transport import TransportResponse, TransportTimeout

ROOT = Path(__file__).resolve().parent.parent
CODE = {"git_commit": None, "git_dirty": None}
LOOPBACK = lambda host, port: ["127.0.0.1"]  # noqa: E731
WALL_NS = 1_792_000_000_000_000_000
LONG_INTERVAL = tm.MAX_INTERVAL_MS  # testte periyodik örnek oluşmaz: yalnızca start/stop


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


class Ticker:
    """Her okumada `step` ns ilerleyen sahte monotonik saat (iş parçacığı güvenli)."""

    def __init__(self, start=1_000_000, step=1_000):
        self.now_ns = start
        self.step = step
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.now_ns += self.step
            return self.now_ns

    def advance_ms(self, ms):
        with self._lock:
            self.now_ns += int(ms * 1_000_000)


def fixed_wall():
    return WALL_NS


def probe(name="cpu_system", read=None, fields=tm.CPU_SYSTEM_FIELDS, scope=tm.SCOPE_SYSTEM, **kw):
    if read is None:
        def read():
            return {"idle_s": 1.0, "kernel_s": 2.0, "user_s": 0.5}
    return tm.Probe(name, scope, "fake", fields, read, **kw)


def raising(exc):
    calls = []

    def read():
        calls.append(1)
        raise exc

    read.calls = calls
    return read


def recorder(probes, **kw):
    kw.setdefault("interval_ms", LONG_INTERVAL)
    kw.setdefault("clock", Ticker())
    kw.setdefault("wall_clock", fixed_wall)
    kw.setdefault("cpu_count", 4)
    return tm.TelemetryRecorder(probes, **kw)


def run_recorder(rec):
    rec.start()
    rec.stop()
    return rec.document("r1", anchor=None, dataset_kind="measurement", generated_at="2026-01-01T00:00:00+00:00")


def walk_keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_keys(v)


# --- örnek biçimi ve zaman damgaları ---
def test_start_and_stop_samples_carry_timestamps_values_and_cost():
    doc = run_recorder(recorder([probe(), probe("memory_system", lambda: {
        "memory_load_percent": 40, "total_phys_bytes": 100, "avail_phys_bytes": 60, "commit_limit_bytes": 200,
        "commit_avail_bytes": 120}, tm.MEMORY_SYSTEM_FIELDS)]))

    assert doc["format"] == tm.TELEMETRY_FORMAT and doc["telemetry_schema_version"] == 1
    assert doc["run_id"] == "r1" and doc["dataset_kind"] == "measurement"
    samples = doc["samples"]
    assert [s["trigger"] for s in samples] == ["start", "stop"]
    assert [s["index"] for s in samples] == [0, 1]
    assert samples[0]["monotonic_ns"] < samples[1]["monotonic_ns"]
    for s in samples:
        assert s["wall_time_ns"] == WALL_NS and s["wall_time_utc"].endswith("+00:00")
        assert s["collect_ns"] > 0 and s["lag_ns"] is None and s["errors"] == {}
        assert list(s["values"]["cpu_system"]) == ["idle_s", "kernel_s", "user_s"]  # tanımlı alanlar, sabit sıra
        assert s["values"]["memory_system"]["avail_phys_bytes"] == 60
        assert s["offset_ms"] is None  # çapa yok: ofset uydurulmaz
    assert doc["clock"]["offset_available"] is False
    assert doc["metrics"]["cpu_system"] == {
        "scope": "system", "source": "fake", "note": "", "available": True, "reason": None,
        "fields": {"idle_s": {"unit": "s", "kind": "counter"}, "kernel_s": {"unit": "s", "kind": "counter"},
                   "user_s": {"unit": "s", "kind": "counter"}},
    }
    assert doc["summary"]["by_trigger"] == {"start": 1, "periodic": 0, "stop": 1}
    assert doc["summary"]["sampler_stopped_cleanly"] is True
    json.dumps(doc, allow_nan=False)  # yazılabilir: NaN/inf yok


def test_offsets_are_relative_to_run_clock_anchor_of_the_same_clock():
    clock = Ticker()
    rec = recorder([probe()], clock=clock)
    rec.start()
    anchor = ClockAnchor.capture(clock, fixed_wall)  # runner'ın ilk isteğinden önceki çapası
    clock.advance_ms(50)
    rec.stop()
    doc = rec.document("r1", anchor=anchor, dataset_kind="measurement", generated_at="T")
    start, stop = doc["samples"]
    assert doc["clock"]["offset_available"] is True
    assert start["offset_ms"] == (start["monotonic_ns"] - anchor.monotonic_ns) / 1e6 < 0  # ilk istekten önce
    assert stop["offset_ms"] >= 50

    other = ClockAnchor(**{**anchor.to_dict(), "monotonic_source": "time.monotonic_ns"})
    doc = rec.document("r1", anchor=other, dataset_kind="measurement", generated_at="T")
    assert doc["clock"]["offset_available"] is False and all(s["offset_ms"] is None for s in doc["samples"])


def test_periodic_samples_follow_the_interval_with_real_clock():
    calls = []

    def read():
        calls.append(time.perf_counter_ns())
        return {"idle_s": 1.0, "kernel_s": 2.0, "user_s": 0.5}

    rec = tm.TelemetryRecorder([probe(read=read)], interval_ms=tm.MIN_INTERVAL_MS)
    rec.start()
    time.sleep(0.45)
    rec.stop()
    doc = rec.document("r1", anchor=None, dataset_kind="measurement", generated_at="T")
    samples = doc["samples"]
    periodic = [s for s in samples if s["trigger"] == "periodic"]
    assert len(periodic) >= 2 and samples[0]["trigger"] == "start" and samples[-1]["trigger"] == "stop"
    assert all(a["monotonic_ns"] < b["monotonic_ns"] for a, b in zip(samples, samples[1:]))
    assert all(s["lag_ns"] >= 0 for s in periodic)  # planlanan andan önce örnek alınmaz
    assert all(s["derived"]["interval_ms"] > 0 for s in samples[1:])
    assert len(calls) == len(samples)
    assert doc["summary"]["sampler_thread_cpu_ms"] is not None and doc["summary"]["lag_ms"]["max"] >= 0


def test_max_samples_drops_periodic_samples_but_keeps_the_stop_sample():
    rec = tm.TelemetryRecorder([probe()], interval_ms=tm.MIN_INTERVAL_MS, max_samples=3)
    rec.start()
    time.sleep(0.45)
    rec.stop()
    summary = rec.summary()
    assert summary["samples"] == 3 and summary["dropped_samples"] >= 1
    assert summary["by_trigger"] == {"start": 1, "periodic": 1, "stop": 1}


# --- hata politikası: değer uydurulmaz, çalıştırma durmaz ---
def test_probe_read_error_is_recorded_without_fabricating_values():
    failing = raising(OSError("sayaç okunamadı"))
    doc = run_recorder(recorder([probe("cpu_system", failing), probe("cpu_process", lambda: {
        "user_s": 0.1, "system_s": 0.2}, tm.CPU_PROCESS_FIELDS, tm.SCOPE_PROCESS)]))
    for s in doc["samples"]:
        assert s["values"]["cpu_system"] is None
        assert s["errors"] == {"cpu_system": "OSError: sayaç okunamadı"}
        assert s["values"]["cpu_process"] == {"user_s": 0.1, "system_s": 0.2}
    assert doc["samples"][1]["derived"]["system_cpu_busy_ratio"] is None  # eksik veriden oran üretilmez
    assert doc["summary"]["probe_errors"] == {"cpu_system": 2}
    assert doc["metrics"]["cpu_system"]["available"] is True  # geçici hata; grup devre dışı bırakılmaz
    assert len(failing.calls) == 2


def test_unavailable_probe_is_marked_once_and_not_retried():
    failing = raising(tm.ProbeUnavailable("bu ortamda yok"))
    doc = run_recorder(recorder([probe("disk_system", failing, tm.DISK_SYSTEM_FIELDS)]))
    assert len(failing.calls) == 1
    assert doc["metrics"]["disk_system"]["available"] is False
    assert doc["metrics"]["disk_system"]["reason"] == "bu ortamda yok"
    assert all(s["values"]["disk_system"] is None and s["errors"] == {} for s in doc["samples"])
    assert doc["summary"]["unavailable"] == {"disk_system": "bu ortamda yok"}


def test_unexpected_exceptions_and_incomplete_values_do_not_stop_sampling():
    doc = run_recorder(recorder([
        probe("cpu_system", raising(ZeroDivisionError())),
        probe("memory_process", lambda: {"working_set_bytes": 1}, tm.MEMORY_PROCESS_FIELDS, tm.SCOPE_PROCESS),
        probe("io_process", lambda: dict.fromkeys(tm.IO_PROCESS_FIELDS, 0), tm.IO_PROCESS_FIELDS, tm.SCOPE_PROCESS),
    ]))
    errors = doc["samples"][0]["errors"]
    assert errors["cpu_system"] == "ZeroDivisionError"
    assert errors["memory_process"].startswith("KeyError")  # eksik alan tamamlanmaz
    assert doc["samples"][0]["values"]["memory_process"] is None
    assert doc["samples"][0]["values"]["io_process"]["read_ops"] == 0
    assert doc["summary"]["sampler_error"] is None and doc["summary"]["sampler_stopped_cleanly"] is True


def test_stop_releases_probe_resources_and_recorder_is_single_use():
    closed = []
    rec = recorder([probe(close=lambda: closed.append(1))])
    rec.stop()  # başlamadan durdurmak etkisiz
    assert rec.summary()["samples"] == 0
    rec.start()
    with pytest.raises(RuntimeError):
        rec.start()
    rec.stop()
    rec.stop()
    assert closed == [1]


@pytest.mark.parametrize("value", [tm.MIN_INTERVAL_MS - 1, tm.MAX_INTERVAL_MS + 1, 0, -5, True, 250.0, "250", None])
def test_invalid_interval_is_rejected(value):
    with pytest.raises(tm.TelemetryError):
        tm.TelemetryRecorder([], interval_ms=value)


def test_interval_limits_are_inclusive():
    assert tm.validate_interval_ms(tm.MIN_INTERVAL_MS) == tm.MIN_INTERVAL_MS
    assert tm.validate_interval_ms(tm.MAX_INTERVAL_MS) == tm.MAX_INTERVAL_MS
    with pytest.raises(tm.TelemetryError):
        tm.TelemetryRecorder([], max_samples=1)


# --- türetilmiş oranlar ---
def sample(ns, cpu=None, proc=None):
    return {"monotonic_ns": ns, "values": {"cpu_system": cpu, "cpu_process": proc}}


def test_derived_cpu_ratios_from_consecutive_samples():
    prev = sample(0, {"idle_s": 10.0, "kernel_s": 15.0, "user_s": 5.0}, {"user_s": 1.0, "system_s": 0.5})
    cur = sample(1_000_000_000, {"idle_s": 11.0, "kernel_s": 17.0, "user_s": 6.0}, {"user_s": 1.25, "system_s": 0.75})
    d = tm.derive(prev, cur, cpu_count=4)
    assert d["interval_ms"] == 1000.0
    assert d["system_cpu_busy_ratio"] == pytest.approx(2 / 3)  # kernel boşta süreyi içerir: (3 - 1) / 3
    assert d["process_cpu_ratio"] == pytest.approx(0.5 / 4)
    assert tm.derive(None, cur, 4) == dict.fromkeys(tm.DERIVED_FIELDS)
    assert tm.derive(prev, cur, None)["process_cpu_ratio"] is None
    same = sample(1_000_000_000, prev["values"]["cpu_system"], None)
    assert tm.derive(prev, same, 4)["system_cpu_busy_ratio"] is None  # payda 0: oran yok


# --- platform ---
def test_unsupported_platform_marks_system_groups_unavailable_without_values():
    probes = tm.default_probes("linux")
    assert [p.name for p in probes] == list(tm.PROBE_NAMES)
    by_name = {p.name: p for p in probes}
    values = by_name["cpu_process"].read()
    assert set(values) == {"user_s", "system_s"} and all(v >= 0 for v in values.values())
    for name in set(tm.PROBE_NAMES) - {"cpu_process"}:
        with pytest.raises(tm.ProbeUnavailable, match="desteklenmeyen platform: linux"):
            by_name[name].read()
    doc = run_recorder(recorder(probes))
    assert {k for k, v in doc["metrics"].items() if v["available"]} == {"cpu_process"}
    assert {p["scope"] for p in doc["metrics"].values()} == {"system", "process"}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows sayaçları")
def test_windows_probes_read_real_counters():
    probes = {p.name: p for p in tm.default_probes()}
    assert list(probes) == list(tm.PROBE_NAMES)
    unavailable = {n: p for n, p in probes.items() if p.source == "unavailable"}
    assert set(unavailable) <= {"disk_system"}, unavailable  # disk sayaçları kapalı olabilir; diğerleri her zaman
    first = {n: p.read() for n, p in probes.items() if n not in unavailable}
    second = {n: p.read() for n, p in probes.items() if n not in unavailable}
    for name, values in first.items():
        assert list(values) == list(probes[name].fields)
        for field, (_, kind) in probes[name].fields.items():
            assert values[field] >= 0
            if kind == tm.COUNTER and name != "net_tcp_system":  # 32 bit TCP sayaçları taşabilir
                assert second[name][field] >= values[field], (name, field)
    cpu = first["cpu_system"]
    assert cpu["kernel_s"] >= cpu["idle_s"] > 0
    mem = first["memory_system"]
    assert mem["total_phys_bytes"] >= mem["avail_phys_bytes"] > 0 and 0 <= mem["memory_load_percent"] <= 100
    assert first["memory_process"]["working_set_bytes"] > 0 and first["cpu_process"]["cycles"] > 0
    if "disk_system" in first:
        assert first["disk_system"]["drives"] >= 1
    for p in probes.values():
        if p.close is not None:
            p.close()


def test_telemetry_module_does_not_import_network_code():
    code = (
        "import sys; import hgs2_lab.telemetry as t; t.default_probes(); "
        "bad = sorted(m for m in ('requests', 'urllib3', 'socket', 'http.client', 'socketserver', "
        "'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.synthetic_server', 'hgs2_lab.target_guard') "
        "if m in sys.modules); print(bad)"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"


def test_document_contains_no_label_design_or_request_position_fields():
    doc = run_recorder(recorder(tm.default_probes("linux")))
    forbidden = {"seq", "iteration", "planned_fault", "expected_outcome", "hold_ms_actual", "planned", "expected",
                 "label_status", "agreement", "scenario", "delay_ms"}
    assert forbidden.isdisjoint(set(walk_keys(doc)))


# --- execute_run entegrasyonu (sahte taşıyıcı) ---
class FakeTransport:
    def __init__(self, clock, outcomes=()):
        self._clock = clock
        self._outcomes = list(outcomes)
        self.sent = []
        self.closed = False

    def send(self, scenario, url, timeout_seconds):
        self.sent.append(url)
        elapsed_ms, outcome = self._outcomes.pop(0) if self._outcomes else (10, TransportResponse(200, 2))
        self._clock.advance_ms(elapsed_ms)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


def run(tmp_path, scenarios=None, outcomes=(), telemetry=None, **limits):
    tmp_path.mkdir(parents=True, exist_ok=True)
    clock = getattr(telemetry, "_clock", None) or Ticker(step=0)
    transport = FakeTransport(clock, outcomes)
    config = LabConfig(base_url="http://127.0.0.1:8080", timeout_seconds=2.0, output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json", limits=RunLimits(**limits))
    (tmp_path / "scenarios.json").write_text('{"scenarios": []}', encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text('{"base_url": "http://127.0.0.1:8080"}', encoding="utf-8")
    scenarios = scenarios or [Scenario(name="s", method="GET", path="/p", repetitions=3, warmup_repetitions=1)]
    outcome = execute_run(config, scenarios, config_path=config_path, run_id="r1", resolver=LOOPBACK,
                          transport_factory=lambda: transport, clock=clock, wall_clock=fixed_wall,
                          now=lambda: "2026-01-01T00:00:00+00:00", sleep=lambda s: clock.advance_ms(s * 1000),
                          code=CODE, telemetry=telemetry)
    return outcome, transport, config.output_dir


def fake_recorder(probes=None):
    clock = Ticker(step=0)
    return tm.TelemetryRecorder(probes or [probe()], interval_ms=LONG_INTERVAL, clock=clock, wall_clock=fixed_wall,
                                cpu_count=4)


def test_execute_run_with_telemetry_writes_separate_file_and_leaves_results_byte_identical(tmp_path):
    plain, _, plain_dir = run(tmp_path / "plain")
    rec = fake_recorder()
    outcome, transport, out = run(tmp_path / "tele", telemetry=rec)

    assert plain.telemetry_path is None and plain.telemetry_error is None
    assert not (plain_dir / tm.TELEMETRY_DIR_NAME).exists()  # telemetri istenmezse dizin bile oluşmaz
    for name in ("r1.csv", "r1.json"):  # v2 sonuç dosyaları telemetriden etkilenmez
        assert (out / name).read_bytes() == (plain_dir / name).read_bytes()
    assert "telemetry" not in json.loads((out / "r1.json").read_text(encoding="utf-8"))

    assert outcome.status == STATUS_COMPLETED and outcome.telemetry_error is None and transport.closed
    assert outcome.telemetry_path == out / "telemetry" / "r1.telemetry.json"
    doc = json.loads(outcome.telemetry_path.read_text(encoding="utf-8"))
    assert doc["run_id"] == "r1" and doc["dataset_kind"] == "measurement"
    assert doc["result_files"] == [{"name": n, "sha256": hashlib.sha256((out / n).read_bytes()).hexdigest()}
                                   for n in ("r1.json", "r1.csv")]
    # Örnekler istekleri kapsar: başlangıç ilk istekten önce, bitiş son istekten sonra (aynı saat, aynı çapa).
    results = ResultStore(out).load_json("r1").results
    start, stop = doc["samples"][0], doc["samples"][-1]
    assert doc["clock"]["offset_available"] is True
    assert start["offset_ms"] <= 0 and stop["offset_ms"] >= results[-1].offset_ms + results[-1].elapsed_ms
    assert rec._thread is not None and not rec._thread.is_alive()


def test_reader_and_analysis_are_unaffected_by_the_telemetry_directory(tmp_path):
    outcome, _, out = run(tmp_path, telemetry=fake_recorder())
    stored = load_run(out, "r1")
    assert sorted(f.name for f in stored.files) == ["r1.csv", "r1.json"]  # telemetri dosyası girdi değildir
    document = build_document(stored, AnalysisParams())
    assert "telemetry" not in json.dumps(document["analysis"]["input"])
    assert document["analysis"]["clock"]["telemetry_alignment"] == "same_process_only"


def test_aborted_run_writes_partial_telemetry_next_to_partial_results(tmp_path):
    outcome, _, out = run(tmp_path, telemetry=fake_recorder(), outcomes=[(5, TransportTimeout("t"))] * 3,
                          max_consecutive_transport_errors=2)
    assert outcome.status == STATUS_ABORTED
    assert outcome.telemetry_path == out / "telemetry" / "r1.partial.telemetry.json"
    doc = json.loads(outcome.telemetry_path.read_text(encoding="utf-8"))
    assert [f["name"] for f in doc["result_files"]] == ["r1.partial.json", "r1.partial.csv"]


def test_keyboard_interrupt_stops_the_sampler_and_keeps_partial_telemetry(tmp_path):
    rec = fake_recorder()
    outcome, _, out = run(tmp_path, telemetry=rec, outcomes=[(5, TransportResponse(200, 1)), (1, KeyboardInterrupt())])
    assert outcome.status == STATUS_INTERRUPTED
    assert not rec._thread.is_alive()
    assert (out / "telemetry" / "r1.partial.telemetry.json").exists()


@pytest.mark.parametrize("name", ["r1.telemetry.json", "r1.partial.telemetry.json"])
def test_existing_telemetry_file_is_not_overwritten_and_nothing_is_sent(tmp_path, name):
    target = tmp_path / "results" / "telemetry" / name
    target.parent.mkdir(parents=True)
    target.write_text("eski", encoding="utf-8")
    with pytest.raises(PreflightError, match="telemetri dosyası zaten var"):
        run(tmp_path, telemetry=fake_recorder())
    assert target.read_text(encoding="utf-8") == "eski"
    assert not (tmp_path / "results" / "r1.json").exists()
    # Telemetri istenmezse eski davranış: telemetri dosyası ön kontrole girmez.
    outcome, _, _ = run(tmp_path, telemetry=None)
    assert outcome.status == STATUS_COMPLETED and target.read_text(encoding="utf-8") == "eski"


def test_telemetry_failures_never_fail_the_run_or_lose_results(tmp_path):
    dead = [probe(n, raising(OSError("yok")), f) for n, f in (("cpu_system", tm.CPU_SYSTEM_FIELDS),
                                                             ("memory_system", tm.MEMORY_SYSTEM_FIELDS))]
    outcome, _, out = run(tmp_path / "a", telemetry=fake_recorder(dead))
    assert outcome.status == STATUS_COMPLETED and outcome.telemetry_path is not None
    doc = json.loads(outcome.telemetry_path.read_text(encoding="utf-8"))
    assert doc["summary"]["probe_errors"] == {"cpu_system": 2, "memory_system": 2}

    class BrokenRecorder(tm.TelemetryRecorder):
        def document(self, *args, **kwargs):
            raise RuntimeError("belge üretilemedi")

    broken = BrokenRecorder([probe()], interval_ms=LONG_INTERVAL, clock=Ticker(step=0), wall_clock=fixed_wall)
    outcome, _, out = run(tmp_path / "b", telemetry=broken)
    assert outcome.status == STATUS_COMPLETED
    assert outcome.telemetry_path is None and outcome.telemetry_error == "RuntimeError: belge üretilemedi"
    assert len(ResultStore(out).load_json("r1").results) == 4
    assert not (out / "telemetry").exists()


def test_synthetic_experiment_rejects_existing_telemetry_before_starting_the_server(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "manifest_version": 1, "experiment_id": "t", "experiment_type": "fault_injection", "dataset_kind": "synthetic",
        "seed": 1, "timeout_seconds": 1, "scenarios": [{"name": "ok", "repetitions": 1, "fault": {"type": "none"}}],
    }), encoding="utf-8")
    existing = tmp_path / "res" / "telemetry" / "syn-1.telemetry.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("eski", encoding="utf-8")

    def no_server(plan):
        raise AssertionError("sunucu başlatılmamalı")

    with pytest.raises(PreflightError, match="syn-1.telemetry.json"):
        run_synthetic_experiment(manifest, results_dir=tmp_path / "res", run_id="syn-1", server_factory=no_server,
                                 telemetry=fake_recorder())
    assert existing.read_text(encoding="utf-8") == "eski"


# --- CLI ---
@pytest.fixture
def cli_files(tmp_path, monkeypatch):
    monkeypatch.setattr(execution, "RequestsTransport",
                        lambda resolver: FakeTransport(Ticker(step=0), [(1, TransportResponse(200, 2))] * 3))
    monkeypatch.setattr(execution, "code_info", lambda: CODE)
    (tmp_path / "scen.json").write_text(json.dumps(
        {"scenarios": [{"name": "a", "method": "GET", "path": "/a", "repetitions": 3}]}), encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"base_url": "http://127.0.0.1:8080", "scenarios_file": "scen.json",
                               "output_dir": "results"}), encoding="utf-8")
    return cfg


def test_cli_run_with_telemetry_writes_file_and_reports_cost(tmp_path, capsys, cli_files):
    assert main(["run", "--config", str(cli_files), "--telemetry", "--telemetry-interval-ms", "100"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "telemetri:" in out and "aralık 100 ms" in out and "toplama medyan" in out
    files = list((tmp_path / "results" / "telemetry").glob("*.telemetry.json"))
    assert len(files) == 1
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["sampling"]["interval_ms"] == 100 and doc["samples"][0]["trigger"] == "start"


def test_cli_run_without_telemetry_keeps_previous_behaviour(tmp_path, capsys, cli_files):
    assert main(["run", "--config", str(cli_files)]) == EXIT_OK
    assert "telemetri" not in capsys.readouterr().out
    assert not (tmp_path / "results" / "telemetry").exists()


@pytest.mark.parametrize("argv", [
    ["run", "--telemetry", "--telemetry-interval-ms", "50"],
    ["run", "--telemetry", "--telemetry-interval-ms", "abc"],
    ["run", "--telemetry-interval-ms", "250"],  # --telemetry olmadan
    ["synthetic", "run", "--manifest", "m.json", "--results-dir", "r", "--telemetry-interval-ms", "250"],
    ["synthetic", "run", "--manifest", "m.json", "--results-dir", "r", "--telemetry", "--telemetry-interval-ms", "0"],
])
def test_cli_rejects_invalid_telemetry_options_as_usage_error(argv, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    assert not (tmp_path / "r").exists()
