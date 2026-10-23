import pytest

from hgs2_lab.models import InvalidRunId
from hgs2_lab.runner import ScenarioRunner
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import (
    TransportConnectionError,
    TransportError,
    TransportResponse,
    TransportTimeout,
)


class FakeClock:
    """Monotonik saat taklidi (ns). Süreyi yalnızca sahte taşıyıcı ilerletir."""

    def __init__(self):
        self.now_ns = 1_000

    def __call__(self):
        return self.now_ns

    def advance_ms(self, ms):
        self.now_ns += int(ms * 1_000_000)


class FakeTransport:
    """outcomes: (geçen_ms, TransportResponse | istisna) çiftleri."""

    def __init__(self, clock, outcomes):
        self._clock = clock
        self._outcomes = list(outcomes)
        self.calls = []

    def send(self, scenario, url, timeout_seconds):
        self.calls.append((url, timeout_seconds))
        elapsed_ms, outcome = self._outcomes.pop(0)
        self._clock.advance_ms(elapsed_ms)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def make_runner(outcomes, sleeps=None, timeout=7.5):
    clock = FakeClock()
    transport = FakeTransport(clock, outcomes)
    runner = ScenarioRunner(
        transport,
        base_url="http://h/",
        run_id="r1",
        timeout_seconds=timeout,
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
        now=lambda: "2026-01-01T00:00:00+00:00",
        clock=clock,
    )
    return runner, transport


def scenario(**kw):
    base = dict(name="s", method="GET", path="/p", repetitions=1)
    base.update(kw)
    return Scenario(**base)


def test_success_record_and_timeout_forwarded():
    runner, transport = make_runner([(20, TransportResponse(200, 10)), (25, TransportResponse(200, 12))])
    results = runner.run(scenario(repetitions=2))
    assert transport.calls == [("http://h/p", 7.5), ("http://h/p", 7.5)]
    assert [r.iteration for r in results] == [1, 2]
    r = results[0]
    assert (r.run_id, r.scenario, r.method, r.url) == ("r1", "s", "GET", "http://h/p")
    assert r.started_at == "2026-01-01T00:00:00+00:00"
    assert r.elapsed_ms == 20.0
    assert r.duration_ms == 20.0  # taşıyıcı süre bildirmedi, elapsed kullanılır
    assert r.status_code == 200 and r.http_ok is True
    assert r.error_type is None and r.error is None and r.business_outcome is None
    assert r.response_bytes == 10
    assert results[1].elapsed_ms == 25.0


def test_transport_reported_duration_is_kept_separate_from_elapsed():
    runner, _ = make_runner([(20, TransportResponse(200, duration_ms=15.0))])
    r = runner.run(scenario())[0]
    assert r.elapsed_ms == 20.0
    assert r.duration_ms == 15.0


def test_http_500_is_http_failure_not_transport_error():
    runner, _ = make_runner([(40, TransportResponse(500, 3))])
    r = runner.run(scenario())[0]
    assert r.status_code == 500
    assert r.http_ok is False
    assert r.error_type is None and r.error is None
    assert r.duration_ms == 40.0 and r.elapsed_ms == 40.0
    assert r.has_response and not r.succeeded


def test_scenario_specific_expected_status():
    runner, _ = make_runner([(1, TransportResponse(404)), (1, TransportResponse(200))])
    results = runner.run(scenario(repetitions=2, expected_status=(404,)))
    assert results[0].http_ok is True
    assert results[1].http_ok is False


def test_timeout_classified():
    runner, _ = make_runner([(7500, TransportTimeout("7.5s doldu"))])
    r = runner.run(scenario())[0]
    assert r.error_type == "timeout"
    assert r.error == "TransportTimeout: 7.5s doldu"
    assert r.elapsed_ms == 7500.0
    assert r.duration_ms is None and r.status_code is None and r.http_ok is None
    assert not r.has_response


def test_connection_error_classified():
    runner, _ = make_runner([(3, TransportConnectionError("reddedildi"))])
    r = runner.run(scenario())[0]
    assert r.error_type == "connection_error"
    assert r.elapsed_ms == 3.0
    assert r.duration_ms is None and r.status_code is None and r.http_ok is None


def test_generic_transport_error_classified():
    runner, _ = make_runner([(1, TransportError("bilinmeyen"))])
    assert runner.run(scenario())[0].error_type == "transport_error"


def test_http_500_and_connection_error_are_distinguishable():
    runner, _ = make_runner([(1, TransportResponse(500)), (1, TransportConnectionError("x"))])
    http_fail, conn_fail = runner.run(scenario(repetitions=2))
    assert http_fail.error_type is None and http_fail.status_code == 500
    assert conn_fail.error_type == "connection_error" and conn_fail.status_code is None


@pytest.mark.parametrize("exc", [RuntimeError("bug"), ValueError("bug"), KeyError("k"), TimeoutError("yerleşik")])
def test_unexpected_exceptions_are_not_swallowed(exc):
    runner, _ = make_runner([(1, exc)])
    with pytest.raises(type(exc)):
        runner.run(scenario())


def test_invalid_transport_response_surfaces_as_error():
    runner, _ = make_runner([(1, TransportResponse(42))])
    with pytest.raises(ValueError):
        runner.run(scenario())


def test_delay_between_iterations_but_not_after_last():
    sleeps = []
    runner, _ = make_runner([(1, TransportResponse(200))] * 3, sleeps)
    runner.run(scenario(repetitions=3, delay_seconds=0.5))
    assert sleeps == [0.5, 0.5]


def test_no_sleep_without_delay():
    sleeps = []
    runner, _ = make_runner([(1, TransportResponse(200))] * 2, sleeps)
    runner.run(scenario(repetitions=2))
    assert sleeps == []


def test_constructor_validates_run_id_and_timeout():
    clock = FakeClock()
    transport = FakeTransport(clock, [])
    with pytest.raises(InvalidRunId):
        ScenarioRunner(transport, "http://h", "../x", 1.0, clock=clock)
    for bad in (0, -1, float("nan"), float("inf"), True, "5"):
        with pytest.raises(ValueError):
            ScenarioRunner(transport, "http://h", "r1", bad, clock=clock)
