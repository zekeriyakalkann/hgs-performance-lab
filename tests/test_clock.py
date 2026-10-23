"""Saat çapası testleri: okuma sırası, belirsizlik penceresi, doğrulama, runner ve metadata entegrasyonu (ağ yok)."""

import time
from datetime import datetime, timezone

import pytest

from hgs2_lab.clock import (
    MONOTONIC_SCOPE_PROCESS,
    ClockAnchor,
    ClockAnchorError,
    callable_name,
    ns_to_utc_iso,
)
from hgs2_lab.config import LabConfig
from hgs2_lab.execution import execute_run
from hgs2_lab.runner import ScenarioRunner
from hgs2_lab.scenarios import Scenario
from hgs2_lab.storage import ResultStore
from hgs2_lab.transport import TransportResponse

WALL_NS = 1_767_225_600_123_456_789  # 2026-01-01T00:00:00.123456789Z


class StepClock:
    """Her okumada `step` ns ilerleyen monotonik saat; okumaları `log`a yazar."""

    def __init__(self, log, start=10_000, step=0):
        self.log, self.now_ns, self.step = log, start, step

    def __call__(self):
        self.log.append(("mono", self.now_ns))
        value = self.now_ns
        self.now_ns += self.step
        return value


def test_capture_reads_monotonic_wall_monotonic_in_order():
    log = []
    mono = StepClock(log, start=10_000, step=700)

    def wall():
        log.append(("wall", WALL_NS))
        return WALL_NS

    anchor = ClockAnchor.capture(mono, wall)
    assert [kind for kind, _ in log] == ["mono", "wall", "mono"]
    assert anchor.monotonic_ns == 10_000  # başlangıç referansı ilk monotonik okumadır
    assert anchor.read_window_ns == 700  # duvar saati okuması bu aralıkta
    assert anchor.wall_time_ns == WALL_NS
    assert anchor.wall_time_utc == "2026-01-01T00:00:00.123456+00:00"
    assert anchor.monotonic_scope == MONOTONIC_SCOPE_PROCESS
    assert anchor.anchor_event == "runner_origin"


def test_default_clock_sources_are_named():
    assert callable_name(time.perf_counter_ns) == "time.perf_counter_ns"
    assert callable_name(time.time_ns) == "time.time_ns"
    anchor = ClockAnchor.capture(time.perf_counter_ns, time.time_ns)
    assert (anchor.monotonic_source, anchor.wall_source) == ("time.perf_counter_ns", "time.time_ns")
    assert anchor.read_window_ns >= 0


def test_ns_to_utc_iso_truncates_to_microseconds():
    assert ns_to_utc_iso(0) == "1970-01-01T00:00:00+00:00"
    assert ns_to_utc_iso(WALL_NS) == datetime(2026, 1, 1, 0, 0, 0, 123456, tzinfo=timezone.utc).isoformat()


def test_offset_to_wall_time():
    anchor = ClockAnchor.capture(StepClock([]), lambda: WALL_NS)
    assert anchor.offset_ms_to_wall_ns(1.5) == WALL_NS + 1_500_000


def test_round_trip_and_validation():
    anchor = ClockAnchor.capture(StepClock([]), lambda: WALL_NS)
    assert ClockAnchor.from_dict(anchor.to_dict()) == anchor

    data = anchor.to_dict()
    with pytest.raises(ClockAnchorError, match="eksik"):
        ClockAnchor.from_dict({k: v for k, v in data.items() if k != "wall_time_ns"})
    with pytest.raises(ClockAnchorError, match="fazla"):
        ClockAnchor.from_dict({**data, "extra": 1})
    with pytest.raises(ClockAnchorError, match="uyuşmuyor"):
        ClockAnchor.from_dict({**data, "wall_time_utc": "2020-01-01T00:00:00+00:00"})
    with pytest.raises(ClockAnchorError, match="read_window_ns"):
        ClockAnchor.from_dict({**data, "read_window_ns": -1})
    with pytest.raises(ClockAnchorError, match="monotonic_ns"):
        ClockAnchor.from_dict({**data, "monotonic_ns": True})
    with pytest.raises(ClockAnchorError, match="wall_time_ns"):
        ClockAnchor.from_dict({**data, "wall_time_ns": 10**30})
    with pytest.raises(ClockAnchorError, match="nesne"):
        ClockAnchor.from_dict([1, 2])


# --- runner ---
class FakeClock:
    def __init__(self):
        self.now_ns = 5_000

    def __call__(self):
        return self.now_ns


class FakeTransport:
    def __init__(self, clock, ms=4):
        self._clock, self._ms = clock, ms

    def send(self, scenario, url, timeout_seconds):
        self._clock.now_ns += self._ms * 1_000_000
        return TransportResponse(200, 1)

    def close(self):
        pass


def make_runner(clock, wall_calls):
    def wall():
        wall_calls.append(clock.now_ns)
        return WALL_NS

    return ScenarioRunner(FakeTransport(clock), "http://h", "r1", 1.0, sleep=lambda s: None,
                          now=lambda: "2026-01-01T00:00:00+00:00", clock=clock, wall_clock=wall)


def test_runner_anchor_is_taken_once_at_origin():
    clock, wall_calls = FakeClock(), []
    runner = make_runner(clock, wall_calls)
    assert runner.clock_anchor is None
    first = runner.run(Scenario(name="a", method="GET", path="/a", repetitions=2))
    second = runner.run(Scenario(name="b", method="GET", path="/b"))
    anchor = runner.clock_anchor
    assert wall_calls == [5_000]  # yalnızca ilk run() başında, istekten önce
    assert anchor.monotonic_ns == 5_000 and anchor.wall_time_ns == WALL_NS
    assert [r.offset_ms for r in first + second] == [0.0, 4.0, 8.0]  # offset'ler çapanın monotonik değerine göre
    assert anchor.offset_ms_to_wall_ns(second[0].offset_ms) == WALL_NS + 8_000_000


def test_execute_run_writes_clock_metadata(tmp_path):
    clock = FakeClock()
    config = LabConfig(base_url="http://127.0.0.1:8080", output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json")
    execute_run(config, [Scenario(name="a", method="GET", path="/a")], config_path=None, run_id="r1",
                resolver=lambda h, p: ["127.0.0.1"], transport_factory=lambda: FakeTransport(clock), clock=clock,
                now=lambda: "2026-01-01T00:00:00+00:00", sleep=lambda s: None,
                code={"git_commit": None, "git_dirty": None}, wall_clock=lambda: WALL_NS)
    meta = ResultStore(tmp_path / "results").load_json("r1").metadata
    anchor = ClockAnchor.from_dict(meta["clock"])
    assert anchor.wall_time_ns == WALL_NS and anchor.monotonic_ns == 5_000 and anchor.read_window_ns == 0
    assert anchor.monotonic_source.endswith("FakeClock")
