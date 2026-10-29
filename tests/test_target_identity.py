"""N12 (F-3) birim testleri: hedef dinleyici kimliği politikası, doğrulayıcı, taşıyıcı, bağlantı katmanı, çalıştırma
akışı, yapılandırma ve test oturumu korumasının bırakılmış port kararı.

Gerçek soket bağlantısı kurulmaz ve işletim sistemi tablosu okunmaz: dinleyici okuyucusu sahtedir.
"""

import json
import os

import isolation_guard
import pytest

from hgs2_lab import execution
from hgs2_lab.config import ConfigError, LabConfig, load_config
from hgs2_lab.execution import PreflightError, execute_run
from hgs2_lab.http_transport import RequestsTransport, _guarded_pool_classes, _ListenerVerifier
from hgs2_lab.scenarios import Scenario
from hgs2_lab.target_guard import (
    LISTENER_DECLARED_EXTERNAL,
    LISTENER_IN_PROCESS,
    ListenerOwner,
    TargetNotAllowed,
    check_listener,
)
from hgs2_lab.target_process import REFUSED_PROCESS_NAMES, validate_target_process

OWN = os.getpid()
OTHER = OWN + 1 if OWN + 1 != 4 else OWN + 2


def owner(pid=OWN, name="python.exe", address="127.0.0.1"):
    return ListenerOwner(pid=pid, process_name=name, address=address)


def loopback(host, port):
    return ["127.0.0.1"]


# --- politika ---
@pytest.mark.parametrize(
    "owners, target_process, expected",
    [
        ([owner()], None, LISTENER_IN_PROCESS),
        ([owner(), owner(address="::1")], None, LISTENER_IN_PROCESS),
        ([owner(OTHER, "python.exe")], "python.exe", LISTENER_DECLARED_EXTERNAL),
        ([owner(OTHER, "Python.EXE")], "python.exe", LISTENER_DECLARED_EXTERNAL),
    ],
)
def test_listener_allowed(owners, target_process, expected):
    assert check_listener(50000, owners, own_pid=OWN, target_process=target_process) == expected


@pytest.mark.parametrize(
    "owners, target_process, match",
    [
        ([], None, "dinleyen süreç bulunamadı"),
        ([owner(OTHER, "python.exe")], None, "target_process"),  # dış süreç bildirilmedi
        ([owner(OTHER, "node.exe")], "python.exe", "eşleşmiyor"),
        ([owner(OTHER, None)], "python.exe", "adı okunamadı"),  # ör. hizmet olarak çalışan süreç
        ([owner(OTHER, "java.exe", "0.0.0.0")], "java.exe", "JVM/PostgreSQL"),  # HGS2: bildirilse bile reddedilir
        ([owner(OTHER, "javaw.exe")], None, "JVM/PostgreSQL"),
        ([owner(OTHER, "postgres.exe")], "postgres.exe", "JVM/PostgreSQL"),
        ([owner(), owner(OTHER, "java.exe", "::")], None, "JVM/PostgreSQL"),  # aynı portta bizim ve başkasının dinleyicisi
    ],
)
def test_listener_refused(owners, target_process, match):
    with pytest.raises(TargetNotAllowed, match=match):
        check_listener(50000, owners, own_pid=OWN, target_process=target_process)


@pytest.mark.parametrize("name", ["python.exe", "python", "my-server_1.exe"])
def test_valid_target_process_names(name):
    assert validate_target_process(name) == name


@pytest.mark.parametrize("name", ["", "a" * 65, "C:\\x\\python.exe", "py thon.exe", 5, None, *REFUSED_PROCESS_NAMES,
                                  "JAVA.EXE"])
def test_invalid_or_refused_target_process_names(name):
    with pytest.raises(ValueError):
        validate_target_process(name)


# --- doğrulayıcı ---
def test_verifier_caches_verified_port_and_rereads_when_no_listener():
    calls, answers = [], {50000: [owner()], 50001: []}
    verifier = _ListenerVerifier(lambda port: calls.append(port) or answers[port], None)
    assert verifier.verify(50000, require_listener=True) == LISTENER_IN_PROCESS
    assert verifier.verify(50000, require_listener=False) == LISTENER_IN_PROCESS
    assert calls == [50000]  # önbellek: ölçüme ek okuma girmez
    assert verifier.verify(50001, require_listener=False) is None  # dinleyici yok: bağlantı işletim sisteminde reddedilir
    assert verifier.verify(50001, require_listener=False) is None and calls == [50000, 50001, 50001]  # önbelleğe girmez
    with pytest.raises(TargetNotAllowed, match="dinleyen süreç bulunamadı"):
        verifier.verify(50001, require_listener=True)


def test_verifier_lookup_failure_is_not_allowed():
    def broken(port):
        raise OSError("tablo okunamadı")

    with pytest.raises(TargetNotAllowed, match="okunamadı"):
        _ListenerVerifier(broken, None).verify(50000, require_listener=False)


# --- taşıyıcı ve bağlantı katmanı ---
def test_verify_target_checks_name_resolution_reserved_port_and_listener():
    lookups = []
    transport = RequestsTransport(resolver=loopback, listener_lookup=lambda p: lookups.append(p) or [owner()])
    with transport:
        assert transport.verify_target("http://127.0.0.1:50000/") == {"port": 50000, "listener": LISTENER_IN_PROCESS}
        with pytest.raises(TargetNotAllowed, match="ayrılmış"):
            transport.verify_target("http://127.0.0.1:8080/")
        with pytest.raises(TargetNotAllowed):
            transport.verify_target("http://203.0.113.5:50000/")
    assert lookups == [50000]  # reddedilen hedeflerde tablo hiç okunmadı


def test_verify_target_refuses_undeclared_and_jvm_listeners():
    with RequestsTransport(resolver=loopback, listener_lookup=lambda p: [owner(OTHER, "python.exe")]) as transport:
        with pytest.raises(TargetNotAllowed, match="target_process"):
            transport.verify_target("http://127.0.0.1:18080/")
    declared = RequestsTransport(resolver=loopback, listener_lookup=lambda p: [owner(OTHER, "python.exe")],
                                 target_process="python.exe")
    with declared:
        assert declared.verify_target("http://localhost:18080/")["listener"] == LISTENER_DECLARED_EXTERNAL
    with RequestsTransport(resolver=loopback, listener_lookup=lambda p: [owner(OTHER, "java.exe", "0.0.0.0")],
                           target_process="python.exe") as hgs2_like:
        with pytest.raises(TargetNotAllowed, match="JVM/PostgreSQL"):
            hgs2_like.verify_target("http://127.0.0.1:18080/")


def test_connection_layer_refuses_external_listener_before_opening_a_socket():
    verifier = _ListenerVerifier(lambda port: [owner(OTHER, "java.exe", "0.0.0.0")], None)
    connection_cls = _guarded_pool_classes(loopback, verifier)["http"].ConnectionCls
    with pytest.raises(TargetNotAllowed, match="JVM/PostgreSQL"):
        connection_cls("127.0.0.1", 18080)._new_conn()  # soket açılsaydı oturum koruması ayrıca engellerdi


# --- çalıştırma akışı ---
def _config(tmp_path, port, **extra):
    (tmp_path / "scenarios.json").write_text('{"scenarios": []}', encoding="utf-8")
    return LabConfig(base_url=f"http://127.0.0.1:{port}", output_dir=tmp_path / "results",
                     scenarios_file=tmp_path / "scenarios.json", **extra)


@pytest.mark.parametrize(
    "owners, extra, match",
    [
        ([], {}, "dinleyen süreç bulunamadı"),
        ([owner(OTHER, "java.exe", "0.0.0.0")], {}, "JVM/PostgreSQL"),  # gerçek HGS2'nin başka bir portta çalışması
        ([owner(OTHER, "java.exe", "0.0.0.0")], {"target_process": "python.exe"}, "JVM/PostgreSQL"),
        ([owner(OTHER, "python.exe")], {}, "target_process"),
    ],
)
def test_run_is_rejected_before_any_request_when_listener_is_not_verified(tmp_path, monkeypatch, owners, extra, match):
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})
    lookups = []
    with pytest.raises(PreflightError, match=match):
        execute_run(_config(tmp_path, 18081, **extra), [Scenario(name="a", method="POST", path="/api/auth/kart-okut")],
                    config_path=None, resolver=loopback, listener_lookup=lambda p: lookups.append(p) or owners)
    assert lookups == [18081] and not (tmp_path / "results").exists()


def test_fake_transports_are_not_listener_checked(tmp_path, monkeypatch):
    """Sahte taşıyıcı ağ kullanmaz (verify_target yok): mevcut birim testleri ve davranış değişmez."""
    from hgs2_lab.transport import TransportResponse

    class Fake:
        def send(self, scenario, url, timeout_seconds):
            return TransportResponse(200, 2, 1.0, body=b"OK", content_type="text/plain")

        def close(self):
            pass

    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})
    outcome = execute_run(_config(tmp_path, 8080), [Scenario(name="a", method="GET", path="/x")], config_path=None,
                          resolver=loopback, transport_factory=Fake,
                          listener_lookup=lambda p: pytest.fail("sahte taşıyıcıda dinleyici okunmamalı"))
    assert outcome.completed
    assert "target_verification" not in json.loads(outcome.json_path.read_text(encoding="utf-8"))["execution"]


# --- yapılandırma (yüklemedeki ön denetim) ---
def test_config_target_process_is_optional_validated_and_recorded_only_when_given(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"base_url": "http://127.0.0.1:18080", "target_process": "python.exe"}),
                    encoding="utf-8")
    config = load_config(path)
    assert config.target_process == "python.exe" and config.to_dict()["target_process"] == "python.exe"
    assert "target_process" not in LabConfig(base_url="http://127.0.0.1:18080").to_dict()  # eski çıktılar değişmez
    for bad in ("java.exe", "javaw", "postgres.exe", "a b", 3):
        path.write_text(json.dumps({"base_url": "http://127.0.0.1:18080", "target_process": bad}), encoding="utf-8")
        with pytest.raises(ConfigError, match="target_process"):
            load_config(path)


# --- test oturumu koruması: bırakılmış port ---
@pytest.mark.parametrize(
    "address, released, free, allowed",
    [
        (("127.0.0.1", 50001), {50001}, True, True),  # kapalı test sunucusu, kimse dinlemiyor: işletim sistemi reddeder
        (("127.0.0.1", 50001), {50001}, False, False),  # bırakılan portu başka bir süreç dinliyor (gerçek HGS2 olabilir)
        (("127.0.0.1", 50002), {50001}, True, False),  # bu süreçte hiç açılmamış port
        (("203.0.113.5", 50001), {50001}, True, False),  # loopback değil
    ],
)
def test_released_port_allowed_only_when_nobody_listens(address, released, free, allowed):
    assert isolation_guard.connection_allowed(address, {50000}, released=released,
                                              no_listener=lambda port: free) is allowed


def test_port_has_no_listener_fails_closed_when_table_unreadable():
    def broken(port):
        raise OSError("okunamadı")

    assert isolation_guard.port_has_no_listener(50000, broken) is False
    assert isolation_guard.port_has_no_listener(50000, lambda p: []) is True
    assert isolation_guard.port_has_no_listener(50000, lambda p: [owner(OTHER, "java.exe")]) is False


def test_closing_a_socket_moves_its_port_from_open_to_released():
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))  # yalnızca bind; dinleme ve bağlantı yok
    port = sock.getsockname()[1]
    assert port in isolation_guard.bound_ports() and port not in isolation_guard.released_ports()
    sock.close()
    assert port not in isolation_guard.bound_ports() and port in isolation_guard.released_ports()
