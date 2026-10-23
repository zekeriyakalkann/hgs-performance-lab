"""Çalıştırma üst verisi: JSON sonuç dosyasına yazılan yapılandırma/senaryo/ortam anlık görüntüsü.

Gizli değerler yazılmaz: adı hassas görünen header/body alanları maskelenir.
"""

from __future__ import annotations

import os
import platform
import re
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from . import __version__
from .config import LabConfig
from .scenarios import Scenario

REDACTED = "***REDACTED***"
_SENSITIVE_RE = re.compile(
    r"(auth|bearer|cookie|token|secret|passw|api[-_]?key|credential|session)", re.IGNORECASE
)


def redact(value: Any) -> Any:
    """İç içe sözlük/liste yapısında hassas anahtarların değerlerini maskeler (kopya döndürür)."""
    if isinstance(value, dict):
        return {
            key: REDACTED if _SENSITIVE_RE.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def scenario_snapshot(scenario: Scenario) -> dict[str, Any]:
    return redact(asdict(scenario))


def environment_info() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }


def build_run_metadata(
    config: LabConfig,
    scenarios: Sequence[Scenario],
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    return {
        "tool_version": __version__,
        "started_at": started_at,
        "finished_at": finished_at,
        "environment": environment_info(),
        "config": config.to_dict(),
        "scenarios": [scenario_snapshot(s) for s in scenarios],
    }
