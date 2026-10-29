"""N11 birim testleri: test süreci yalıtım koruması (isolation_guard.py) ve ayrılmış portlar (target_guard.py).

Gerçek soket bağlantısı kurulmaz: koruma kararı sahte bir "gerçek connect" ile sınanır; ayrılmış port denetimi
bağlantıdan önce reddettiği için hiçbir soket açılmaz (açılmaya çalışılsaydı conftest'teki koruma da engellerdi).
"""

import isolation_guard
import pytest

from hgs2_lab import execution
from hgs2_lab.config import LabConfig
from hgs2_lab.execution import PreflightError, execute_run
from hgs2_lab.http_transport import RequestsTransport, _guarded_pool_classes
from hgs2_lab.scenarios import Scenario
from hgs2_lab.target_guard import RESERVED_PORTS, TargetNotAllowed, check_not_reserved_port

GET = Scenario(name="s", method="GET", path="/x")


def loopback(host, port):
    return ["127.0.0.1"]


# --- süreç içi yalıtım kararı ---
@pytest.mark.parametrize(
    "address, allowed",
    [
        (("127.0.0.1", 50000), True),
        (("::1", 50000, 0, 0), True),
        (("::ffff:127.0.0.1", 50000), True),
        (("127.0.0.1", 8080), False),  # gerçek HGS2 portu: bu süreçte bind edilmedi
        (("127.0.0.1", 5432), False),  # PostgreSQL
        (("203.0.113.5", 50000), False),  # loopback değil
        (("localhost", 50000), False),  # ad değil, çözümlenmiş IP beklenir
        (("127.0.0.1", "50000"), False),
        (("127.0.0.1", True), False),
        ("/tmp/sock", False),
        ((), False),
    ],
)
def test_connection_allowed_only_to_loopback_ports_bound_in_this_process(address, allowed):
    assert isolation_guard.connection_allowed(address, {50000}) is allowed


def test_guard_never_calls_real_connect_for_out_of_process_target():
    calls, record = [], []
    guarded = isolation_guard.make_guarded(lambda sock, addr: calls.append(addr), lambda: frozenset({50000}), record)
    with pytest.raises(isolation_guard.OutOfProcessConnectionBlocked, match="8080"):
        guarded(object(), ("127.0.0.1", 8080))
    assert calls == [] and [a for a, _ in record] == [("127.0.0.1", 8080)]
    guarded(object(), ("127.0.0.1", 50000))
    assert calls == [("127.0.0.1", 50000)] and len(record) == 1


def test_guard_is_installed_for_the_whole_session():
    import socket

    assert socket.socket.connect is isolation_guard.guarded_connect
    assert socket.socket.connect_ex is isolation_guard.guarded_connect_ex
    assert 8080 not in isolation_guard.bound_ports() and 5432 not in isolation_guard.bound_ports()


# --- ayrılmış portlar (gerçek HGS2 / PostgreSQL) ---
def test_reserved_ports_are_hgs2_server_and_database_ports():
    assert set(RESERVED_PORTS) == {8080, 5432}
    with pytest.raises(TypeError):
        RESERVED_PORTS[18080] = "x"  # değiştirilemez; açan ayar yok


@pytest.mark.parametrize("port", [8080, 5432])
def test_check_not_reserved_port_rejects(port):
    with pytest.raises(TargetNotAllowed, match=f"Port {port} ayrılmış"):
        check_not_reserved_port(port)


@pytest.mark.parametrize("port", [80, 443, 18080, 50000])
def test_other_ports_are_not_reserved(port):
    check_not_reserved_port(port)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/x", "http://localhost:8080/api/auth/kart-okut",
                                 "http://[::1]:8080/x", "http://127.0.0.1:5432/"])
def test_transport_refuses_reserved_port_before_any_connection(url):
    with RequestsTransport(resolver=lambda h, p: ["::1"] if h == "::1" else ["127.0.0.1"]) as transport:
        with pytest.raises(TargetNotAllowed, match="ayrılmış"):
            transport.send(GET, url, 5.0)


def test_connection_layer_refuses_reserved_port():
    connection_cls = _guarded_pool_classes(loopback)["http"].ConnectionCls
    with pytest.raises(TargetNotAllowed, match="ayrılmış"):
        connection_cls("127.0.0.1", 8080)._new_conn()


def test_run_against_reserved_port_is_rejected_before_any_request(tmp_path, monkeypatch):
    # N12: ayrılmış port artık çalıştırma başlamadan (verify_target) reddedilir: istek yok, dosya yok.
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})
    (tmp_path / "scenarios.json").write_text('{"scenarios": []}', encoding="utf-8")
    config = LabConfig(base_url="http://127.0.0.1:8080", output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json")
    lookups = []
    with pytest.raises(PreflightError, match="Port 8080 ayrılmış"):
        execute_run(config, [Scenario(name="a", method="POST", path="/api/auth/kart-okut", repetitions=2)],
                    config_path=None, resolver=loopback, listener_lookup=lambda port: lookups.append(port) or [])
    assert lookups == []  # ayrılmış port dinleyici okunmadan reddedilir
    assert not (tmp_path / "results").exists()
