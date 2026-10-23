"""RequestsTransport'un gerçek bir yerel HTTP sunucusuna karşı entegrasyon testleri.

Varsayılan çalıştırmada hariçtir; `pytest -m integration` ile seçilir.

Ağ sınırı:
* Sunucu yalnızca 127.0.0.1'e, geçici bir porta bind eder (bkz. local_http_server.py).
* İstemci istekleri yalnızca bu sunucuya gider.
* `block_external_network` her testte `socket.socket.connect` ve `connect_ex`'i sarar:
  hedef 127.0.0.1 değilse bağlantı KURULMADAN ExternalNetworkBlocked fırlatılır ve adres
  kaydedilir. Sunucu tarafı işlemler (bind/listen/accept/close) etkilenmez.
* Proxy testlerinde ortam değişkenine yazılan 203.0.113.1 (RFC 5737 belge adresi)
  yalnızca bir değerdir; ona yönelik her bağlantı girişimi koruma tarafından engellenir.
"""

import json
import socket

import pytest
import requests
from local_http_server import (
    ERROR_BODY,
    GZIP_COMPRESSED,
    GZIP_PLAIN,
    HELLO_BODY,
    LOOPBACK,
    SLOW_BODY_DELAY_SECONDS,
    SLOW_BODY_PARTS,
    ExternalNetworkBlocked,
    LocalHTTPServer,
    install_network_guard,
)
from urllib3.exceptions import ReadTimeoutError

from hgs2_lab.http_transport import RequestsTransport
from hgs2_lab.runner import ScenarioRunner
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import TransportTimeout

pytestmark = pytest.mark.integration

SAFE_TIMEOUT = 5.0  # zaman aşımı beklenmeyen testlerde geniş pay
READ_TIMEOUT = 1.0  # zaman aşımı testlerinde istemci; sunucu en fazla 15 sn bekler (15 kat pay)
BLACKHOLE = ("203.0.113.1", 9)
BLACKHOLE_PROXY_URL = f"http://{BLACKHOLE[0]}:{BLACKHOLE[1]}"
PROXY_ENV_NAMES = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked_sockets = install_network_guard(monkeypatch)
    yield attempts
    # Reddedilen soketler hiçbir yere bağlanmadı; çağıran onları kapatmadığı için burada kapatılır.
    for sock in blocked_sockets:
        sock.close()  # kapalı sokette etkisizdir


@pytest.fixture(scope="module")
def _module_server():
    srv = LocalHTTPServer()
    assert srv.server_address[0] == LOOPBACK
    srv.start()
    yield srv
    leftovers = srv.stop()
    assert leftovers == [], f"Kapanmayan thread'ler: {leftovers}"
    assert srv.is_closed
    assert srv.unexpected_errors() == []


@pytest.fixture
def server(_module_server):
    _module_server.reset()
    yield _module_server
    _module_server.release_stalled()


@pytest.fixture
def transport():
    with RequestsTransport() as t:  # her test kendi oturumu/bağlantı havuzu
        yield t


@pytest.fixture
def hostile_proxy_env(monkeypatch, tmp_path):
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    for name in PROXY_ENV_NAMES:
        monkeypatch.setenv(name, BLACKHOLE_PROXY_URL)
    # trust_env=True kontrol testi kullanıcının gerçek .netrc dosyasını okumasın.
    monkeypatch.setenv("NETRC", str(tmp_path / "olmayan-netrc"))


def scenario(path, method="GET", **kw):
    return Scenario(name="it", method=method, path=path, **kw)


def send(transport, server, scn, timeout=SAFE_TIMEOUT):
    return transport.send(scn, server.base_url + scn.path, timeout)


def run_once(transport, server, scn, timeout=SAFE_TIMEOUT):
    (result,) = ScenarioRunner(transport, server.base_url, "it-run", timeout).run(scn)
    return result


def test_get_returns_body_and_size(server, transport):
    resp = send(transport, server, scenario("/hello"))
    assert resp.status_code == 200
    assert resp.body == HELLO_BODY
    assert resp.size_bytes == len(HELLO_BODY)
    assert resp.duration_ms > 0
    assert server.requests_seen() == [("GET", "/hello")]


def test_post_json_body_reaches_server(server, transport):
    body = {"a": 1, "metin": "çğüşöı", "liste": [1, 2]}
    resp = send(transport, server, scenario("/echo", method="POST", headers={"X-Test": "abc"}, body=body))
    assert resp.status_code == 200
    assert json.loads(resp.body) == {
        "method": "POST",
        "content_type": "application/json",
        "x_test": "abc",
        "body": body,
    }


def test_http_500_is_a_response_not_a_transport_error(server, transport):
    resp = send(transport, server, scenario("/error"))
    assert resp.status_code == 500
    assert resp.body == ERROR_BODY
    r = run_once(transport, server, scenario("/error"))
    assert (r.status_code, r.http_ok, r.error_type, r.error) == (500, False, None, None)
    assert r.duration_ms is not None
    assert r.response_bytes == len(ERROR_BODY)


def test_redirect_is_not_followed(server, transport):
    resp = send(transport, server, scenario("/redirect"))
    assert resp.status_code == 302
    assert server.requests_seen() == [("GET", "/redirect")]  # /hello hiç istenmedi
    assert run_once(transport, server, scenario("/redirect")).http_ok is False  # varsayılan beklenti 2xx
    assert run_once(transport, server, scenario("/redirect", expected_status=(302,))).http_ok is True
    assert ("GET", "/hello") not in server.requests_seen()


def test_delayed_body_is_inside_duration(server, transport):
    r = run_once(transport, server, scenario("/slow-body"))
    assert r.status_code == 200
    assert r.response_bytes == sum(len(part) for part in SLOW_BODY_PARTS)
    # Yalnızca alt sınır: yavaş makine testi bozmaz. %20 pay saat çözünürlüğü içindir.
    assert r.duration_ms >= SLOW_BODY_DELAY_SECONDS * 1000 * 0.8
    assert r.elapsed_ms >= r.duration_ms


def test_read_timeout_before_headers(server, transport):
    with pytest.raises(TransportTimeout) as info:
        send(transport, server, scenario("/stall-headers"), timeout=READ_TIMEOUT)
    cause = info.value.__cause__
    # Beklenen zincir: urllib3 ReadTimeoutError -> requests ReadTimeout -> TransportTimeout
    assert type(cause) is requests.exceptions.ReadTimeout, repr(cause)
    assert any(isinstance(arg, ReadTimeoutError) for arg in cause.args), cause.args


def test_read_timeout_record_via_runner(server, transport):
    r = run_once(transport, server, scenario("/stall-headers"), timeout=READ_TIMEOUT)
    assert r.error_type == "timeout"
    assert r.status_code is None and r.duration_ms is None and r.http_ok is None
    assert r.elapsed_ms >= READ_TIMEOUT * 1000 * 0.5  # yalnızca alt sınır


def test_read_timeout_while_reading_body(server, transport):
    with pytest.raises(TransportTimeout) as info:
        send(transport, server, scenario("/stall-body"), timeout=READ_TIMEOUT)
    cause = info.value.__cause__
    # Beklenen zincir: urllib3 ReadTimeoutError -> requests ConnectionError (Timeout DEĞİL) -> TransportTimeout.
    # Bu zincir, zaman aşımının başlıklardan sonra, gövde okunurken oluştuğunu da gösterir
    # (başlık öncesi zaman aşımı requests ReadTimeout olurdu).
    assert isinstance(cause, requests.exceptions.ConnectionError), repr(cause)
    assert not isinstance(cause, requests.exceptions.Timeout), repr(cause)
    assert any(isinstance(arg, ReadTimeoutError) for arg in cause.args), cause.args


def test_gzip_size_is_decoded_body_length(server, transport):
    assert len(GZIP_COMPRESSED) < len(GZIP_PLAIN)  # sunucu gerçekten sıkıştırılmış gövde gönderiyor
    resp = send(transport, server, scenario("/gzip"))
    assert resp.status_code == 200
    assert resp.body == GZIP_PLAIN
    assert resp.size_bytes == len(GZIP_PLAIN)


def test_environment_proxy_is_ignored(server, hostile_proxy_env, block_external_network):
    with RequestsTransport() as t:  # kendi oturumu: trust_env=False
        resp = send(t, server, scenario("/hello"))
    assert resp.status_code == 200
    assert server.requests_seen() == [("GET", "/hello")]
    assert block_external_network == []


def test_control_trust_env_session_would_use_proxy(server, hostile_proxy_env, block_external_network):
    """Kontrol: ortam proxy'si bu ortamda gerçekten etkin; trust_env=True olsaydı istek proxy'ye
    yönelirdi. Koruma bağlantıyı kurulmadan engeller. Bu test olmadan önceki test boşuna geçebilirdi.

    RequestsTransport artık trust_env=True bir oturumu kabul etmediği için kontrol düz requests ile yapılır."""
    session = requests.Session()  # trust_env=True (requests varsayılanı)
    try:
        with pytest.raises(ValueError, match="trust_env"):
            RequestsTransport(session=session)  # taşıyıcı bu oturumu reddeder
        with pytest.raises(ExternalNetworkBlocked):
            session.get(server.base_url + "/hello", timeout=SAFE_TIMEOUT)
    finally:
        session.close()
    assert block_external_network == [BLACKHOLE]
    assert server.requests_seen() == []


def test_network_guard_blocks_non_loopback_before_connecting(block_external_network):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(ExternalNetworkBlocked):
            s.connect(BLACKHOLE)
        with pytest.raises(ExternalNetworkBlocked):
            s.connect_ex(BLACKHOLE)
    assert block_external_network == [BLACKHOLE, BLACKHOLE]


def test_server_shutdown_closes_socket_and_threads():
    srv = LocalHTTPServer()
    srv.start()
    try:
        with RequestsTransport() as t:
            assert t.send(scenario("/hello"), srv.base_url + "/hello", SAFE_TIMEOUT).status_code == 200
            with pytest.raises(TransportTimeout):  # bekleyen bir handler bırakır
                t.send(scenario("/stall-body"), srv.base_url + "/stall-body", READ_TIMEOUT)
        assert srv.handler_threads(), "en az bir handler thread'i oluşmalıydı"
    finally:
        leftovers = srv.stop()
    assert leftovers == []
    assert srv.is_closed
    assert srv.unexpected_errors() == []
