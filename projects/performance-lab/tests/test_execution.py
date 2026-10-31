"""execute_run birim testleri: sahte taşıyıcı, sahte saat, sahte çözümleyici; ağ yok. Gizli değerler sahtedir."""

import json
import re
import socket

import pytest
from factories import make_failed_result, make_result

from hgs2_lab.config import LabConfig, RunLimits
from hgs2_lab.execution import (
    STATUS_ABORTED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    PreflightError,
    execute_run,
    generate_run_id,
    minimum_duration_seconds,
    planned_request_count,
    summarize,
)
from hgs2_lab.models import validate_run_id
from hgs2_lab.scenarios import Scenario
from hgs2_lab.storage import ResultStore
from hgs2_lab.target_guard import TargetNotAllowed
from hgs2_lab.transport import TransportConnectionError, TransportResponse, TransportTimeout

FAKE = "FAKE-SECRET-123"
CODE = {"git_commit": None, "git_dirty": None}
LOOPBACK = lambda host, port: ["127.0.0.1"]  # noqa: E731


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


class FakeClock:
    def __init__(self):
        self.now_ns = 1_000

    def __call__(self):
        return self.now_ns

    def advance_ms(self, ms):
        self.now_ns += int(ms * 1_000_000)


class FakeTransport:
    """outcomes: (geçen_ms, TransportResponse | istisna); tükenirse 200 döner."""

    def __init__(self, clock, outcomes=()):
        self._clock = clock
        self._outcomes = list(outcomes)
        self.sent = []
        self.closed = False

    def send(self, scenario, url, timeout_seconds):
        self.sent.append(url)
        elapsed_ms, outcome = self._outcomes.pop(0) if self._outcomes else (1, TransportResponse(200, 2))
        self._clock.advance_ms(elapsed_ms)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


class Harness:
    def __init__(self, tmp_path, outcomes=(), base_url="http://127.0.0.1:8080", **limits):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.clock = FakeClock()
        self.transport = FakeTransport(self.clock, outcomes)
        self.factory_calls = 0
        self.config = LabConfig(
            base_url=base_url,
            timeout_seconds=2.0,
            output_dir=tmp_path / "results",
            scenarios_file=tmp_path / "scenarios.json",
            limits=RunLimits(**limits),
        )
        (tmp_path / "scenarios.json").write_text('{"scenarios": []}', encoding="utf-8")
        self.config_path = tmp_path / "config.json"
        self.config_path.write_text('{"base_url": "http://127.0.0.1:8080"}', encoding="utf-8")
        self.store = ResultStore(self.config.output_dir)

    def factory(self):
        self.factory_calls += 1
        return self.transport

    def run(self, scenarios, resolver=LOOPBACK, **kw):
        kw.setdefault("run_id", "r1")
        return execute_run(
            self.config, scenarios, config_path=self.config_path, resolver=resolver,
            transport_factory=self.factory, clock=self.clock, now=lambda: "2026-01-01T00:00:00+00:00",
            sleep=lambda s: self.clock.advance_ms(s * 1000), code=CODE, **kw,
        )


def scenario(name="s", **kw):
    base = dict(name=name, method="GET", path="/p", repetitions=1)
    base.update(kw)
    return Scenario(**base)


# --- başarılı çalıştırma ---
def test_completed_run_saves_results_and_metadata(tmp_path):
    h = Harness(tmp_path, [(10, TransportResponse(200, 3)), (20, TransportResponse(500, 4)),
                           (5, TransportTimeout("t")), (15, TransportResponse(201, 1))])
    scenarios = [scenario("a", repetitions=2, warmup_repetitions=1), scenario("b", expected_status=(201,))]
    outcome = h.run(scenarios, target_label="yerel")

    assert outcome.status == STATUS_COMPLETED and outcome.completed
    assert outcome.planned_requests == 4 and len(outcome.results) == 4
    assert h.transport.closed and h.factory_calls == 1
    assert outcome.csv_path.name == "r1.csv" and outcome.json_path.name == "r1.json"

    stored = h.store.load_json("r1")
    assert stored.results == outcome.results == h.store.load_csv("r1")
    meta = stored.metadata
    assert meta["run_id"] == "r1" and all(r.run_id == "r1" for r in stored.results)
    assert meta["target_label"] == "yerel"
    assert meta["monotonic_duration_ms"] == 50.0  # sahte saatle gerçek süre: 10+20+5+15
    assert meta["execution"] == {
        "status": "completed", "stop_reason": None, "message": None,
        "planned_requests": 4, "completed_requests": 4, "limits": RunLimits().to_dict(),
    }
    # HTTP 500 bir yanıttır, taşıma hatası değildir; timeout ise taşıma hatasıdır.
    assert (stored.results[2].status_code, stored.results[2].error_type) == (None, "timeout")
    assert (stored.results[1].status_code, stored.results[1].http_ok, stored.results[1].error_type) == (500, False, None)
    assert [r.warmup for r in stored.results] == [True, False, False, False]
    assert str(tmp_path) not in h.store.paths("r1")[1].read_text(encoding="utf-8")  # mutlak yol yok


def test_generated_run_id_is_safe_and_used(tmp_path):
    rid = generate_run_id()
    assert validate_run_id(rid) == rid and re.fullmatch(r"run-\d{8}T\d{6}Z-[0-9a-f]{6}", rid)
    h = Harness(tmp_path)
    outcome = h.run([scenario()], run_id=None)
    assert re.fullmatch(r"run-\d{8}T\d{6}Z-[0-9a-f]{6}", outcome.run_id)
    assert outcome.json_path.name == f"{outcome.run_id}.json"


# --- ön kontrol: hiçbir istek gönderilmez ---
@pytest.mark.parametrize("base_url", ["http://203.0.113.5:8080", "http://[2001:db8::1]:8080", "http://example.com"])
def test_non_loopback_targets_rejected_before_any_request(tmp_path, base_url):
    h = Harness(tmp_path, base_url=base_url)
    with pytest.raises(PreflightError, match="Hedef reddedildi"):
        h.run([scenario()])
    assert h.factory_calls == 0 and h.transport.sent == []
    assert not (tmp_path / "results").exists()


def test_dns_resolving_outside_loopback_rejected_before_any_request(tmp_path):
    h = Harness(tmp_path, base_url="http://localhost:8080")
    with pytest.raises(PreflightError, match="loopback dışı"):
        h.run([scenario()], resolver=lambda host, port: ["127.0.0.1", "203.0.113.5"])
    assert h.factory_calls == 0


def test_request_budget_counts_warmups_and_rejects_before_any_request(tmp_path):
    scenarios = [scenario("a", repetitions=3, warmup_repetitions=2), scenario("b", repetitions=2)]
    assert planned_request_count(scenarios) == 7
    h = Harness(tmp_path, max_requests=6)
    with pytest.raises(PreflightError, match="İstek bütçesi aşıldı: planlanan 7"):
        h.run(scenarios)
    assert h.factory_calls == 0 and h.transport.sent == []
    assert Harness(tmp_path / "ok", max_requests=7).run(scenarios).planned_requests == 7  # sınırda izinli


def test_delays_exceeding_duration_budget_rejected_before_any_request(tmp_path):
    scenarios = [scenario(repetitions=4, warmup_repetitions=1, delay_seconds=3.0)]
    assert minimum_duration_seconds(scenarios) == 12.0
    h = Harness(tmp_path, max_duration_seconds=10.0)
    with pytest.raises(PreflightError, match="Süre bütçesi"):
        h.run(scenarios)
    assert h.factory_calls == 0


def test_existing_output_is_not_overwritten_and_nothing_is_sent(tmp_path):
    h = Harness(tmp_path)
    h.config.output_dir.mkdir()
    existing = h.config.output_dir / "r1.partial.json"
    existing.write_text("eski", encoding="utf-8")
    with pytest.raises(PreflightError, match="r1.partial.json"):
        h.run([scenario()])
    assert existing.read_text(encoding="utf-8") == "eski"
    assert h.factory_calls == 0


@pytest.mark.parametrize("kw", [{"target_label": ""}, {"target_label": 5}, {"run_id": "../x"}])
def test_invalid_label_or_run_id_rejected_before_any_request(tmp_path, kw):
    h = Harness(tmp_path)
    with pytest.raises(PreflightError):
        h.run([scenario()], **kw)
    assert h.factory_calls == 0


def test_empty_scenarios_rejected(tmp_path):
    with pytest.raises(PreflightError, match="senaryo yok"):
        Harness(tmp_path).run([])


# --- kontrollü durdurma ---
def test_consecutive_timeouts_stop_the_run_and_save_partial_results(tmp_path):
    h = Harness(tmp_path, [(100, TransportTimeout("t"))] * 5, max_consecutive_transport_errors=2)
    outcome = h.run([scenario(repetitions=5)])
    assert outcome.status == STATUS_ABORTED and not outcome.completed
    assert outcome.stop_reason == "consecutive_transport_errors"
    assert len(h.transport.sent) == 2 and h.transport.closed
    assert outcome.json_path.name == "r1.partial.json" and outcome.csv_path.name == "r1.partial.csv"
    assert not h.store.paths("r1")[1].exists()  # tamamlanmış gibi görünen dosya yok
    stored = h.store.load_json("r1", partial=True)
    assert stored.metadata["execution"]["status"] == "aborted"
    assert stored.metadata["execution"]["completed_requests"] == 2
    assert stored.metadata["execution"]["planned_requests"] == 5
    assert h.store.load_csv("r1", partial=True) == stored.results


def test_http_errors_do_not_count_as_consecutive_transport_errors_but_count_for_error_rate(tmp_path):
    outcomes = [(1, TransportResponse(200))] + [(1, TransportResponse(500))] * 9
    h = Harness(tmp_path, outcomes, max_consecutive_transport_errors=2, error_rate_min_requests=4, max_error_rate=0.5)
    outcome = h.run([scenario(repetitions=10)])
    assert outcome.stop_reason == "error_rate"  # 3/4 = 0.75 > 0.5 (ardışık taşıma hatası değil)
    assert len(outcome.results) == 4
    assert all(r.error_type is None for r in outcome.results)


def test_error_rate_is_not_evaluated_before_minimum_requests(tmp_path):
    h = Harness(tmp_path, [(1, TransportResponse(500))] * 3, error_rate_min_requests=20)
    assert h.run([scenario(repetitions=3)]).status == STATUS_COMPLETED


def test_duration_limit_stops_before_starting_new_request(tmp_path):
    h = Harness(tmp_path, [(600, TransportResponse(200))] * 5, max_duration_seconds=1.0)
    outcome = h.run([scenario(repetitions=5)])
    assert outcome.stop_reason == "duration_limit"
    assert len(h.transport.sent) == 2  # 0 ms ve 600 ms'de başladı; 1200 ms'de yeni istek yok


def test_keyboard_interrupt_saves_partial_results_and_closes_transport(tmp_path):
    h = Harness(tmp_path, [(1, TransportResponse(200)), (1, TransportResponse(200)), (1, KeyboardInterrupt())])
    outcome = h.run([scenario(repetitions=5)])
    assert outcome.status == STATUS_INTERRUPTED and outcome.stop_reason == "keyboard_interrupt"
    assert h.transport.closed
    assert len(outcome.results) == 2  # kesilen istek kaydedilmez
    stored = h.store.load_json("r1", partial=True)
    assert stored.metadata["execution"]["status"] == "interrupted"
    assert stored.metadata["monotonic_duration_ms"] == 3.0


def test_unexpected_error_saves_partial_results_then_propagates(tmp_path):
    h = Harness(tmp_path, [(1, TransportResponse(200)), (1, RuntimeError("bug"))])
    with pytest.raises(RuntimeError, match="bug"):
        h.run([scenario(repetitions=3)])
    assert h.transport.closed
    execution = h.store.load_json("r1", partial=True).metadata["execution"]
    assert (execution["status"], execution["stop_reason"], execution["message"]) == (STATUS_FAILED, "unexpected_error", "RuntimeError")
    assert execution["completed_requests"] == 1


def test_target_rejected_at_connection_time_aborts_the_run(tmp_path):
    h = Harness(tmp_path, [(1, TransportResponse(200)), (0, TargetNotAllowed("'localhost' loopback dışı adrese çözümlendi"))])
    outcome = h.run([scenario(repetitions=3)])
    assert outcome.status == STATUS_ABORTED and outcome.stop_reason == "target_not_allowed"
    assert len(outcome.results) == 1 and h.transport.closed


# --- gizlilik ---
def test_sensitive_values_do_not_leak_into_result_files(tmp_path):
    error = TransportConnectionError(f"failed /p?token={FAKE} Bearer {FAKE}")
    h = Harness(tmp_path, [(1, TransportResponse(200)), (1, error)])
    scn = scenario(path=f"/p?page=1&token={FAKE}", repetitions=2, headers={"Authorization": f"Bearer {FAKE}"},
                   body=None)
    outcome = h.run([scn])
    for path in (outcome.csv_path, outcome.json_path):
        assert FAKE not in path.read_text(encoding="utf-8")
    assert outcome.results[0].url == "http://127.0.0.1:8080/p?page=1&token=***REDACTED***"
    assert h.transport.sent[0].endswith(f"token={FAKE}")  # istek ham değerle gider


def test_summarize_counts():
    results = [make_result(warmup=True), make_result(seq=2, duration_ms=10.0),
               make_result(seq=3, status_code=500, http_ok=False, duration_ms=30.0), make_failed_result(seq=4)]
    s = summarize(results)
    assert (s["total"], s["warmup"], s["measured"]) == (4, 1, 3)
    assert (s["http_ok"], s["http_unexpected"], s["transport_errors"]) == (2, 1, {"timeout": 1})
    assert (s["duration_ms_median"], s["duration_ms_min"], s["duration_ms_max"]) == (20.0, 10.0, 30.0)
    json.dumps(s)
