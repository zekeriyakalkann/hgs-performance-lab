"""Yapılandırma yönetimi: JSON dosyasından doğrulanmış ayarlar yükler.

Kimlik bilgisi içermez; base_url içinde kullanıcı adı/parola da reddedilir.
Göreli yollar (output_dir, scenarios_file) yapılandırma dosyasının bulunduğu
dizine göre çözülür, çalışma dizinine göre değil.

`target_process` (isteğe bağlı, N12): hedef portu bu Lab süreci dışındaki bir süreç dinliyorsa o sürecin dosya adı
(ör. `python.exe`). Yükleme sırasında biçimi ve JVM/PostgreSQL adı olmadığı denetlenir; dinleyicinin gerçekten bu
süreç olduğu çalıştırmada, ilk istekten önce denetlenir (bkz. target_guard.check_listener). Verilmezse yalnızca Lab'in
kendi süreç içi sunucularına gidilebilir.

Yükleme sırasında ayrılmış port ve dinleyici denetimi YAPILMAZ: LabConfig sahte taşıyıcılı testlerde de kullanılır ve
dinleyici ancak çalıştırma anında okunabilir. Bu denetimler gerçek ağ taşıyıcısıyla çalıştırmada, ilk istekten önce
uygulanır (execution.execute_run).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from ._validate import read_json_file, reject_unknown_keys, require_int, require_number, require_str
from .target_process import validate_target_process

ALLOWED_KEYS = frozenset({"base_url", "timeout_seconds", "output_dir", "scenarios_file", "limits", "target_process"})

# Yapılandırmayla aşılamayan sabit tavanlar (bkz. README "İstek bütçesi ve durdurma").
HARD_MAX_REQUESTS = 10_000
HARD_MAX_DURATION_SECONDS = 3_600.0


class ConfigError(ValueError):
    """Geçersiz veya eksik yapılandırma."""


@dataclass(frozen=True)
class RunLimits:
    """Bir çalıştırmanın güvenlik sınırları.

    * max_requests: ısınma dahil toplam planlanan istek; aşılırsa hiçbir istek gönderilmez.
    * max_duration_seconds: çalıştırma süresi; dolunca yeni istek başlatılmaz.
    * max_consecutive_transport_errors: art arda bu kadar taşıma hatası (timeout/bağlantı) olursa durulur.
    * max_error_rate / error_rate_min_requests: en az bu kadar istekten sonra başarısız oran
      (taşıma hatası veya beklenmeyen HTTP durumu) eşiği aşarsa durulur.
    """

    max_requests: int = 1_000
    max_duration_seconds: float = 600.0
    max_consecutive_transport_errors: int = 5
    max_error_rate: float = 0.5
    error_rate_min_requests: int = 20

    def __post_init__(self) -> None:
        err = ConfigError
        require_int(self.max_requests, "limits.max_requests", err, minimum=1)
        if self.max_requests > HARD_MAX_REQUESTS:
            raise err(f"limits.max_requests en fazla {HARD_MAX_REQUESTS} olabilir")
        require_number(self.max_duration_seconds, "limits.max_duration_seconds", err, positive=True)
        if self.max_duration_seconds > HARD_MAX_DURATION_SECONDS:
            raise err(f"limits.max_duration_seconds en fazla {HARD_MAX_DURATION_SECONDS:g} olabilir")
        require_int(self.max_consecutive_transport_errors, "limits.max_consecutive_transport_errors", err, minimum=1)
        rate = require_number(self.max_error_rate, "limits.max_error_rate", err, positive=True)
        if rate > 1:
            raise err("limits.max_error_rate 0 ile 1 arasında olmalı (0 hariç)")
        require_int(self.error_rate_min_requests, "limits.error_rate_min_requests", err, minimum=1)

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_limits(raw: object) -> RunLimits:
    if not isinstance(raw, dict):
        raise ConfigError("limits bir nesne olmalı")
    reject_unknown_keys(raw, RunLimits.__dataclass_fields__.keys(), ConfigError, "limits")
    return RunLimits(**raw)


def _validate_base_url(base_url: object) -> None:
    require_str(base_url, "base_url", ConfigError)
    try:
        parts = urlsplit(base_url)
        parts.port  # noqa: B018 - geçersiz port burada ValueError üretir
    except ValueError as exc:
        raise ConfigError(f"base_url ayrıştırılamadı: {exc}") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError("base_url http:// veya https:// ile başlamalı ve ana makine adı içermeli")
    if parts.username is not None or parts.password is not None:
        raise ConfigError("base_url kimlik bilgisi içeremez")
    if parts.query or parts.fragment:
        raise ConfigError("base_url sorgu (?) veya parça (#) içeremez")


@dataclass(frozen=True)
class LabConfig:
    base_url: str
    timeout_seconds: float = 10.0
    output_dir: Path = Path("results")
    scenarios_file: Path = Path("scenarios.json")
    limits: RunLimits = field(default_factory=RunLimits)
    target_process: str | None = None

    def __post_init__(self) -> None:
        _validate_base_url(self.base_url)
        if self.target_process is not None:
            try:
                validate_target_process(self.target_process)
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc
        require_number(self.timeout_seconds, "timeout_seconds", ConfigError, positive=True)
        for name in ("output_dir", "scenarios_file"):
            if not isinstance(getattr(self, name), Path):
                raise ConfigError(f"{name} bir Path olmalı")
        if not isinstance(self.limits, RunLimits):
            raise ConfigError("limits bir RunLimits olmalı")

    def to_dict(self) -> dict:
        data = {
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "output_dir": str(self.output_dir),
            "scenarios_file": str(self.scenarios_file),
        }
        if self.target_process is not None:  # yalnızca verildiğinde: önceki metadata çıktıları değişmez
            data["target_process"] = self.target_process
        return data


def load_config(path: str | Path) -> LabConfig:
    path = Path(path)
    raw = read_json_file(path, ConfigError, "Yapılandırma dosyası")
    if not isinstance(raw, dict):
        raise ConfigError("Yapılandırma dosyası bir JSON nesnesi olmalı")
    reject_unknown_keys(raw, ALLOWED_KEYS, ConfigError, "Yapılandırma")
    if "base_url" not in raw:
        raise ConfigError("'base_url' alanı zorunlu")

    base_dir = path.resolve().parent
    kwargs: dict = {"base_url": raw["base_url"]}
    if "timeout_seconds" in raw:
        kwargs["timeout_seconds"] = raw["timeout_seconds"]
    if "limits" in raw:
        kwargs["limits"] = _parse_limits(raw["limits"])
    if "target_process" in raw:
        kwargs["target_process"] = raw["target_process"]
    for key, default in (("output_dir", "results"), ("scenarios_file", "scenarios.json")):
        value = require_str(raw.get(key, default), key, ConfigError)
        kwargs[key] = (base_dir / value).resolve()  # mutlak yol verilirse olduğu gibi kalır
    return LabConfig(**kwargs)
