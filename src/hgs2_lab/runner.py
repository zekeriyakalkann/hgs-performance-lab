"""Senaryo yürütücü.

Ağ erişimi içermez: istek gönderimi dışarıdan enjekte edilen `Transport` ile
yapılır (bkz. transport.py). Gerçek HTTP taşıyıcısı bu aşamada YAZILMAMIŞTIR.

Yalnızca `TransportError` ailesi ölçüm kaydına çevrilir. Diğer tüm
istisnalar (programlama hataları dahil) olduğu gibi yayılır.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone

from ._validate import require_number
from .models import RawResult, validate_run_id
from .scenarios import Scenario
from .transport import Transport, TransportError, TransportResponse

_NS_PER_MS = 1_000_000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _describe(exc: Exception) -> str:
    message = str(exc)
    name = type(exc).__name__
    return f"{name}: {message}" if message else name


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
    ) -> None:
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._run_id = validate_run_id(run_id)
        self._timeout_seconds = require_number(timeout_seconds, "timeout_seconds", ValueError, positive=True)
        self._sleep = sleep
        self._now = now
        self._clock = clock

    def run(self, scenario: Scenario) -> list[RawResult]:
        url = self._base_url + scenario.path
        results: list[RawResult] = []
        for i in range(1, scenario.repetitions + 1):
            results.append(self._run_once(scenario, url, i))
            if scenario.delay_seconds and i < scenario.repetitions:
                self._sleep(scenario.delay_seconds)
        return results

    def _run_once(self, scenario: Scenario, url: str, iteration: int) -> RawResult:
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
            scenario=scenario.name,
            iteration=iteration,
            method=scenario.method,
            url=url,
            started_at=started_at,
            elapsed_ms=elapsed_ms,
        )
        if failure is not None:
            return RawResult(
                **common,
                duration_ms=None,
                status_code=None,
                http_ok=None,
                error_type=failure.error_type,
                error=_describe(failure),
            )
        assert response is not None
        return RawResult(
            **common,
            duration_ms=response.duration_ms if response.duration_ms is not None else elapsed_ms,
            status_code=response.status_code,
            http_ok=scenario.is_expected_status(response.status_code),
            response_bytes=response.size_bytes,
        )
