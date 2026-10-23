"""Yapılandırma yönetimi: JSON dosyasından doğrulanmış ayarlar yükler.

Kimlik bilgisi içermez; base_url içinde kullanıcı adı/parola da reddedilir.
Göreli yollar (output_dir, scenarios_file) yapılandırma dosyasının bulunduğu
dizine göre çözülür, çalışma dizinine göre değil.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ._validate import read_json_file, reject_unknown_keys, require_number, require_str

ALLOWED_KEYS = frozenset({"base_url", "timeout_seconds", "output_dir", "scenarios_file"})


class ConfigError(ValueError):
    """Geçersiz veya eksik yapılandırma."""


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

    def __post_init__(self) -> None:
        _validate_base_url(self.base_url)
        require_number(self.timeout_seconds, "timeout_seconds", ConfigError, positive=True)
        for name in ("output_dir", "scenarios_file"):
            if not isinstance(getattr(self, name), Path):
                raise ConfigError(f"{name} bir Path olmalı")

    def to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "output_dir": str(self.output_dir),
            "scenarios_file": str(self.scenarios_file),
        }


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
    for key, default in (("output_dir", "results"), ("scenarios_file", "scenarios.json")):
        value = require_str(raw.get(key, default), key, ConfigError)
        kwargs[key] = (base_dir / value).resolve()  # mutlak yol verilirse olduğu gibi kalır
    return LabConfig(**kwargs)
