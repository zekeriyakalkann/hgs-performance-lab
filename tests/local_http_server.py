"""Entegrasyon testleri için yerel HTTP sunucusu (yalnızca standart kütüphane).

Ağ sınırı:
* Yalnızca 127.0.0.1 adresine, işletim sisteminin atadığı geçici bir porta bind eder.
* Hiçbir giden bağlantı (connect) açmaz.
* `server_bind`, HTTPServer'ın yaptığı ters DNS sorgusunu (`socket.getfqdn`) yapmaz.

Kaynak yönetimi:
* Bekleten uçlar (`/stall-*`) sabit `sleep` yerine bir olay (Event) üzerinde en fazla
  STALL_MAX_SECONDS bekler; `release_stalled()` / `stop()` onları hemen serbest bırakır.
* Her handler thread'i kaydedilir; `stop()` sunucu soketini kapatır, thread'leri süre
  sınırıyla bekler ve hâlâ yaşayanları döndürür (boş liste = temiz kapanış).
"""

from __future__ import annotations

import gzip
import json
import socket
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOOPBACK = "127.0.0.1"
STALL_MAX_SECONDS = 15.0
SLOW_BODY_DELAY_SECONDS = 0.3
HANDLER_SOCKET_TIMEOUT = 5.0  # boşta kalan keep-alive bağlantısı en fazla bu kadar tutulur

HELLO_BODY = b"hello"
ERROR_BODY = b"boom"
SLOW_BODY_PARTS = (b"a" * 100, b"b" * 100)
STALL_BODY_PARTS = (b"12345", b"67890")
GZIP_PLAIN = b"hgs2-performance-lab " * 500
GZIP_COMPRESSED = gzip.compress(GZIP_PLAIN, mtime=0)


class ExternalNetworkBlocked(AssertionError):
    """Test, 127.0.0.1 dışındaki bir adrese bağlanmaya çalıştı."""


def install_network_guard(monkeypatch) -> tuple[list, list]:
    """`socket.socket.connect`/`connect_ex`'i sarar: hedef 127.0.0.1 değilse bağlantı KURULMADAN
    ExternalNetworkBlocked fırlatır ve adresi kaydeder. Sunucu tarafı (bind/listen/accept) etkilenmez.

    (girişimler, reddedilen soketler) döndürür. Çağıran kod (ör. urllib3 create_connection) soketi
    yalnızca OSError'da kapattığı için reddedilen soketler test bitince çağıran fixture'ca kapatılmalı.
    """
    attempts: list = []
    blocked_sockets: list = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def check(sock, address):
        if not (isinstance(address, tuple) and address and address[0] == LOOPBACK):
            attempts.append(address)
            blocked_sockets.append(sock)
            raise ExternalNetworkBlocked(f"127.0.0.1 dışına bağlantı engellendi: {address!r}")

    def guarded_connect(self, address):
        check(self, address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        check(self, address)
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    return attempts, blocked_sockets


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = HANDLER_SOCKET_TIMEOUT
    server: "LocalHTTPServer"

    def setup(self) -> None:
        self.server.track_handler_thread(threading.current_thread())
        super().setup()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - üst sınıf imzası
        pass  # test çıktısını kirletmesin

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        self.server.record_request(self.command, self.path)
        route = _ROUTES.get((self.command, urlsplit(self.path).path))  # sorgu dizgisi rota seçimini etkilemez
        try:
            if route is None:
                self._send(404, b"not found")
            else:
                route(self)
        except ConnectionError:
            # İstemci (ör. zaman aşımıyla) bağlantıyı kapattıktan sonra yazma girişimi: beklenen durum.
            self.close_connection = True

    def _send_head(self, status: int, length: int, content_type: str = "text/plain",
                   headers: tuple = (), close: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        for name, value in headers:
            self.send_header(name, value)
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()

    def _send(self, status: int, body: bytes, content_type: str = "text/plain",
              headers: tuple = (), close: bool = False) -> None:
        self._send_head(status, len(body), content_type, headers, close)
        self.wfile.write(body)


def _hello(h: _Handler) -> None:
    h._send(200, HELLO_BODY)


def _echo(h: _Handler) -> None:
    length = int(h.headers.get("Content-Length", "0"))
    raw = h.rfile.read(length) if length else b""
    payload = {
        "method": h.command,
        "content_type": h.headers.get("Content-Type"),
        "x_test": h.headers.get("X-Test"),
        "body": json.loads(raw) if raw else None,
    }
    h._send(200, json.dumps(payload).encode("utf-8"), "application/json")


def _error(h: _Handler) -> None:
    h._send(500, ERROR_BODY)


def _redirect(h: _Handler) -> None:
    h._send(302, b"", headers=(("Location", "/hello"),))


def _gzip(h: _Handler) -> None:
    h._send(200, GZIP_COMPRESSED, headers=(("Content-Encoding", "gzip"),))


def _slow_body(h: _Handler) -> None:
    first, second = SLOW_BODY_PARTS
    h._send_head(200, len(first) + len(second))
    h.wfile.write(first)
    h.wfile.flush()
    time.sleep(SLOW_BODY_DELAY_SECONDS)
    h.wfile.write(second)


def _stall_headers(h: _Handler) -> None:
    h.server.wait_for_release()  # başlıklar gönderilmeden bekler
    h._send(200, b"late", close=True)


def _stall_body(h: _Handler) -> None:
    first, second = STALL_BODY_PARTS
    h._send_head(200, len(first) + len(second), close=True)
    h.wfile.write(first)  # başlıklar ve gövdenin bir kısmı gider
    h.wfile.flush()
    h.server.wait_for_release()
    h.wfile.write(second)


_ROUTES = {
    ("GET", "/hello"): _hello,
    ("POST", "/echo"): _echo,
    ("GET", "/error"): _error,
    ("GET", "/redirect"): _redirect,
    ("GET", "/gzip"): _gzip,
    ("GET", "/slow-body"): _slow_body,
    ("GET", "/stall-headers"): _stall_headers,
    ("GET", "/stall-body"): _stall_body,
}


class LocalHTTPServer(ThreadingHTTPServer):
    # Takılı bir handler süreç çıkışını engellemesin; temiz kapanış stop() içinde doğrulanır.
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__((LOOPBACK, 0), _Handler)
        self._lock = threading.Lock()
        self._stall_gate = threading.Event()
        self._requests: list[tuple[str, str]] = []
        self._handler_threads: list[threading.Thread] = []
        self._errors: list[BaseException] = []
        self._serve_thread: threading.Thread | None = None

    def server_bind(self) -> None:
        # HTTPServer.server_bind, socket.getfqdn ile ters DNS sorgusu yapar; burada gereksiz.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://{LOOPBACK}:{self.port}"

    @property
    def is_closed(self) -> bool:
        return self.socket.fileno() == -1

    def start(self) -> None:
        self._serve_thread = threading.Thread(
            target=self.serve_forever, kwargs={"poll_interval": 0.05}, name="local-http-server", daemon=True
        )
        self._serve_thread.start()

    def stop(self, join_timeout: float = 10.0) -> list[threading.Thread]:
        """Sunucuyu kapatır; süre sınırı içinde sonlanmayan thread'leri döndürür."""
        self.release_stalled()
        if self._serve_thread is not None:
            self.shutdown()  # serve_forever döngüsünü durdurur
        self.server_close()  # dinleyen soketi kapatır
        threads = ([self._serve_thread] if self._serve_thread else []) + self.handler_threads()
        deadline = time.monotonic() + join_timeout
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return [t for t in threads if t.is_alive()]

    def reset(self) -> None:
        """Önceki testin bekleyen handler'larını serbest bırakır ve istek kaydını temizler."""
        with self._lock:
            self._stall_gate.set()
            self._stall_gate = threading.Event()
            self._requests.clear()

    def release_stalled(self) -> None:
        with self._lock:
            self._stall_gate.set()

    def wait_for_release(self) -> None:
        with self._lock:
            gate = self._stall_gate
        gate.wait(STALL_MAX_SECONDS)

    def record_request(self, method: str, path: str) -> None:
        with self._lock:
            self._requests.append((method, path))

    def requests_seen(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._requests)

    def track_handler_thread(self, thread: threading.Thread) -> None:
        with self._lock:
            self._handler_threads.append(thread)

    def handler_threads(self) -> list[threading.Thread]:
        with self._lock:
            return list(self._handler_threads)

    def handle_error(self, request: object, client_address: object) -> None:
        # Varsayılan davranış stderr'e yazar; burada kaydedilir ve testlerde denetlenir.
        with self._lock:
            self._errors.append(sys.exc_info()[1])

    def unexpected_errors(self) -> list[BaseException]:
        """İstemcinin bağlantıyı kapatmasından kaynaklanan ConnectionError'lar dışındaki hatalar."""
        with self._lock:
            return [e for e in self._errors if not isinstance(e, ConnectionError)]
