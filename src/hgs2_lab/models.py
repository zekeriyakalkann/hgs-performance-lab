"""Ham sonuç veri modeli: her istek girişimi için tek bir kayıt.

İki ayrı sonuç düzlemi vardır ve karıştırılmaz:

* Taşıma düzlemi: HTTP yanıtı alınabildi mi? Alınamadıysa `error_type` dolu,
  `status_code`/`duration_ms`/`http_ok` boştur.
* HTTP düzlemi: yanıt alındıysa `status_code` ve senaryonun beklediği
  durum koduna göre `http_ok` doludur. HTTP 500 de bir yanıttır; `error_type`
  boş kalır.

`business_outcome` ileride HGS2 yanıt gövdesinden ayrıştırılacak iş mantığı
sonucu içindir; şimdilik her zaman boştur.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from typing import Any

from ._validate import require_int, require_number, require_str

ERROR_TIMEOUT = "timeout"
ERROR_CONNECTION = "connection_error"
ERROR_TRANSPORT = "transport_error"  # sınıflandırılamayan diğer taşıma hataları
ERROR_TYPES = frozenset({ERROR_TIMEOUT, ERROR_CONNECTION, ERROR_TRANSPORT})

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class InvalidRunId(ValueError):
    """run_id dosya adı olarak güvenli değil."""


def validate_run_id(run_id: object) -> str:
    """run_id'nin dosya adı olarak güvenli olduğunu doğrular (yol ayracı, nokta ile başlama vb. yok)."""
    if not isinstance(run_id, str) or not _RUN_ID_RE.match(run_id):
        raise InvalidRunId(
            f"Geçersiz run_id {run_id!r}: harf/rakamla başlamalı; yalnızca harf, rakam, '.', '_', '-' "
            "içermeli; en çok 64 karakter olmalı"
        )
    if run_id.endswith("."):
        raise InvalidRunId(f"Geçersiz run_id {run_id!r}: '.' ile bitemez")
    if run_id.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        raise InvalidRunId(f"Geçersiz run_id {run_id!r}: Windows ayrılmış adı")
    return run_id


@dataclass(frozen=True)
class RawResult:
    run_id: str
    scenario: str
    iteration: int
    method: str
    url: str
    started_at: str  # ISO 8601, UTC; girişimin başladığı duvar saati zamanı
    elapsed_ms: float  # girişimden taşıyıcının sonuç/hata döndürmesine kadar (monotonik saat)
    duration_ms: float | None  # yalnızca HTTP yanıtı alındıysa dolu
    status_code: int | None  # yalnızca HTTP yanıtı alındıysa dolu
    http_ok: bool | None  # yalnızca HTTP yanıtı alındıysa dolu: durum kodu beklenen mi?
    business_outcome: str | None = None
    error_type: str | None = None  # None: taşıma hatası yok
    error: str | None = None
    response_bytes: int | None = None

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        for name in ("scenario", "method", "url", "started_at"):
            require_str(getattr(self, name), name, ValueError)
        require_int(self.iteration, "iteration", ValueError, minimum=1)
        require_number(self.elapsed_ms, "elapsed_ms", ValueError, non_negative=True)
        if self.duration_ms is not None:
            require_number(self.duration_ms, "duration_ms", ValueError, non_negative=True)
        if self.status_code is not None:
            require_int(self.status_code, "status_code", ValueError, minimum=100)
            if self.status_code > 599:
                raise ValueError(f"status_code 100-599 aralığında olmalı (alınan: {self.status_code})")
        if self.response_bytes is not None:
            require_int(self.response_bytes, "response_bytes", ValueError, minimum=0)
        for name in ("business_outcome", "error"):
            if getattr(self, name) is not None:
                require_str(getattr(self, name), name, ValueError)
        if self.error_type is not None:
            require_str(self.error_type, "error_type", ValueError)
            if self.error_type not in ERROR_TYPES:
                raise ValueError(f"Bilinmeyen error_type: {self.error_type!r}")

        if self.error_type is None:
            if self.status_code is None:
                raise ValueError("HTTP yanıtı yoksa error_type zorunlu")
            if self.error is not None:
                raise ValueError("error yalnızca error_type ile birlikte dolu olabilir")
            if not isinstance(self.http_ok, bool):
                raise ValueError("HTTP yanıtı varsa http_ok bool olmalı")
        else:
            for name in ("duration_ms", "status_code", "http_ok", "business_outcome", "response_bytes"):
                if getattr(self, name) is not None:
                    raise ValueError(f"Taşıma hatası kaydında {name} boş olmalı")
            if self.error is None:
                raise ValueError("error_type varsa error zorunlu")

    @property
    def has_response(self) -> bool:
        return self.status_code is not None

    @property
    def succeeded(self) -> bool:
        """HTTP düzleminde başarı: yanıt alındı ve durum kodu beklenen değerlerden biri."""
        return self.http_ok is True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawResult":
        expected = set(cls.field_names())
        actual = set(data)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"Alanlar uyuşmuyor (eksik: {missing}, fazla: {extra})")
        return cls(**data)

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]
