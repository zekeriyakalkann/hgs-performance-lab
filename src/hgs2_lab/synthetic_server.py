"""Yerel sentetik test sunucusu: planlanmış hataları uygulayan HTTP sunucusu (yalnızca standart kütüphane).

Bu sunucu yalnızca sentetik deneyler içindir; gerçek HGS2'yi temsil etmez.

Ağ sınırı:
* Yalnızca 127.0.0.1'e bind eder (değiştirilemez); varsayılan port 0 = işletim sisteminin seçtiği boş port.
* Adres yeniden kullanımı kapalıdır (`allow_reuse_address = False`; Windows'ta ayrıca SO_EXCLUSIVEADDRUSE):
  dolu bir porta bind girişimi başka bir dinleyiciyle paylaşılmaz, açık bir hatayla reddedilir.
* HTTPServer'ın ters DNS sorgusu (`socket.getfqdn`) yapılmaz; sunucu hiçbir giden bağlantı açmaz.
* Sunucu, istemcinin hedef korumasını değiştirmez: motor ona normal `base_url` ile, tüm denetimlerden geçerek bağlanır.

Davranış: istek `/synthetic/<senaryo>` rotasına gelir; sunucu o rotaya gelen k. isteğe planın k. girdisini
uygular (normal yanıt, gecikme, HTTP hatası, bağlantıyı yanıtsız kapatma, zaman aşımı için bekletme). Plan dışı
istekler (bilinmeyen rota, plan tükenmiş, metot uyuşmazlığı, büyük gövde, aşırı eşzamanlılık) hemen yanıtlanıp
kapatılır ve "unexpected" olay olarak kaydedilir.

Kaynak sınırları: eşzamanlı bağlantı sayısı, istek gövdesi boyutu, olay kaydı sayısı ve bekletme süresi
sınırlıdır; boşta bağlantı en çok HANDLER_SOCKET_TIMEOUT tutulur. `stop()` bekleyen tüm istekleri en çok bir
uyku dilimi (HOLD_SLICE_SECONDS) içinde serbest bırakır, iş parçacıklarını süre sınırıyla bekler ve hâlâ
yaşayanları döndürür (boş liste = temiz kapanış).

Bekleme (`_hold`): son tarih `time.perf_counter_ns` ile belirlenir; en çok HOLD_SLICE_SECONDS uzunluğunda
`time.sleep` dilimleriyle beklenir ve her dilim arasında durdurma işareti denetlenir. `threading.Event.wait`
Windows'ta zamanlayıcı adımına (~15,6 ms) yuvarlandığı için kısa gecikmeleri medyan ~8-14 ms uzatıyordu;
`time.sleep` Python 3.11+ ile Windows'ta yüksek çözünürlüklü zamanlayıcı kullanır (bu makinede aşım medyanı
<1 ms ölçüldü). Meşgul bekleme kullanılmaz (CPU). Bekleme yine de planlanandan kısa olamaz, yalnızca uzun
olabilir; gerçekleşen süre her olayda `hold_ms_actual` olarak kaydedilir.

Sunucu olayları istemci sonuçlarından AYRI bir kaynaktır; zaman damgaları `time.perf_counter_ns`'dir.
"""

from __future__ import annotations

import socket
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .synthetic import (
    FAULT_CONNECTION_DROP,
    FAULT_TIMEOUT,
    ROUTE_PREFIX,
    PlannedRequest,
    SyntheticPlan,
)

LOOPBACK = "127.0.0.1"
HANDLER_SOCKET_TIMEOUT = 5.0
MAX_BODY_BYTES = 64 * 1024
DEFAULT_MAX_CONCURRENT = 8
MAX_CONCURRENT_LIMIT = 64
MAX_HOLD_MS = 30_000.0
HOLD_METHOD = "sliced_sleep"  # sunucu olay dosyasına yazılır: verinin hangi bekleme yöntemiyle üretildiği
HOLD_SLICE_SECONDS = 0.02  # en uzun tek uyku dilimi = durdurma işaretine tepki süresinin üst sınırı
EXTRA_EVENT_CAPACITY = 1_000
OK_BODY = b"synthetic ok"

OUTCOME_RESPONDED = "responded"
OUTCOME_DROPPED = "dropped"  # bilinçli olarak yanıtsız kapatıldı
OUTCOME_HELD_THEN_CLOSED = "held_then_closed"  # zaman aşımı hatası: bekletildi, yanıtsız kapatıldı
OUTCOME_CLIENT_GONE = "client_gone"  # yanıt yazılırken istemci bağlantıyı kapatmıştı
OUTCOME_STOPPED = "stopped"  # sunucu kapanırken bekletme yarıda kesildi
OUTCOME_REJECTED = "rejected"


class SyntheticServerError(RuntimeError):
    """Sunucu başlatılamadı veya geçersiz yapılandırıldı."""


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = HANDLER_SOCKET_TIMEOUT
    server: "_HTTPServer"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - üst sınıf imzası
        pass

    def do_GET(self) -> None:
        self.server.controller._handle(self)

    def do_POST(self) -> None:
        self.server.controller._handle(self)

    def send_plain(self, status: int, body: bytes, close: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)


class _HTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False  # HTTPServer varsayılanı True'dur; dolu port paylaşılmasın
    daemon_threads = True

    def __init__(self, port: int, controller: "SyntheticServer") -> None:
        self.controller = controller
        super().__init__((LOOPBACK, port), _Handler)

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)  # yalnızca Windows
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        socketserver.TCPServer.server_bind(self)  # HTTPServer.server_bind'in ters DNS sorgusu atlanır
        host, port = self.server_address[:2]
        self.server_name, self.server_port = host, port

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.controller._acquire_slot():
            self.controller._record_rejection("overload")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.controller._release_slot()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        self.controller._track_thread(threading.current_thread())
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.controller._release_slot()

    def handle_error(self, request: object, client_address: object) -> None:
        self.controller._record_error(sys.exc_info()[1])


class SyntheticServer:
    def __init__(
        self,
        plan: SyntheticPlan,
        *,
        port: int = 0,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        max_events: int | None = None,
    ) -> None:
        if not isinstance(plan, SyntheticPlan):
            raise SyntheticServerError("plan bir SyntheticPlan olmalı")
        if isinstance(port, bool) or not isinstance(port, int) or not (port == 0 or 1024 <= port <= 65535):
            raise SyntheticServerError(f"port 0 (otomatik) ya da 1024..65535 olmalı (alınan: {port!r})")
        if isinstance(max_concurrent, bool) or not isinstance(max_concurrent, int) \
                or not 1 <= max_concurrent <= MAX_CONCURRENT_LIMIT:
            raise SyntheticServerError(f"max_concurrent 1..{MAX_CONCURRENT_LIMIT} olmalı (alınan: {max_concurrent!r})")
        for entry in plan.entries:
            if not 0 <= entry.delay_ms <= MAX_HOLD_MS:
                raise SyntheticServerError(f"{entry.index}. planlı istekte bekletme sınır dışı: {entry.delay_ms}")
        self._routes: dict[str, tuple[PlannedRequest, ...]] = {}
        for entry in plan.entries:
            self._routes.setdefault(entry.scenario, ())
            self._routes[entry.scenario] += (entry,)
        self._requested_port = port
        self._max_concurrent = max_concurrent
        self._max_events = max_events if max_events is not None else len(plan.entries) + EXTRA_EVENT_CAPACITY
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._arrivals = 0
        self._route_counts: dict[str, int] = {}
        self._events: list[dict[str, Any]] = []
        self._dropped_events = 0
        self._unexpected = 0
        self._errors: list[str] = []
        self._active = 0
        self._threads: list[threading.Thread] = []
        self._httpd: _HTTPServer | None = None
        self._serve_thread: threading.Thread | None = None

    # --- yaşam döngüsü ---
    def start(self) -> "SyntheticServer":
        if self._httpd is not None:
            raise SyntheticServerError("sunucu zaten başlatıldı")
        try:
            self._httpd = _HTTPServer(self._requested_port, self)
        except OSError as exc:
            raise SyntheticServerError(
                f"127.0.0.1:{self._requested_port} dinlenemedi ({type(exc).__name__}: {exc}); port kullanımda olabilir"
            ) from exc
        if self._httpd.server_address[0] != LOOPBACK:  # savunma: bind adresi değişmiş olamaz
            self._httpd.server_close()
            raise SyntheticServerError(f"sunucu loopback dışına bağlandı: {self._httpd.server_address!r}")
        self._serve_thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05},
                                              name="synthetic-server", daemon=True)
        self._serve_thread.start()
        return self

    def stop(self, join_timeout: float = 10.0) -> list[threading.Thread]:
        """Sunucuyu kapatır; süre sınırı içinde sonlanmayan iş parçacıklarını döndürür."""
        self._stop_event.set()  # bekletilen istekler hemen serbest kalır
        if self._httpd is None:
            return []
        if self._serve_thread is not None and self._serve_thread.is_alive():
            self._httpd.shutdown()
        self._httpd.server_close()
        with self._lock:
            threads = ([self._serve_thread] if self._serve_thread else []) + list(self._threads)
        deadline = time.monotonic() + join_timeout
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return [t for t in threads if t.is_alive()]

    def __enter__(self) -> "SyntheticServer":
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    @property
    def host(self) -> str:
        return LOOPBACK

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise SyntheticServerError("sunucu başlatılmadı")
        return self._httpd.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://{LOOPBACK}:{self.port}"

    @property
    def bound_address(self) -> tuple[str, int]:
        if self._httpd is None:
            raise SyntheticServerError("sunucu başlatılmadı")
        return self._httpd.server_address[:2]

    @property
    def is_closed(self) -> bool:
        return self._httpd is not None and self._httpd.socket.fileno() == -1

    def snapshot(self) -> dict[str, Any]:
        """Sunucu tarafı kayıtların kopyası (istemci sonuçlarından ayrı kaynak)."""
        with self._lock:
            return {
                "source": "synthetic_server",
                "host": LOOPBACK,
                "port": self._httpd.server_address[1] if self._httpd else None,
                "arrivals": self._arrivals,
                "unexpected_requests": self._unexpected,
                "dropped_events": self._dropped_events,
                "errors": list(self._errors),
                "events": [dict(e) for e in self._events],
            }

    # --- iç yardımcılar (iş parçacığı güvenli) ---
    def _acquire_slot(self) -> bool:
        with self._lock:
            if self._active >= self._max_concurrent:
                return False
            self._active += 1
            return True

    def _release_slot(self) -> None:
        with self._lock:
            self._active -= 1

    def _track_thread(self, thread: threading.Thread) -> None:
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]  # liste sınırsız büyümesin
            self._threads.append(thread)

    def _record_error(self, exc: BaseException | None) -> None:
        if isinstance(exc, ConnectionError):
            return  # istemcinin bağlantıyı kapatması beklenen bir durumdur
        with self._lock:
            if len(self._errors) < 100:
                self._errors.append(type(exc).__name__ if exc else "Unknown")

    def _new_event(self, **fields: Any) -> dict[str, Any]:
        """Olayı kaydeder (kilit tutulurken çağrılır); sınır aşılırsa kaydedilmeyen bir kopya döner."""
        event = {"arrival": self._arrivals, "received_ns": time.perf_counter_ns(), "completed_ns": None, **fields}
        if len(self._events) < self._max_events:
            self._events.append(event)
        else:
            self._dropped_events += 1
        return event

    def _record_rejection(self, reason: str) -> None:
        with self._lock:
            self._arrivals += 1
            self._unexpected += 1
            event = self._new_event(kind="unexpected", reason=reason, method=None, path=None, route=None,
                                    route_index=None, planned_fault=None, status_sent=None, hold_ms_planned=None,
                                    hold_ms_actual=None, hold_started_ns=None, hold_ended_ns=None,
                                    outcome=OUTCOME_REJECTED)
            event["completed_ns"] = time.perf_counter_ns()

    def _claim(self, method: str, raw_path: str, reject: str | None) -> tuple[dict[str, Any], PlannedRequest | None]:
        path = urlsplit(raw_path).path
        with self._lock:
            self._arrivals += 1
            route = path[len(ROUTE_PREFIX):] if path.startswith(ROUTE_PREFIX) else None
            entry = None
            if reject is None:
                entries = self._routes.get(route) if route is not None else None
                if entries is None:
                    reject = "unknown_route"
                else:
                    k = self._route_counts.get(route, 0)
                    if k >= len(entries):
                        reject = "plan_exhausted"
                    elif entries[k].method != method:
                        reject = "method_mismatch"
                    else:
                        self._route_counts[route] = k + 1
                        entry = entries[k]
            if entry is None:
                self._unexpected += 1
            event = self._new_event(
                kind="planned" if entry else "unexpected", reason=reject, method=method, path=path[:200],
                route=entry.scenario if entry else None, route_index=entry.route_index if entry else None,
                planned_fault=entry.fault if entry else None, status_sent=None,
                hold_ms_planned=entry.delay_ms if entry else None, hold_ms_actual=None, hold_started_ns=None,
                hold_ended_ns=None, outcome=None,
            )
        return event, entry

    def _finish(self, event: dict[str, Any], **fields: Any) -> None:
        with self._lock:
            event.update(fields, completed_ns=time.perf_counter_ns())

    def _hold(self, ms: float) -> tuple[int, int, bool]:
        """En az `ms` bekler (durdurulmazsa); (başlangıç ns, bitiş ns, durduruldu mu). Bkz. modül belgesi."""
        start = time.perf_counter_ns()
        deadline = start + int(ms * 1_000_000)
        stopped = False
        while True:
            remaining = deadline - time.perf_counter_ns()
            if remaining <= 0:
                break
            if self._stop_event.is_set():
                stopped = True
                break
            time.sleep(min(remaining / 1e9, HOLD_SLICE_SECONDS))
        return start, time.perf_counter_ns(), stopped

    def _record_hold(self, event: dict[str, Any], started_ns: int, ended_ns: int) -> None:
        # Bekleme biter bitmez kaydedilir: sonradan yanıt yazılamasa (istemci gitmiş) bile kaybolmaz.
        with self._lock:
            event.update(hold_started_ns=started_ns, hold_ended_ns=ended_ns,
                         hold_ms_actual=(ended_ns - started_ns) / 1e6)

    def _handle(self, h: _Handler) -> None:
        reject = None
        length_text = h.headers.get("Content-Length")
        length = 0
        if length_text is not None:
            try:
                length = int(length_text)
            except ValueError:
                length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            reject = "body_too_large" if length > MAX_BODY_BYTES else "bad_content_length"
        elif length:
            h.rfile.read(length)  # sınırlı gövde okunur ve atılır
        event, entry = self._claim(h.command, h.path, reject)
        try:
            if entry is None:
                status = {"unknown_route": 404, "plan_exhausted": 410, "method_mismatch": 405,
                          "body_too_large": 413}.get(event["reason"], 400)
                h.send_plain(status, f"synthetic: {event['reason']}".encode("ascii"), close=True)
                self._finish(event, status_sent=status, outcome=OUTCOME_REJECTED)
                return
            if entry.delay_ms > 0:
                started_ns, ended_ns, stopped = self._hold(entry.delay_ms)
                self._record_hold(event, started_ns, ended_ns)
                if stopped:
                    h.close_connection = True
                    self._finish(event, outcome=OUTCOME_STOPPED)
                    return
            if entry.fault in (FAULT_CONNECTION_DROP, FAULT_TIMEOUT):
                h.close_connection = True  # yanıt yazılmadan bağlantı kapanır
                outcome = OUTCOME_DROPPED if entry.fault == FAULT_CONNECTION_DROP else OUTCOME_HELD_THEN_CLOSED
                self._finish(event, outcome=outcome)
                return
            body = OK_BODY if entry.status < 400 else f"synthetic error {entry.status}".encode("ascii")
            h.send_plain(entry.status, body)
            self._finish(event, status_sent=entry.status, outcome=OUTCOME_RESPONDED)
        except ConnectionError:
            h.close_connection = True
            self._finish(event, outcome=OUTCOME_CLIENT_GONE)
