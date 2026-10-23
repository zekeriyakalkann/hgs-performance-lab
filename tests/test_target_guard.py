"""Hedef korumasının birim testleri. Ağ yok: herhangi bir soket bağlantısı girişimi testi başarısız kılar."""

import socket

import pytest
import requests

from hgs2_lab.http_transport import RequestsTransport, _guarded_pool_classes, _LoopbackOnlyAdapter
from hgs2_lab.scenarios import Scenario
from hgs2_lab.target_guard import (
    TargetNotAllowed,
    check_target,
    check_url,
    is_loopback_ip,
    resolve_loopback,
)


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


def fixed(*addresses):
    calls = []

    def resolver(host, port):
        calls.append((host, port))
        return list(addresses)

    resolver.calls = calls
    return resolver


GET = Scenario(name="s", method="GET", path="/x")


# --- URL metni ---
@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://127.0.0.1:8080/x", ("127.0.0.1", 8080)),
        ("http://localhost/x", ("localhost", 80)),
        ("https://LOCALHOST/x", ("localhost", 443)),
        ("http://[::1]:9000/x", ("::1", 9000)),
    ],
)
def test_allowed_urls(url, expected):
    assert check_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://203.0.113.5/x",  # loopback dışı IPv4
        "http://10.0.0.1/x",
        "http://[2001:db8::1]/x",  # loopback dışı IPv6
        "http://[::ffff:203.0.113.5]/x",
        "http://127.0.0.2/x",  # loopback ama izin listesinde değil
        "http://example.com/x",
        "http://localhost.example.com/x",
        "http://127.0.0.1.nip.io/x",
        "http://localhost./x",
        "http:///x",
    ],
)
def test_non_allowed_hosts_rejected(url):
    with pytest.raises(TargetNotAllowed):
        check_url(url)


@pytest.mark.parametrize("url", ["ftp://127.0.0.1/x", "file:///etc/passwd", "gopher://localhost/", "127.0.0.1/x", ""])
def test_unsupported_schemes_rejected(url):
    with pytest.raises(TargetNotAllowed, match="şema"):
        check_url(url)


def test_invalid_port_rejected():
    with pytest.raises(TargetNotAllowed):
        check_url("http://127.0.0.1:99999/x")


# --- IP sınıflandırması ---
@pytest.mark.parametrize("ip", ["127.0.0.1", "127.255.0.9", "::1", "::ffff:127.0.0.1"])
def test_loopback_ips(ip):
    assert is_loopback_ip(ip)


@pytest.mark.parametrize("ip", ["203.0.113.5", "0.0.0.0", "::", "::ffff:203.0.113.5", "fe80::1%3", "localhost", ""])
def test_non_loopback_ips(ip):
    assert not is_loopback_ip(ip)


# --- Çözümleme ---
def test_resolution_must_be_entirely_loopback():
    assert resolve_loopback("localhost", 80, fixed("::1", "127.0.0.1", "127.0.0.1")) == ["::1", "127.0.0.1"]
    with pytest.raises(TargetNotAllowed, match="203.0.113.5"):
        resolve_loopback("localhost", 80, fixed("127.0.0.1", "203.0.113.5"))  # tek bir dış adres yeter
    with pytest.raises(TargetNotAllowed, match="hiçbir"):
        resolve_loopback("localhost", 80, fixed())


def test_resolution_failure_is_rejected():
    def broken(host, port):
        raise socket.gaierror("çözümlenemedi")

    with pytest.raises(TargetNotAllowed, match="gaierror"):
        resolve_loopback("localhost", 80, broken)


def test_check_target_combines_text_and_resolution():
    resolver = fixed("203.0.113.5")
    with pytest.raises(TargetNotAllowed):
        check_target("http://localhost:8080/x", resolver)  # DNS loopback dışı döndürüyor
    assert resolver.calls == [("localhost", 8080)]
    unused = fixed("127.0.0.1")
    with pytest.raises(TargetNotAllowed):
        check_target("http://203.0.113.5/x", unused)
    assert unused.calls == []  # metin kontrolü çözümlemeden önce reddeder


# --- Taşıyıcı katmanı ---
@pytest.mark.parametrize(
    "url",
    ["http://203.0.113.5/x", "http://[2001:db8::1]/x", "ftp://127.0.0.1/x", "file:///etc/passwd", "http://example.com/x"],
)
def test_transport_rejects_before_any_connection(url):
    with RequestsTransport() as transport:
        with pytest.raises(TargetNotAllowed):
            transport.send(GET, url, 5.0)


def test_transport_rejects_localhost_resolving_outside_loopback():
    with RequestsTransport(resolver=fixed("203.0.113.5")) as transport:
        with pytest.raises(TargetNotAllowed, match="loopback dışı"):
            transport.send(GET, "http://localhost:8080/x", 5.0)


def test_transport_session_has_loopback_adapter_and_refuses_proxies():
    with RequestsTransport() as transport:
        adapter = transport._session.get_adapter("http://127.0.0.1/")
        assert isinstance(adapter, _LoopbackOnlyAdapter)
        assert transport._session.get_adapter("https://127.0.0.1/") is adapter
        with pytest.raises(TargetNotAllowed, match="Proxy"):
            adapter.proxy_manager_for("http://203.0.113.1:9")


@pytest.mark.parametrize("configure", [lambda s: None, lambda s: s.proxies.update({"http": "http://203.0.113.1:9"})])
def test_injected_session_must_not_trust_env_or_use_proxies(configure):
    session = requests.Session()
    configure(session)  # ilki: trust_env=True (varsayılan); ikincisi: ayrıca açık proxy
    try:
        with pytest.raises(ValueError, match="trust_env"):
            RequestsTransport(session=session)
    finally:
        session.close()


def test_connection_layer_rejects_non_loopback_resolution_before_connecting():
    # DNS rebinding: bağlantı anındaki çözümleme dış adres döndürürse soket açılmaz.
    connection_cls = _guarded_pool_classes(fixed("203.0.113.5"))["http"].ConnectionCls
    conn = connection_cls("localhost", 8080)
    with pytest.raises(TargetNotAllowed):
        conn._new_conn()
    assert conn.host == "localhost"  # özgün ad korunur
