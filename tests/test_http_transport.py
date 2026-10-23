"""RequestsTransport testleri: gerçek ağ yok; oturum ve yanıt sahte, hata sınıfları gerçek requests sınıfları."""

import json
from types import SimpleNamespace

import pytest
import requests
from urllib3.exceptions import ReadTimeoutError

from hgs2_lab import http_transport
from hgs2_lab.http_transport import RequestsTransport
from hgs2_lab.runner import ScenarioRunner
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import (
    TransportConnectionError,
    TransportError,
    TransportResponse,
    TransportTimeout,
)

URL = "http://h/p"


class FakeClock:
    def __init__(self):
        self.now_ns = 1_000

    def __call__(self):
        return self.now_ns

    def advance_ms(self, ms):
        self.now_ns += int(ms * 1_000_000)


class FakeResponse:
    def __init__(self, status_code=200, content=b"", read_error=None, clock=None, read_ms=0, close_ms=0):
        self.status_code = status_code
        self._content = content
        self._read_error = read_error
        self._clock = clock
        self._read_ms = read_ms
        self._close_ms = close_ms
        self.closed = False

    @property
    def content(self):
        if self._clock is not None:
            self._clock.advance_ms(self._read_ms)
        if self._read_error is not None:
            raise self._read_error
        return self._content

    def close(self):
        if self._clock is not None:
            self._clock.advance_ms(self._close_ms)
        self.closed = True


class FakeSession:
    """outcome: FakeResponse ya da fırlatılacak istisna."""

    def __init__(self, outcome, clock=None, request_ms=0):
        self._outcome = outcome
        self._clock = clock
        self._request_ms = request_ms
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self._clock is not None:
            self._clock.advance_ms(self._request_ms)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome

    def close(self):
        self.closed = True


def scenario(**kw):
    base = dict(name="s", method="GET", path="/p")
    base.update(kw)
    return Scenario(**base)


def make(outcome, **session_kw):
    clock = FakeClock()
    session = FakeSession(outcome, clock=clock, **session_kw)
    return RequestsTransport(session=session, clock=clock), session, clock


# 1. Başarılı GET
def test_successful_get():
    transport, session, _ = make(FakeResponse(200, b"hello"), request_ms=12)
    result = transport.send(scenario(), URL, 5.0)
    assert result == TransportResponse(status_code=200, size_bytes=5, duration_ms=12.0, body=b"hello")
    (method, url, kwargs), = session.calls
    assert (method, url) == ("GET", URL)
    assert kwargs["timeout"] == 5.0
    assert kwargs["data"] is None
    assert kwargs["headers"] == {}
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True


# 2. JSON gövdeli POST
def test_post_with_json_body():
    body = {"a": 1, "b": "çğ", "c": [1, 2]}
    transport, session, _ = make(FakeResponse(201, b"{}"))
    transport.send(scenario(method="POST", body=body), URL, 5.0)
    _, _, kwargs = session.calls[0]
    assert isinstance(kwargs["data"], bytes)
    assert json.loads(kwargs["data"]) == body
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert session.calls[0][0] == "POST"


def test_custom_content_type_is_not_duplicated():
    transport, session, _ = make(FakeResponse(200))
    transport.send(scenario(method="POST", body={"a": 1}, headers={"content-type": "application/vnd.x+json"}), URL, 5.0)
    headers = session.calls[0][2]["headers"]
    assert [k for k in headers if k.lower() == "content-type"] == ["content-type"]
    assert headers["content-type"] == "application/vnd.x+json"


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_all_supported_methods_are_forwarded(method):
    transport, session, _ = make(FakeResponse(200))
    transport.send(scenario(method=method), URL, 5.0)
    assert session.calls[0][0] == method


# 3. Desteklenmeyen metot
def test_unsupported_method_raises_and_sends_nothing():
    transport, session, _ = make(FakeResponse(200))
    fake = SimpleNamespace(method="TRACE", headers={}, body=None)
    with pytest.raises(ValueError, match="TRACE"):
        transport.send(fake, URL, 5.0)
    assert session.calls == []


# 4. HTTP 500 taşıma hatası değildir
def test_http_500_is_a_normal_response():
    transport, session, _ = make(FakeResponse(500, b"err"), request_ms=40)
    result = transport.send(scenario(), URL, 5.0)
    assert result.status_code == 500
    assert result.size_bytes == 3
    assert result.duration_ms == 40.0


# 5-7. Taşıma hatalarının sınıflandırılması
def test_connect_timeout_is_timeout_not_connection_error():
    transport, _, _ = make(requests.exceptions.ConnectTimeout("bağlanma zaman aşımı"))
    with pytest.raises(TransportTimeout) as info:
        transport.send(scenario(), URL, 5.0)
    assert not isinstance(info.value, TransportConnectionError)
    assert "ConnectTimeout" in str(info.value)
    assert isinstance(info.value.__cause__, requests.exceptions.ConnectTimeout)


def test_read_timeout():
    transport, _, _ = make(requests.exceptions.ReadTimeout("okuma zaman aşımı"))
    with pytest.raises(TransportTimeout, match="ReadTimeout"):
        transport.send(scenario(), URL, 5.0)


def test_connection_error():
    transport, _, _ = make(requests.exceptions.ConnectionError("reddedildi"))
    with pytest.raises(TransportConnectionError, match="ConnectionError"):
        transport.send(scenario(), URL, 5.0)


@pytest.mark.parametrize("exc", [requests.exceptions.SSLError("tls"), requests.exceptions.ProxyError("proxy")])
def test_ssl_and_proxy_errors_are_connection_errors(exc):
    transport, _, _ = make(exc)
    with pytest.raises(TransportConnectionError):
        transport.send(scenario(), URL, 5.0)


def test_read_timeout_while_reading_body_is_timeout():
    wrapped = requests.exceptions.ConnectionError(ReadTimeoutError(None, URL, "Read timed out"))
    response = FakeResponse(200, read_error=wrapped)
    transport, _, _ = make(response)
    with pytest.raises(TransportTimeout):
        transport.send(scenario(), URL, 5.0)
    assert response.closed


def test_connection_dropped_while_reading_body():
    response = FakeResponse(200, read_error=requests.exceptions.ChunkedEncodingError("kesildi"))
    transport, _, _ = make(response)
    with pytest.raises(TransportConnectionError):
        transport.send(scenario(), URL, 5.0)
    assert response.closed


def test_other_request_exceptions_become_generic_transport_error():
    response = FakeResponse(200, read_error=requests.exceptions.ContentDecodingError("bozuk gzip"))
    transport, _, _ = make(response)
    with pytest.raises(TransportError) as info:
        transport.send(scenario(), URL, 5.0)
    assert type(info.value) is TransportError
    assert info.value.error_type == "transport_error"


def test_long_error_messages_are_truncated():
    transport, _, _ = make(requests.exceptions.ConnectionError("x" * 5000))
    with pytest.raises(TransportConnectionError) as info:
        transport.send(scenario(), URL, 5.0)
    assert len(str(info.value)) <= 300


# 8. timeout aktarımı
def test_timeout_is_forwarded_as_float():
    transport, session, _ = make(FakeResponse(200))
    transport.send(scenario(), URL, 3.5)
    assert session.calls[0][2]["timeout"] == 3.5


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "5", None])
def test_invalid_timeout_rejected_before_request(bad):
    transport, session, _ = make(FakeResponse(200))
    with pytest.raises(ValueError):
        transport.send(scenario(), URL, bad)
    assert session.calls == []


# 9. Header ve body aktarımı
def test_headers_are_forwarded_as_a_copy():
    scn = scenario(headers={"X-Test": "1", "Accept": "application/json"})
    transport, session, _ = make(FakeResponse(200))
    transport.send(scn, URL, 5.0)
    sent = session.calls[0][2]["headers"]
    assert sent == {"X-Test": "1", "Accept": "application/json"}
    assert sent is not scn.headers
    assert "Content-Type" not in scn.headers  # senaryo değiştirilmez


def test_non_serializable_or_nan_body_propagates_without_request():
    for body in ({"a": float("nan")}, {"a": object()}):
        transport, session, _ = make(FakeResponse(200))
        with pytest.raises((ValueError, TypeError)):
            transport.send(scenario(method="POST", body=body), URL, 5.0)
        assert session.calls == []


# 10. Yanıt boyutu
@pytest.mark.parametrize(
    "content, expected",
    [(b"", 0), (b"abc", 3), ("çç".encode("utf-8") * 3, 12), (b"\x00" * 1000, 1000)],
)
def test_size_is_decoded_body_byte_count(content, expected):
    transport, _, _ = make(FakeResponse(200, content))
    result = transport.send(scenario(), URL, 5.0)
    assert result.size_bytes == expected
    assert result.body == content


# Süre ölçüm sınırı
def test_duration_covers_request_and_full_body_read():
    clock = FakeClock()
    response = FakeResponse(200, b"x", clock=clock, read_ms=5)
    session = FakeSession(response, clock=clock, request_ms=10)
    transport = RequestsTransport(session=session, clock=clock)
    assert transport.send(scenario(), URL, 5.0).duration_ms == 15.0


# 11. Beklenmeyen hatalar yutulmaz
@pytest.mark.parametrize("exc", [RuntimeError("bug"), KeyError("k"), TypeError("bug"), OSError("ham soket hatası")])
def test_unexpected_exceptions_from_request_propagate(exc):
    transport, _, _ = make(exc)
    with pytest.raises(type(exc)):
        transport.send(scenario(), URL, 5.0)


def test_unexpected_exception_while_reading_body_propagates_and_closes():
    response = FakeResponse(200, read_error=RuntimeError("bug"))
    transport, _, _ = make(response)
    with pytest.raises(RuntimeError):
        transport.send(scenario(), URL, 5.0)
    assert response.closed


@pytest.mark.parametrize(
    "exc",
    [requests.exceptions.InvalidURL("kötü"), requests.exceptions.MissingSchema("şema yok"),
     requests.exceptions.InvalidHeader("başlık")],
)
def test_input_errors_are_not_converted_to_transport_errors(exc):
    transport, _, _ = make(exc)
    with pytest.raises(type(exc)) as info:
        transport.send(scenario(), URL, 5.0)
    assert not isinstance(info.value, TransportError)


def test_response_is_closed_on_success():
    response = FakeResponse(200, b"x")
    transport, _, _ = make(response)
    transport.send(scenario(), URL, 5.0)
    assert response.closed


# Oturum yönetimi
def test_default_session_is_isolated_from_environment_and_has_no_retries():
    with RequestsTransport() as transport:  # oturum oluşturur; ağ erişimi yok
        session = transport._session
        assert session.trust_env is False
        assert session.get_adapter("http://example.invalid").max_retries.total == 0


def test_injected_session_is_not_closed_by_transport():
    session = FakeSession(FakeResponse(200))
    RequestsTransport(session=session).close()
    assert session.closed is False


# Runner entegrasyonu: RawResult uyumu
def make_runner(transport, clock):
    return ScenarioRunner(
        transport, base_url="http://h", run_id="r1", timeout_seconds=5.0,
        sleep=lambda s: None, now=lambda: "2026-01-01T00:00:00+00:00", clock=clock,
    )


def test_runner_http_500_record():
    transport, _, clock = make(FakeResponse(500, b"err"), request_ms=40)
    r = make_runner(transport, clock).run(scenario())[0]
    assert (r.status_code, r.http_ok, r.error_type, r.error) == (500, False, None, None)
    assert r.duration_ms == 40.0 and r.response_bytes == 3


def test_runner_timeout_and_connection_error_records():
    for exc, expected in (
        (requests.exceptions.ReadTimeout("t"), "timeout"),
        (requests.exceptions.ConnectionError("c"), "connection_error"),
    ):
        transport, _, clock = make(exc, request_ms=7)
        r = make_runner(transport, clock).run(scenario())[0]
        assert r.error_type == expected
        assert r.status_code is None and r.duration_ms is None and r.http_ok is None
        assert r.elapsed_ms == 7.0


def test_runner_does_not_swallow_programming_errors_from_real_transport():
    transport, _, clock = make(RuntimeError("bug"))
    with pytest.raises(RuntimeError):
        make_runner(transport, clock).run(scenario())


# elapsed_ms ile duration_ms ölçüm sınırları
class SlowJson:
    """http_transport içindeki `json` adının yerine geçer; serileştirme sahte saatte süre harcar."""

    def __init__(self, clock, ms):
        self._clock = clock
        self._ms = ms

    def dumps(self, *args, **kwargs):
        self._clock.advance_ms(self._ms)
        return json.dumps(*args, **kwargs)


def test_elapsed_includes_preparation_and_close_but_duration_does_not(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(http_transport, "json", SlowJson(clock, 3))  # hazırlık: 3 ms
    response = FakeResponse(200, b"ok", clock=clock, read_ms=5, close_ms=2)  # gövde: 5 ms, kapatma: 2 ms
    session = FakeSession(response, clock=clock, request_ms=10)  # istek: 10 ms
    transport = RequestsTransport(session=session, clock=clock)
    r = make_runner(transport, clock).run(scenario(method="POST", body={"a": 1}))[0]
    assert r.duration_ms == 15.0  # istek + gövdenin tamamı
    assert r.elapsed_ms == 20.0  # + hazırlık + kapatma
    assert r.elapsed_ms - r.duration_ms == 5.0
    assert response.closed


def test_elapsed_includes_preparation_on_timeout_while_duration_is_absent(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(http_transport, "json", SlowJson(clock, 3))
    session = FakeSession(requests.exceptions.ReadTimeout("t"), clock=clock, request_ms=7)
    transport = RequestsTransport(session=session, clock=clock)
    r = make_runner(transport, clock).run(scenario(method="POST", body={"a": 1}))[0]
    assert r.error_type == "timeout"
    assert r.elapsed_ms == 10.0  # hazırlık 3 + istek 7
    assert r.duration_ms is None
