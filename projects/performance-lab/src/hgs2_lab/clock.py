"""Saat çapası: çalıştırmanın monotonik başlangıç referansı ile UTC duvar saatinin birlikte kaydı.

Runner, ilk isteğin `offset_ms` değerlerini monotonik saate göre hesaplar; duvar saati ise
yalnızca `started_at` gibi metinlerde görünür. Çapa, ikisini AYNI başlangıç anında okuyup
metadata'ya `clock` olarak yazar; böylece bir `offset_ms` değeri UTC zamana çevrilebilir.

Okuma sırası: monotonik (m0) -> duvar saati -> monotonik (m1). `monotonic_ns` = m0 runner'ın
başlangıç referansıdır; duvar saati okuması [m0, m1] aralığında bir yerdedir ve
`read_window_ns` = m1 - m0 bu belirsizliğin üst sınırıdır.

Kapsam (`monotonic_scope = "process"`): monotonik değerin başlangıç noktası tanımsızdır; yalnızca
aynı süreç içindeki farklar anlamlıdır. Başka bir süreçteki veya makinedeki saatlerle eşitlik
kanıtlanmış DEĞİLDİR; telemetri hizalaması ayrıca doğrulanmalıdır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ._validate import require_int, require_str

MONOTONIC_SCOPE_PROCESS = "process"
ANCHOR_EVENT_RUNNER_ORIGIN = "runner_origin"
_NS_PER_SECOND = 1_000_000_000
_NS_PER_MS = 1_000_000


def callable_name(fn: Callable[..., Any]) -> str:
    """Saat kaynağının okunur adı (ör. `time.perf_counter_ns`); enjekte edilen sahteler için sınıf adı."""
    module = getattr(fn, "__module__", None)
    name = getattr(fn, "__qualname__", None) or type(fn).__qualname__
    return f"{module}.{name}" if module else name


def ns_to_utc_iso(wall_ns: int) -> str:
    """Unix epoch nanosaniyesini mikrosaniye çözünürlüklü ISO 8601 UTC metnine çevirir."""
    seconds, rest = divmod(wall_ns, _NS_PER_SECOND)
    return datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=rest // 1000).isoformat()


class ClockAnchorError(ValueError):
    """Geçersiz saat çapası."""


@dataclass(frozen=True)
class ClockAnchor:
    anchor_event: str  # çapanın alındığı an; şimdilik yalnızca runner_origin
    monotonic_source: str
    monotonic_ns: int  # runner'ın başlangıç referansı: offset_ms = 0 bu andır
    monotonic_scope: str
    wall_source: str
    wall_time_ns: int  # Unix epoch, ns
    wall_time_utc: str  # wall_time_ns'in ISO 8601 UTC karşılığı (mikrosaniye)
    read_window_ns: int  # m1 - m0: duvar saati okumasının belirsizlik üst sınırı

    def __post_init__(self) -> None:
        err = ClockAnchorError
        for name in ("anchor_event", "monotonic_source", "monotonic_scope", "wall_source", "wall_time_utc"):
            require_str(getattr(self, name), f"clock.{name}", err)
        require_int(self.monotonic_ns, "clock.monotonic_ns", err)
        require_int(self.wall_time_ns, "clock.wall_time_ns", err, minimum=0)
        require_int(self.read_window_ns, "clock.read_window_ns", err, minimum=0)
        try:
            expected_utc = ns_to_utc_iso(self.wall_time_ns)
        except (OverflowError, OSError, ValueError) as exc:
            raise err(f"clock.wall_time_ns geçerli bir zaman değil: {self.wall_time_ns}") from exc
        if self.wall_time_utc != expected_utc:
            raise err("clock.wall_time_utc, clock.wall_time_ns ile uyuşmuyor")

    @classmethod
    def capture(
        cls,
        clock: Callable[[], int],
        wall_clock: Callable[[], int],
        *,
        anchor_event: str = ANCHOR_EVENT_RUNNER_ORIGIN,
    ) -> "ClockAnchor":
        m0 = clock()
        wall_ns = wall_clock()
        m1 = clock()
        return cls(
            anchor_event=anchor_event,
            monotonic_source=callable_name(clock),
            monotonic_ns=m0,
            monotonic_scope=MONOTONIC_SCOPE_PROCESS,
            wall_source=callable_name(wall_clock),
            wall_time_ns=wall_ns,
            wall_time_utc=ns_to_utc_iso(wall_ns),
            read_window_ns=m1 - m0,
        )

    def offset_ms_to_wall_ns(self, offset_ms: float) -> int:
        """Aynı runner'daki bir `offset_ms` değerinin yaklaşık duvar saati karşılığı (± read_window_ns)."""
        return self.wall_time_ns + round(offset_ms * _NS_PER_MS)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "ClockAnchor":
        if not isinstance(data, Mapping):
            raise ClockAnchorError(f"clock bir nesne olmalı (alınan: {type(data).__name__})")
        expected = {f for f in cls.__dataclass_fields__}
        missing = sorted(expected - set(data))
        extra = sorted(set(data) - expected)
        if missing or extra:
            raise ClockAnchorError(f"clock alanları uyuşmuyor (eksik: {missing}, fazla: {extra})")
        return cls(**data)
