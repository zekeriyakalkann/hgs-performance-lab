"""Uçtan uca çalıştırma: Config -> Scenarios -> ön kontrol -> Metadata -> Runner -> Transport -> Storage.

Mevcut bileşenleri birbirine bağlar; kendi yürütme döngüsü yoktur (döngü ScenarioRunner'dadır).

Akış:
1. Ön kontrol (`preflight`): hedef (metin + ad çözümlemesi, yalnızca loopback), istek bütçesi,
   gecikmelerden gelen en kısa süre ve sonuç dosyası çakışması. Herhangi biri uymazsa
   `PreflightError` fırlatılır ve HİÇBİR HTTP isteği gönderilmez, taşıyıcı oluşturulmaz.
2. İstekler başlamadan Git bilgisi ve girdi dosyası özetleri alınır.
3. Runner, `SafetyGuard` ile çalışır: süre sınırı, art arda taşıma hatası ve hata oranı eşiği.
4. Sonuç ne olursa olsun taşıyıcı kapatılır, tamamlanan kayıtlar metadata ile kaydedilir.

Çalıştırma durumları (`execution.status`):
* completed  : tüm planlanan istekler yapıldı -> `<run_id>.csv/json`
* aborted    : güvenlik sınırı ya da çalışma anında reddedilen hedef -> `<run_id>.partial.*`
* interrupted: kullanıcı Ctrl+C ile durdurdu -> `<run_id>.partial.*`
* failed     : beklenmeyen istisna -> `<run_id>.partial.*`, ardından istisna yeniden fırlatılır
"""

from __future__ import annotations

import secrets
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .config import LabConfig, RunLimits
from .http_transport import RequestsTransport
from .metadata import build_run_metadata, code_info, input_hashes, validate_dataset_kind, validate_target_label
from .models import (  # noqa: F401 - durum sabitleri buradan da dışa aktarılır
    STATUS_ABORTED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    RawResult,
    validate_run_id,
)
from .models import DATASET_MEASUREMENT
from .runner import RunStopped, ScenarioRunner
from .sanitize import sanitize_text
from .scenarios import Scenario
from .storage import ResultStore
from .target_guard import Resolver, TargetNotAllowed, check_target, system_resolver
from .transport import Transport

_NS_PER_SECOND = 1_000_000_000


class PreflightError(ValueError):
    """Çalıştırma başlamadan reddedildi; hiçbir HTTP isteği gönderilmedi."""


class ClosableTransport(Transport, Protocol):
    def close(self) -> None: ...


@dataclass
class RunOutcome:
    run_id: str
    status: str
    stop_reason: str | None
    message: str | None
    planned_requests: int
    results: list[RawResult] = field(default_factory=list)
    csv_path: Path | None = None
    json_path: Path | None = None

    @property
    def completed(self) -> bool:
        return self.status == STATUS_COMPLETED


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_run_id(now: datetime | None = None) -> str:
    """Zaman damgası + rastgele ek: çakışma olasılığı düşük, dosya adı olarak güvenli."""
    moment = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return validate_run_id(f"run-{moment}-{secrets.token_hex(3)}")


def planned_request_count(scenarios: Sequence[Scenario]) -> int:
    return sum(s.warmup_repetitions + s.repetitions for s in scenarios)


def minimum_duration_seconds(scenarios: Sequence[Scenario]) -> float:
    """Yalnızca senaryo gecikmelerinden gelen alt sınır (istek süreleri hariç)."""
    return sum(s.delay_seconds * (s.warmup_repetitions + s.repetitions - 1) for s in scenarios)


def preflight(
    config: LabConfig,
    scenarios: Sequence[Scenario],
    *,
    store: ResultStore,
    run_id: str,
    resolver: Resolver = system_resolver,
) -> int:
    """İstek göndermeden önceki tüm kontroller; planlanan istek sayısını döndürür."""
    if not scenarios:
        raise PreflightError("Çalıştırılacak senaryo yok")
    try:
        check_target(config.base_url, resolver)  # senaryo path'leri tek '/' ile başlar: ana makine değişmez
    except TargetNotAllowed as exc:
        raise PreflightError(f"Hedef reddedildi: {exc}") from exc

    limits = config.limits
    planned = planned_request_count(scenarios)
    if planned > limits.max_requests:
        raise PreflightError(
            f"İstek bütçesi aşıldı: planlanan {planned} istek (ısınma dahil) > limits.max_requests {limits.max_requests}"
        )
    floor = minimum_duration_seconds(scenarios)
    if floor >= limits.max_duration_seconds:
        raise PreflightError(
            f"Süre bütçesi aşıldı: gecikmeler tek başına {floor:g} sn sürer >= "
            f"limits.max_duration_seconds {limits.max_duration_seconds:g}"
        )
    existing = store.existing_files(run_id)
    if existing:
        raise PreflightError(f"Bu run_id için sonuç dosyası zaten var, üzerine yazılmaz: {existing[0].name}")
    return planned


class SafetyGuard:
    """Çalıştırma sırasında güvenlik sınırlarını uygular (ısınma istekleri dahil)."""

    def __init__(self, limits: RunLimits, clock: Callable[[], int]) -> None:
        self._limits = limits
        self._clock = clock
        self._start_ns = clock()
        self.total = 0
        self.failed = 0
        self._consecutive_transport_errors = 0

    def before_request(self) -> None:
        elapsed_s = (self._clock() - self._start_ns) / _NS_PER_SECOND
        if elapsed_s >= self._limits.max_duration_seconds:
            raise RunStopped(
                "duration_limit",
                f"Süre sınırına ulaşıldı ({elapsed_s:.1f} sn >= {self._limits.max_duration_seconds:g} sn)",
            )

    def after_result(self, result: RawResult) -> None:
        self.total += 1
        transport_error = result.error_type is not None
        self.failed += transport_error or result.http_ok is False
        self._consecutive_transport_errors = self._consecutive_transport_errors + 1 if transport_error else 0

        if self._consecutive_transport_errors >= self._limits.max_consecutive_transport_errors:
            raise RunStopped(
                "consecutive_transport_errors",
                f"Art arda {self._consecutive_transport_errors} taşıma hatası (son: {result.error_type})",
            )
        if self.total >= self._limits.error_rate_min_requests:
            rate = self.failed / self.total
            if rate > self._limits.max_error_rate:
                raise RunStopped(
                    "error_rate",
                    f"Hata oranı {rate:.2f} > {self._limits.max_error_rate:g} ({self.failed}/{self.total} istek)",
                )


def execute_run(
    config: LabConfig,
    scenarios: Sequence[Scenario],
    *,
    config_path: Path | None,
    target_label: str | None = None,
    run_id: str | None = None,
    resolver: Resolver = system_resolver,
    transport_factory: Callable[[], ClosableTransport] | None = None,
    clock: Callable[[], int] = time.perf_counter_ns,
    now: Callable[[], str] = _utc_now_iso,
    sleep: Callable[[float], None] = time.sleep,
    code: dict[str, Any] | None = None,
    wall_clock: Callable[[], int] = time.time_ns,
    dataset_kind: str = DATASET_MEASUREMENT,
    synthetic: dict[str, Any] | None = None,
) -> RunOutcome:
    """Bir çalıştırmayı uçtan uca yürütür ve sonuçları kaydeder.

    `dataset_kind`/`synthetic` yalnızca metadata'ya yazılır; ön kontrol, hedef koruması ve güvenlik
    sınırları veri türünden bağımsız olarak AYNEN uygulanır.

    Ön kontrol başarısızsa `PreflightError` (istek yok). Sonuçlar yazılamazsa `StorageError`.
    Beklenmeyen bir istisnada kısmi sonuçlar kaydedilir ve istisna yeniden fırlatılır.
    """
    try:
        validate_target_label(target_label)
        validate_dataset_kind(dataset_kind, synthetic)  # istek göndermeden önce; metadata aynı kuralı uygular
        run_id = validate_run_id(run_id) if run_id is not None else generate_run_id()
    except ValueError as exc:
        raise PreflightError(str(exc)) from exc
    store = ResultStore(config.output_dir)
    planned = preflight(config, scenarios, store=store, run_id=run_id, resolver=resolver)

    # İstekler başlamadan: kod sürümü ve girdi dosyalarının özetleri.
    code = code if code is not None else code_info()
    inputs = input_hashes(config_path, config.scenarios_file)
    started_at = now()

    factory = transport_factory or (lambda: RequestsTransport(resolver=resolver))
    transport = factory()
    runner = ScenarioRunner(
        transport, config.base_url, run_id, config.timeout_seconds,
        sleep=sleep, now=now, clock=clock, guard=SafetyGuard(config.limits, clock), wall_clock=wall_clock,
    )
    status, stop_reason, message = STATUS_COMPLETED, None, None
    pending: BaseException | None = None
    try:
        for scenario in scenarios:
            runner.run(scenario)
    except RunStopped as exc:
        status, stop_reason, message = STATUS_ABORTED, exc.reason, str(exc)
    except TargetNotAllowed as exc:  # bağlantı anında yakalanan hedef (ör. DNS rebinding)
        status, stop_reason, message = STATUS_ABORTED, "target_not_allowed", str(exc)
    except KeyboardInterrupt:
        status, stop_reason, message = STATUS_INTERRUPTED, "keyboard_interrupt", "Kullanıcı tarafından durduruldu (Ctrl+C)"
    except Exception as exc:  # programlama hatası: kaydet, sonra yeniden fırlat
        status, stop_reason, message = STATUS_FAILED, "unexpected_error", type(exc).__name__
        pending = exc
    finally:
        transport.close()

    results = runner.results
    execution = {
        "status": status,
        "stop_reason": stop_reason,
        "message": sanitize_text(message) if message else None,
        "planned_requests": planned,
        "completed_requests": len(results),
        "limits": config.limits.to_dict(),
    }
    metadata = build_run_metadata(
        config, scenarios, started_at, now(),
        config_path=config_path, monotonic_duration_ms=runner.monotonic_duration_ms,
        target_label=target_label, code=code, inputs=inputs, execution=execution, clock=runner.clock_anchor,
        dataset_kind=dataset_kind, synthetic=synthetic,
    )
    try:
        csv_path, json_path = store.save(run_id, results, metadata, partial=status != STATUS_COMPLETED)
    except Exception:
        if pending is not None:
            raise pending
        raise
    if pending is not None:
        raise pending
    return RunOutcome(run_id, status, stop_reason, execution["message"], planned, results, csv_path, json_path)


def summarize(results: Sequence[RawResult]) -> dict[str, Any]:
    """CLI özeti için sayımlar ve ölçüm isteklerinin duration_ms özeti."""
    measured = [r for r in results if not r.warmup]
    durations = [r.duration_ms for r in measured if r.duration_ms is not None]
    errors: dict[str, int] = {}
    for r in results:
        if r.error_type is not None:
            errors[r.error_type] = errors.get(r.error_type, 0) + 1
    return {
        "total": len(results),
        "warmup": len(results) - len(measured),
        "measured": len(measured),
        "http_ok": sum(r.http_ok is True for r in results),
        "http_unexpected": sum(r.http_ok is False for r in results),
        "transport_errors": errors,
        "duration_ms_median": statistics.median(durations) if durations else None,
        "duration_ms_min": min(durations) if durations else None,
        "duration_ms_max": max(durations) if durations else None,
    }
