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
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import requests
from urllib3.exceptions import ReadTimeoutError  # requests'in bağımlılığı

from ._validate import require_number
from .scenarios import ALLOWED_METHODS, Scenario
from .transport import (
    TransportConnectionError,
    TransportError,
    TransportResponse,
    TransportTimeout,
)

_MAX_ERROR_CHARS = 300


def _describe(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= _MAX_ERROR_CHARS else text[: _MAX_ERROR_CHARS - 3] + "..."


def _translate(exc: requests.exceptions.RequestException) -> TransportError | None:
    """requests hatasını taşıma hatasına çevirir; çevrilmemesi gereken hata için None döndürür."""
    if isinstance(exc, ValueError):
        # InvalidURL, MissingSchema, InvalidSchema, InvalidHeader...: ölçüm değil girdi hatası.
        return None
    text = _describe(exc)
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


class RequestsTransport:
    """`Transport` protokolünün requests uygulaması.

    Kendi oluşturduğu oturumda `trust_env=False` kullanılır: ortam değişkenlerindeki
    proxy'ler, .netrc ve CA ayarları ölçümü sessizce etkilemez. Yeniden deneme yoktur
    (requests varsayılanı), yönlendirmeler izlenmez (3xx olduğu gibi raporlanır).
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        clock: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self._owns_session = session is None
        if session is None:
            session = requests.Session()
            session.trust_env = False
        self._session = session
        self._clock = clock

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
        headers, data = self._prepare(scenario)  # ölçüm dışı; hatalar yayılır

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
            translated = _translate(exc)
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
