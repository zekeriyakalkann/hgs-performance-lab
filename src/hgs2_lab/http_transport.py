"""requests tabanlı HTTP taşıyıcısı.

Ölçüm sınırı (`TransportResponse.duration_ms`): `session.request(...)` çağrısından
hemen önce başlar; yanıt gövdesinin TAMAMI okunduktan hemen sonra biter
(`stream=True` ile başlıklar alınır, gövde `response.content` ile okunur).
Başlık/gövde hazırlığı (JSON serileştirme) ve yanıtın kapatılması bu süreye
girmez; bunlar yalnızca runner'ın `elapsed_ms` değerine girer.

Yanıt boyutu (`size_bytes`): içerik kodlaması (gzip/deflate) çözüldükten sonraki
gövdenin bayt sayısıdır; başlıklar ve ağdaki sıkıştırılmış boyut dahil değildir.

Hata modeli: HTTP yanıtı alınabildiyse (500 dahil) hata fırlatılmaz. Yanıt
alınamazsa requests hataları `TransportTimeout` / `TransportConnectionError` /
`TransportError`'a çevrilir. Girdi hataları (geçersiz URL/başlık, serileştirilemeyen
body, desteklenmeyen metot) ve diğer beklenmeyen istisnalar OLDUĞU GİBİ yayılır.
Çevrilen hata mesajlarında hassas sorgu değerleri, URL parolaları ve isteğin hassas
header değerleri maskelenir (bkz. sanitize.py).

Hedef güvenliği (bkz. target_guard.py): `send` her istekte URL'yi ve ad çözümlemesini
denetler; ayrıca oturuma takılan adaptör, urllib3 soketi açmadan hemen önce adı yeniden
çözümler ve yalnızca doğrulanmış loopback IP'sine bağlanır. Proxy kullanımı reddedilir.
Kurallara uymayan hedef `TargetNotAllowed` ile, bağlantı kurulmadan reddedilir.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError, ReadTimeoutError  # requests'in bağımlılığı

from ._validate import require_number
from .sanitize import sanitize_text, sensitive_values
from .scenarios import ALLOWED_METHODS, Scenario
from .target_guard import Resolver, TargetNotAllowed, check_url, resolve_loopback, system_resolver
from .transport import (
    TransportConnectionError,
    TransportError,
    TransportResponse,
    TransportTimeout,
)

_MAX_ERROR_CHARS = 300


def _describe(exc: Exception, secrets: list[str]) -> str:
    # Önce maskele, sonra kırp: kırpma bir gizli değeri maskelenemez biçimde bölmesin.
    text = sanitize_text(f"{type(exc).__name__}: {exc}", secrets)
    return text if len(text) <= _MAX_ERROR_CHARS else text[: _MAX_ERROR_CHARS - 3] + "..."


def _translate(exc: requests.exceptions.RequestException, secrets: list[str]) -> TransportError | None:
    """requests hatasını taşıma hatasına çevirir; çevrilmemesi gereken hata için None döndürür."""
    if isinstance(exc, ValueError):
        # InvalidURL, MissingSchema, InvalidSchema, InvalidHeader...: ölçüm değil girdi hatası.
        return None
    text = _describe(exc, secrets)
    # ConnectTimeout hem Timeout hem ConnectionError alt sınıfıdır: önce Timeout bakılmalı.
    if isinstance(exc, requests.exceptions.Timeout):
        return TransportTimeout(text)
    if isinstance(exc, requests.exceptions.ConnectionError):
        # Gövde okunurken oluşan okuma zaman aşımı requests'te ConnectionError(ReadTimeoutError) olur.
        if any(isinstance(arg, ReadTimeoutError) for arg in exc.args):
            return TransportTimeout(text)
        return TransportConnectionError(text)  # SSLError ve ProxyError dahil
    if isinstance(exc, requests.exceptions.ChunkedEncodingError):
        return TransportConnectionError(text)  # bağlantı gövde okunurken koptu
    return TransportError(text)


class _LoopbackConnectionMixin:
    """urllib3 bağlantısı: soketi açmadan önce adı çözümler, loopback değilse reddeder,
    yalnızca doğrulanmış IP adresine bağlanır (çözümleme ile bağlantı arasında adres değişemez).

    Not: urllib3'ün iç `_dns_host` özniteliği kullanılır (constraints.txt ile sabitlenmiş sürüm);
    yerel entegrasyon testleri bu davranışı gerçek soketle doğrular.
    """

    _resolver: Resolver = staticmethod(system_resolver)

    def _new_conn(self):  # type: ignore[no-untyped-def]
        name = self._dns_host  # type: ignore[attr-defined]
        addresses = resolve_loopback(name.strip("[]"), self.port, type(self)._resolver)  # type: ignore[attr-defined]
        last_error: NewConnectionError | None = None
        try:
            for address in addresses:
                self._dns_host = address  # yalnızca soket için; Host başlığı/SNI özgün addan gelir
                try:
                    return super()._new_conn()  # type: ignore[misc]
                except NewConnectionError as exc:  # ör. ::1 kapalı, 127.0.0.1 açık
                    last_error = exc
            assert last_error is not None
            raise last_error
        finally:
            self._dns_host = name


def _guarded_pool_classes(resolver: Resolver) -> dict[str, type]:
    attrs = {"_resolver": staticmethod(resolver)}
    http_conn = type("LoopbackHTTPConnection", (_LoopbackConnectionMixin, HTTPConnection), attrs)
    https_conn = type("LoopbackHTTPSConnection", (_LoopbackConnectionMixin, HTTPSConnection), attrs)
    return {
        "http": type("LoopbackHTTPConnectionPool", (HTTPConnectionPool,), {"ConnectionCls": http_conn}),
        "https": type("LoopbackHTTPSConnectionPool", (HTTPSConnectionPool,), {"ConnectionCls": https_conn}),
    }


class _LoopbackOnlyAdapter(HTTPAdapter):
    """Bağlantıları loopback korumalı urllib3 havuzlarıyla açar; proxy kullanımını reddeder."""

    def __init__(self, resolver: Resolver) -> None:
        self._pool_classes = _guarded_pool_classes(resolver)
        super().__init__()  # init_poolmanager burada çağrılır

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = dict(self._pool_classes)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> Any:
        raise TargetNotAllowed("Proxy üzerinden bağlantıya izin verilmiyor")


class RequestsTransport:
    """`Transport` protokolünün requests uygulaması.

    Kendi oluşturduğu oturumda `trust_env=False` kullanılır: ortam değişkenlerindeki
    proxy'ler, .netrc ve CA ayarları ölçümü sessizce etkilemez. Yeniden deneme yoktur
    (requests varsayılanı), yönlendirmeler izlenmez (3xx olduğu gibi raporlanır).

    Dışarıdan bir `requests.Session` verilirse `trust_env=False` ve proxy'siz olmalıdır;
    ona da loopback korumalı adaptör takılır. Başka türden oturum nesneleri (test sahteleri)
    için `send` içindeki URL ve çözümleme kontrolü yine uygulanır.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        clock: Callable[[], int] = time.perf_counter_ns,
        resolver: Resolver = system_resolver,
    ) -> None:
        self._owns_session = session is None
        if session is None:
            session = requests.Session()
            session.trust_env = False
        if isinstance(session, requests.Session):
            if session.trust_env or session.proxies:
                raise ValueError("Oturum trust_env=False olmalı ve proxy içermemeli")
            adapter = _LoopbackOnlyAdapter(resolver)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
        self._session = session
        self._clock = clock
        self._resolver = resolver

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "RequestsTransport":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def send(self, scenario: Scenario, url: str, timeout_seconds: float) -> TransportResponse:
        if scenario.method not in ALLOWED_METHODS:
            raise ValueError(f"Desteklenmeyen HTTP metodu: {scenario.method!r}")
        timeout = require_number(timeout_seconds, "timeout_seconds", ValueError, positive=True)
        host, port = check_url(url)  # şema ve ad; TargetNotAllowed yayılır
        resolve_loopback(host, port, self._resolver)  # çözümlenen adreslerin tamamı loopback olmalı
        headers, data = self._prepare(scenario)  # ölçüm dışı; hatalar yayılır
        secrets = sensitive_values(headers, url)  # hata mesajlarında maskelenecek değerler

        start = self._clock()
        try:
            response = self._session.request(
                scenario.method,
                url,
                headers=headers,
                data=data,
                timeout=timeout,
                allow_redirects=False,
                stream=True,
            )
            try:
                body = response.content  # gövdenin tamamını okur
                end = self._clock()
            finally:
                response.close()
        except requests.exceptions.RequestException as exc:
            translated = _translate(exc, secrets)
            if translated is None:
                raise
            raise translated from exc

        return TransportResponse(
            status_code=response.status_code,
            size_bytes=len(body),
            duration_ms=(end - start) / 1_000_000,
            body=body,
        )

    @staticmethod
    def _prepare(scenario: Scenario) -> tuple[dict[str, str], bytes | None]:
        headers = dict(scenario.headers)
        if scenario.body is None:
            return headers, None
        # Kendimiz serileştiririz: NaN/serileştirilemeyen değer ValueError/TypeError olarak
        # yayılır ve requests'in InvalidJSONError'ı ile taşıma hatasına karışmaz.
        data = json.dumps(scenario.body, allow_nan=False).encode("utf-8")
        if not any(name.lower() == "content-type" for name in headers):
            headers["Content-Type"] = "application/json"
        return headers, data
