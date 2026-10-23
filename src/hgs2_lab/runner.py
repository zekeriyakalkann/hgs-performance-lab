"""Senaryo yürütücü.

Ağ erişimi içermez: istek gönderimi dışarıdan enjekte edilen `Transport` ile
yapılır (bkz. transport.py; gerçek taşıyıcı http_transport.RequestsTransport).

Bir `ScenarioRunner` örneği bir çalıştırmayı temsil eder: `run()` birden çok
senaryo için çağrılabilir; `seq` bu çağrılar boyunca kesintisiz artar ve
`offset_ms` ilk `run()` çağrısında alınan ortak monotonik referansa göre
hesaplanır. Her senaryoda önce `warmup_repetitions` ısınma isteği (warmup=True),
sonra `repetitions` ölçüm isteği aynı yürütme yolundan geçer.

Yalnızca `TransportError` ailesi ölçüm kaydına çevrilir. Diğer tüm
istisnalar (programlama hataları dahil) olduğu gibi yayılır.

Kayda yazılan URL ve hata mesajındaki hassas değerler maskelenir (bkz. sanitize.py).

İsteğe bağlı `guard`: her istekten önce `before_request()`, her kayıttan sonra
`after_result(result)` çağrılır; `RunStopped` fırlatarak çalıştırmayı kontrollü
durdurabilir. Tamamlanan kayıtlar `results` ile her zaman (kesinti sonrasında da)
okunabilir.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from ._validate import require_number
from .models import RawResult, validate_run_id
from .sanitize import sanitize_text, sanitize_url, sensitive_values
from .scenarios import Scenario
from .transport import Transport, TransportError, TransportResponse

_NS_PER_MS = 1_000_000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _describe(exc: Exception) -> str:
    message = str(exc)
    name = type(exc).__name__
    return f"{name}: {message}" if message else name


class RunStopped(Exception):
    """Bir güvenlik sınırı nedeniyle çalıştırma kontrollü olarak durduruldu."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class RunGuard(Protocol):
    def before_request(self) -> None: ...

    def after_result(self, result: RawResult) -> None: ...


class ScenarioRunner:
    def __init__(
        self,
        transport: Transport,
        base_url: str,
        run_id: str,
        timeout_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], str] = _utc_now_iso,
        clock: Callable[[], int] = time.perf_counter_ns,
        guard: RunGuard | None = None,
    ) -> None:
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._run_id = validate_run_id(run_id)
        self._timeout_seconds = require_number(timeout_seconds, "timeout_seconds", ValueError, positive=True)
        self._sleep = sleep
        self._now = now
        self._clock = clock
        self._origin_ns: int | None = None  # çalıştırmanın ortak monotonik başlangıç referansı
        self._last_ns: int | None = None  # son run() çağrısının bittiği (ya da kesildiği) an
        self._seq = 0
        self._guard = guard
        self._results: list[RawResult] = []

    @property
    def results(self) -> list[RawResult]:
        """Bu çalıştırmada şimdiye kadar tamamlanan tüm kayıtlar (kopya)."""
        return list(self._results)

    @property
    def monotonic_duration_ms(self) -> float | None:
        """İlk run() başlangıcından son run() bitişine kadar geçen süre; henüz çalışmadıysa None."""
        if self._origin_ns is None or self._last_ns is None:
            return None
        return (self._last_ns - self._origin_ns) / _NS_PER_MS

    def run(self, scenario: Scenario) -> list[RawResult]:
        if self._origin_ns is None:
            self._origin_ns = self._clock()
        url = self._base_url + scenario.path
        record_url = sanitize_url(url)
        secrets = sensitive_values(scenario.headers, url)

        plan = [(True, i) for i in range(1, scenario.warmup_repetitions + 1)]
        plan += [(False, i) for i in range(1, scenario.repetitions + 1)]
        results: list[RawResult] = []
        try:
            for position, (warmup, iteration) in enumerate(plan, start=1):
                if self._guard is not None:
                    self._guard.before_request()
                result = self._run_once(scenario, url, record_url, secrets, warmup, iteration)
                results.append(result)
                self._results.append(result)
                if self._guard is not None:
                    self._guard.after_result(result)
                if scenario.delay_seconds and position < len(plan):
                    self._sleep(scenario.delay_seconds)
        finally:
            self._last_ns = self._clock()  # kesintide de süre gerçek bitişi yansıtır
        return results

    def _run_once(
        self,
        scenario: Scenario,
        url: str,
        record_url: str,
        secrets: list[str],
        warmup: bool,
        iteration: int,
    ) -> RawResult:
        assert self._origin_ns is not None
        self._seq += 1
        started_at = self._now()
        response: TransportResponse | None = None
        failure: TransportError | None = None

        start = self._clock()
        try:
            response = self._transport.send(scenario, url, self._timeout_seconds)
        except TransportError as exc:
            failure = exc
        elapsed_ms = (self._clock() - start) / _NS_PER_MS

        common = dict(
            run_id=self._run_id,
            seq=self._seq,
            scenario=scenario.name,
            iteration=iteration,
            warmup=warmup,
            method=scenario.method,
            url=record_url,
            started_at=started_at,
            offset_ms=(start - self._origin_ns) / _NS_PER_MS,
            elapsed_ms=elapsed_ms,
        )
        if failure is not None:
            return RawResult(
                **common,
                duration_ms=None,
                status_code=None,
                http_ok=None,
                error_type=failure.error_type,
                error=sanitize_text(_describe(failure), secrets),
            )
        assert response is not None
        return RawResult(
            **common,
            duration_ms=response.duration_ms if response.duration_ms is not None else elapsed_ms,
            status_code=response.status_code,
            http_ok=scenario.is_expected_status(response.status_code),
            response_bytes=response.size_bytes,
        )
