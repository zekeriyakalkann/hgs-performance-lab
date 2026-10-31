"""Sentetik sunucu entegrasyon testleri: gerçek soket, yalnızca 127.0.0.1.

`pytest -m integration` ile seçilir. Her testte 127.0.0.1 dışına bağlantı girişimi, bağlantı kurulmadan
reddedilir (local_http_server.install_network_guard). Her test sonunda sunucunun temiz kapandığı
(dinleyen soket kapalı, iş parçacığı kalmamış) doğrulanır.
"""

import http.client
import socket
import threading
import time

import pytest
from local_http_server import install_network_guard

from hgs2_lab.synthetic import build_plan, parse_manifest
from hgs2_lab.synthetic_server import (
    MAX_BODY_BYTES,
    SyntheticServer,
    SyntheticServerError,
)

pytestmark = pytest.mark.integration

TIMEOUT_S = 0.3


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked:
        sock.close()
    assert attempts == []


def make_plan(*scenarios, timeout=TIMEOUT_S):
    return build_plan(parse_manifest({
        "manifest_version": 1, "experiment_id": "srv", "experiment_type": "fault_injection",
        "dataset_kind": "synthetic", "seed": 1, "timeout_seconds": timeout,
        "limits": {"max_consecutive_transport_errors": 10}, "scenarios": list(scenarios),
    }))


def scenario(name, fault, repetitions=1, **kw):
    return {"name": name, "repetitions": repetitions, "fault": fault, **kw}


@pytest.fixture
def started():
    servers = []

    def start(plan, **kw):
        srv = SyntheticServer(plan, **kw).start()
        servers.append(srv)
        return srv

    yield start
    for srv in servers:
        assert srv.stop() == []  # iş parçacığı kalmadı
        assert srv.is_closed and srv.snapshot()["errors"] == []


def request(srv, path, method="GET", body=None, timeout=5.0, declared_length=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=timeout)
    start = time.perf_counter()
    try:
        if declared_length is None:
            conn.request(method, path, body=body)
        else:  # yalnızca başlık: sunucu gövdeyi okumadan reddetmeli
            conn.putrequest(method, path)
            conn.putheader("Content-Length", str(declared_length))
            conn.endheaders()
        response = conn.getresponse()
        return response.status, response.read(), (time.perf_counter() - start) * 1000
    finally:
        conn.close()


# --- yaşam döngüsü ve bağlanma ---
def test_start_binds_loopback_ephemeral_port_and_stops_cleanly():
    srv = SyntheticServer(make_plan(scenario("ok", {"type": "none"})))
    with pytest.raises(SyntheticServerError, match="başlatılmadı"):
        srv.port
    srv.start()
    host, port = srv.bound_address
    assert host == "127.0.0.1" and port > 0 and srv.base_url == f"http://127.0.0.1:{port}"
    assert srv._httpd.socket.family == socket.AF_INET and srv._httpd.socket.getsockname()[0] == "127.0.0.1"
    with pytest.raises(SyntheticServerError, match="zaten"):
        srv.start()
    assert request(srv, "/synthetic/ok")[0] == 200
    assert srv.stop() == [] and srv.is_closed
    assert srv.stop() == []  # ikinci kez kapatmak güvenli
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()  # artık dinlemiyor


def test_context_manager_closes_server():
    with SyntheticServer(make_plan(scenario("ok", {"type": "none"}))) as srv:
        assert request(srv, "/synthetic/ok")[0] == 200
    assert srv.is_closed


def test_port_conflict_is_rejected_not_shared(started):
    plan = make_plan(scenario("ok", {"type": "none"}))
    first = started(plan)
    with pytest.raises(SyntheticServerError, match="kullanımda"):
        SyntheticServer(plan, port=first.port).start()
    assert request(first, "/synthetic/ok")[0] == 200  # ilk sunucu etkilenmedi


@pytest.mark.parametrize("kwargs, message", [
    ({"port": 80}, "port"), ({"port": -1}, "port"), ({"port": True}, "port"), ({"port": 70000}, "port"),
    ({"max_concurrent": 0}, "max_concurrent"), ({"max_concurrent": 1000}, "max_concurrent"),
])
def test_invalid_configuration_rejected(kwargs, message):
    with pytest.raises(SyntheticServerError, match=message):
        SyntheticServer(make_plan(scenario("ok", {"type": "none"})), **kwargs)
    with pytest.raises(SyntheticServerError, match="SyntheticPlan"):
        SyntheticServer({"entries": []})


# --- davranışlar ---
def test_normal_http_error_and_fixed_delay(started):
    srv = started(make_plan(
        scenario("ok", {"type": "none"}),
        scenario("err", {"type": "http_error", "status": 503}),
        scenario("slow", {"type": "fixed_delay", "delay_ms": 120}),
    ))
    assert request(srv, "/synthetic/ok")[:2] == (200, b"synthetic ok")
    assert request(srv, "/synthetic/err")[:2] == (503, b"synthetic error 503")
    status, _, client_ms = request(srv, "/synthetic/slow")
    assert status == 200 and client_ms >= 120  # istemci süresi enjekte edilen gecikmeyi içerir
    events = srv.snapshot()["events"]
    assert [(e["route"], e["planned_fault"], e["status_sent"], e["outcome"]) for e in events] == [
        ("ok", "none", 200, "responded"), ("err", "http_error", 503, "responded"),
        ("slow", "fixed_delay", 200, "responded")]
    assert events[2]["hold_ms_actual"] >= 120  # sunucu tarafı bekleme ayrı ölçülür


def test_random_delay_uses_planned_values(started):
    plan = make_plan(scenario("rnd", {"type": "random_delay", "min_delay_ms": 20, "max_delay_ms": 60}, repetitions=3))
    srv = started(plan)
    for _ in range(3):
        assert request(srv, "/synthetic/rnd")[0] == 200
    held = [e["hold_ms_actual"] for e in srv.snapshot()["events"]]
    planned = [e.delay_ms for e in plan.entries]
    assert all(h >= p for h, p in zip(held, planned))
    assert [e["hold_ms_planned"] for e in srv.snapshot()["events"]] == planned


def test_onset_after_switches_to_fault(started):
    srv = started(make_plan(scenario("late", {"type": "http_error", "status": 500, "onset_after": 2}, repetitions=4)))
    assert [request(srv, "/synthetic/late")[0] for _ in range(4)] == [200, 200, 500, 500]
    assert [e["route_index"] for e in srv.snapshot()["events"]] == [1, 2, 3, 4]


def test_connection_drop_is_a_transport_error(started):
    srv = started(make_plan(scenario("drop", {"type": "connection_drop"})))
    with pytest.raises((http.client.RemoteDisconnected, ConnectionError)):
        request(srv, "/synthetic/drop")
    assert srv.snapshot()["events"][0]["outcome"] == "dropped"


def test_timeout_fault_holds_longer_than_client_timeout(started):
    srv = started(make_plan(scenario("to", {"type": "timeout"})))
    with pytest.raises(TimeoutError):  # socket.timeout, Python 3.10+ TimeoutError'ın takma adıdır
        request(srv, "/synthetic/to", timeout=TIMEOUT_S)
    assert srv.snapshot()["events"][0]["planned_fault"] == "timeout"


@pytest.mark.parametrize("path, method, body, declared, status, reason", [
    ("/baska", "GET", None, None, 404, "unknown_route"),
    ("/synthetic/yok", "GET", None, None, 404, "unknown_route"),
    ("/synthetic/ok", "POST", b"{}", None, 405, "method_mismatch"),
    ("/synthetic/ok", "POST", None, MAX_BODY_BYTES + 1, 413, "body_too_large"),
])
def test_unexpected_requests_are_rejected_and_recorded(started, path, method, body, declared, status, reason):
    srv = started(make_plan(scenario("ok", {"type": "none"})))
    assert request(srv, path, method, body, declared_length=declared)[0] == status
    snap = srv.snapshot()
    assert snap["unexpected_requests"] == 1 and snap["events"][0]["reason"] == reason
    assert request(srv, "/synthetic/ok")[0] == 200  # plan girdisi tüketilmedi


def test_plan_exhausted_requests_are_rejected(started):
    srv = started(make_plan(scenario("ok", {"type": "none"})))
    assert [request(srv, "/synthetic/ok")[0] for _ in range(3)] == [200, 410, 410]
    snap = srv.snapshot()
    assert (snap["arrivals"], snap["unexpected_requests"]) == (3, 2)


def test_event_log_is_bounded(started):
    srv = started(make_plan(scenario("ok", {"type": "none"})), max_events=2)
    for _ in range(4):
        request(srv, "/synthetic/ok")
    snap = srv.snapshot()
    assert len(snap["events"]) == 2 and snap["dropped_events"] == 2 and snap["arrivals"] == 4


def test_concurrency_limit_rejects_extra_connections(started):
    srv = started(make_plan(scenario("ok", {"type": "none"})), max_concurrent=1)
    idle = socket.create_connection(("127.0.0.1", srv.port), timeout=5)  # istek göndermeyen bağlantı
    try:
        deadline = time.monotonic() + 5
        while srv._active < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        extra = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
        try:
            extra.settimeout(5)
            try:
                data = extra.recv(1)
            except ConnectionError:
                data = b""
            assert data == b""  # sunucu fazla bağlantıyı hemen kapattı
        finally:
            extra.close()
    finally:
        idle.close()
    reasons = [e["reason"] for e in srv.snapshot()["events"]]
    assert reasons == ["overload"]


def test_stop_releases_held_requests_promptly():
    srv = SyntheticServer(make_plan(scenario("to", {"type": "timeout"}), timeout=10.0)).start()  # 15 sn bekletme
    errors = []

    def client():
        try:
            request(srv, "/synthetic/to", timeout=20)
        except Exception as exc:  # noqa: BLE001 - sunucu kapanınca bağlantı yanıtsız kapanır
            errors.append(exc)

    thread = threading.Thread(target=client)
    thread.start()
    deadline = time.monotonic() + 5
    while not srv.snapshot()["events"] and time.monotonic() < deadline:
        time.sleep(0.01)
    start = time.monotonic()
    assert srv.stop() == []
    assert time.monotonic() - start < 3
    thread.join(5)
    assert not thread.is_alive() and errors
    assert srv.snapshot()["events"][0]["outcome"] == "stopped"


def test_hold_fields_over_real_socket_and_client_time_includes_hold(started):
    """Sunucu beklemesi (hold_ms_actual) ile istemcinin ölçtüğü toplam süre ayrı ölçülür; istemci beklemeyi kapsar."""
    plan = make_plan(scenario("ok", {"type": "none"}), scenario("d", {"type": "fixed_delay", "delay_ms": 30}))
    srv = started(plan)
    request(srv, "/synthetic/ok")
    _, _, client_ms = request(srv, "/synthetic/d")
    plain, delayed = srv.snapshot()["events"]
    assert plain["hold_ms_actual"] is None and plain["hold_started_ns"] is None
    assert delayed["hold_ms_planned"] == 30.0 and delayed["hold_ms_actual"] >= 30.0
    assert delayed["received_ns"] <= delayed["hold_started_ns"] < delayed["hold_ended_ns"] <= delayed["completed_ns"]
    assert client_ms >= delayed["hold_ms_actual"]  # istemci süresi = bekleme + istek/yanıt yolu
