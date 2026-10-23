"""Uçtan uca akış (ağsız): config/senaryo dosyaları -> runner -> metadata -> sonuç deposu -> yükleyiciler.

Taşıyıcı ve saat sahtedir; tüm gizli değerler sahtedir.
"""

import hashlib
import json

from hgs2_lab.config import load_config
from hgs2_lab.metadata import build_run_metadata
from hgs2_lab.runner import ScenarioRunner
from hgs2_lab.scenarios import load_scenarios
from hgs2_lab.storage import SCHEMA_VERSION, ResultStore
from hgs2_lab.transport import TransportResponse, TransportTimeout

FAKE = "FAKE-SECRET-123"


class FakeClock:
    def __init__(self):
        self.now_ns = 1_000

    def __call__(self):
        return self.now_ns

    def advance_ms(self, ms):
        self.now_ns += int(ms * 1_000_000)


class FakeTransport:
    def __init__(self, clock, outcomes):
        self._clock = clock
        self._outcomes = list(outcomes)

    def send(self, scenario, url, timeout_seconds):
        elapsed_ms, outcome = self._outcomes.pop(0)
        self._clock.advance_ms(elapsed_ms)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def write_project(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "scenarios.json").write_text(json.dumps({"scenarios": [
        {"name": "list", "method": "GET", "path": f"/items?page=1&token={FAKE}", "repetitions": 2,
         "warmup_repetitions": 1, "headers": {"Authorization": f"Bearer {FAKE}"}},
        {"name": "create", "method": "POST", "path": "/items", "body": {"password": FAKE, "n": 1},
         "repetitions": 2, "expected_status": [201]},
    ]}), encoding="utf-8")
    config_path = configs / "config.json"
    config_path.write_text(json.dumps({
        "base_url": "http://127.0.0.1:9", "output_dir": "../results", "scenarios_file": "scenarios.json",
    }), encoding="utf-8")
    return config_path


def test_runner_to_storage_to_loaders_roundtrip(tmp_path):
    config_path = write_project(tmp_path)
    config = load_config(config_path)
    scenarios = load_scenarios(config.scenarios_file)

    clock = FakeClock()
    transport = FakeTransport(clock, [
        (10, TransportResponse(200, 3)),  # list ısınma
        (12, TransportResponse(200, 3)),  # list ölçüm 1
        (11, TransportResponse(200, 3)),  # list ölçüm 2
        (20, TransportResponse(201, 2)),  # create ölçüm 1
        (5, TransportTimeout(f"timed out /items?token={FAKE}")),  # create ölçüm 2
    ])
    runner = ScenarioRunner(transport, config.base_url, "e2e-1", config.timeout_seconds,
                            sleep=lambda s: None, now=lambda: "2026-01-01T00:00:00+00:00", clock=clock)
    results = []
    for s in scenarios:
        results += runner.run(s)

    meta = build_run_metadata(
        config, scenarios, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00",
        config_path=config_path, monotonic_duration_ms=runner.monotonic_duration_ms,
        target_label="yerel-e2e", code={"git_commit": None, "git_dirty": None},
    )
    store = ResultStore(config.output_dir)
    csv_path, json_path = store.save("e2e-1", results, meta)

    # Kayıplı dönüşüm yok: iki yükleyici de bellekteki sonuçları birebir verir.
    stored = store.load_json("e2e-1")
    assert stored.results == results
    assert store.load_csv("e2e-1") == results

    assert [r.seq for r in results] == [1, 2, 3, 4, 5]
    assert [r.offset_ms for r in results] == [0.0, 10.0, 22.0, 33.0, 53.0]
    assert [(r.scenario, r.warmup, r.iteration) for r in results] == [
        ("list", True, 1), ("list", False, 1), ("list", False, 2), ("create", False, 1), ("create", False, 2),
    ]
    assert results[3].http_ok is True and results[4].error_type == "timeout"

    assert stored.metadata["schema_version"] == SCHEMA_VERSION == 2
    assert stored.metadata["run_id"] == "e2e-1"
    assert stored.metadata["monotonic_duration_ms"] == 58.0
    assert stored.metadata["target_label"] == "yerel-e2e"
    assert stored.metadata["inputs"]["config_sha256"] == hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert stored.metadata["inputs"]["scenarios_sha256"] == hashlib.sha256(
        config.scenarios_file.read_bytes()).hexdigest()

    # Sonuç dosyalarında gizli değer ve mutlak yerel yol yok.
    for path in (csv_path, json_path):
        text = path.read_text(encoding="utf-8")
        assert FAKE not in text
        assert str(tmp_path) not in text and json.dumps(str(tmp_path))[1:-1] not in text
    assert results[0].url == "http://127.0.0.1:9/items?page=1&token=***REDACTED***"
    assert csv_path.parent == (tmp_path / "results").resolve()
