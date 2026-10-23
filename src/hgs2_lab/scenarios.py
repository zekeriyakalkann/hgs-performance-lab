"""Test senaryosu tanımları ve JSON'dan yüklenmesi."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._validate import read_json_file, reject_unknown_keys, require_int, require_number, require_str

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
ALLOWED_KEYS = frozenset(
    {"name", "method", "path", "repetitions", "delay_seconds", "headers", "body", "expected_status",
     "warmup_repetitions"}
)
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class ScenarioError(ValueError):
    """Geçersiz senaryo tanımı."""


@dataclass(frozen=True)
class Scenario:
    name: str
    method: str
    path: str
    repetitions: int = 1
    delay_seconds: float = 0.0
    headers: dict[str, str] = field(default_factory=dict)
    body: dict | None = None
    # Boşsa 2xx beklenir; doluysa yalnızca listedeki durum kodları http_ok sayılır.
    expected_status: tuple[int, ...] = ()
    # Ölçüm tekrarlarından önce yapılan, warmup=True olarak kaydedilen istek sayısı.
    warmup_repetitions: int = 0

    def __post_init__(self) -> None:
        err = ScenarioError
        require_str(self.name, "name", err)
        require_str(self.method, "method", err)
        if self.method not in ALLOWED_METHODS:
            raise err(f"Desteklenmeyen HTTP metodu: {self.method!r} (büyük harfli olmalı)")
        require_str(self.path, "path", err)
        if not self.path.startswith("/") or self.path.startswith("//") or re.search(r"\s", self.path):
            raise err(f"path tek '/' ile başlamalı ve boşluk içermemeli: {self.path!r}")
        require_int(self.repetitions, "repetitions", err, minimum=1)
        require_int(self.warmup_repetitions, "warmup_repetitions", err, minimum=0)
        require_number(self.delay_seconds, "delay_seconds", err, non_negative=True)

        if not isinstance(self.headers, dict):
            raise err("headers bir nesne (sözlük) olmalı")
        for key, value in self.headers.items():
            if not isinstance(key, str) or not _HEADER_NAME_RE.match(key):
                raise err(f"Geçersiz header adı: {key!r}")
            if not isinstance(value, str):
                raise err(f"header {key!r} değeri metin olmalı")

        if self.body is not None:
            if not isinstance(self.body, dict) or not all(isinstance(k, str) for k in self.body):
                raise err("body null veya anahtarları metin olan bir nesne olmalı")

        if not isinstance(self.expected_status, tuple):
            raise err("expected_status bir tuple olmalı")
        for code in self.expected_status:
            require_int(code, "expected_status öğesi", err, minimum=100)
            if code > 599:
                raise err(f"expected_status öğesi 100-599 aralığında olmalı (alınan: {code})")

    def is_expected_status(self, status_code: int) -> bool:
        if self.expected_status:
            return status_code in self.expected_status
        return 200 <= status_code < 300


def scenario_from_dict(data: Any) -> Scenario:
    if not isinstance(data, dict):
        raise ScenarioError(f"Senaryo bir nesne olmalı (alınan: {type(data).__name__})")
    reject_unknown_keys(data, ALLOWED_KEYS, ScenarioError, "Senaryo")
    for key in ("name", "method", "path"):
        if key not in data:
            raise ScenarioError(f"Senaryoda eksik alan: {key}")

    method = data["method"]
    if isinstance(method, str):
        method = method.upper()

    expected = data.get("expected_status", [])
    if not isinstance(expected, list):
        raise ScenarioError("expected_status bir liste olmalı")

    return Scenario(
        name=data["name"],
        method=method,
        path=data["path"],
        repetitions=data.get("repetitions", 1),
        delay_seconds=data.get("delay_seconds", 0.0),
        headers=data.get("headers", {}),
        body=data.get("body"),
        expected_status=tuple(expected),
        warmup_repetitions=data.get("warmup_repetitions", 0),
    )


def load_scenarios(path: str | Path) -> list[Scenario]:
    raw = read_json_file(path, ScenarioError, "Senaryo dosyası")
    if not isinstance(raw, dict):
        raise ScenarioError("Senaryo dosyası bir JSON nesnesi olmalı")
    reject_unknown_keys(raw, {"scenarios"}, ScenarioError, "Senaryo dosyası")

    items = raw.get("scenarios")
    if not isinstance(items, list):
        raise ScenarioError("'scenarios' listesi zorunlu")
    if not items:
        raise ScenarioError("'scenarios' listesi boş olamaz")

    scenarios = [scenario_from_dict(item) for item in items]
    names = [s.name for s in scenarios]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ScenarioError(f"Senaryo adları benzersiz olmalı (tekrar eden: {', '.join(duplicates)})")
    return scenarios
