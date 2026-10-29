"""Çalıştırma üst verisi: JSON sonuç dosyasına yazılan tekrarlanabilirlik bilgisi.

Gizlilik kuralları:
* Adı hassas görünen header/body alanları ve hassas sorgu değerleri maskelenir.
* Mutlak yerel yollar yazılmaz; dosyalar yalnızca adlarıyla anılır.
* Yapılandırma ve senaryo dosyalarının içeriği değil, yalnızca orijinal baytlarının
  SHA-256 özeti yazılır.
* Git'ten yalnızca HEAD commit kimliği ve çalışma ağacının temiz olup olmadığı alınır;
  dosya adları yazılmaz.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import math
import os
import platform
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import __version__
from .clock import ClockAnchor
from .config import LabConfig
from .models import DATASET_KINDS, DATASET_MEASUREMENT, DATASET_SYNTHETIC
from .response_parser import MAX_PARSE_BYTES, PARSER_VERSION, RECOGNIZED_BUSINESS_OUTCOMES
from .sanitize import REDACTED, SENSITIVE_KEY_RE, sanitize_url
from .scenarios import Scenario

__all__ = [
    "REDACTED",
    "build_run_metadata",
    "code_info",
    "config_snapshot",
    "dependency_versions",
    "environment_info",
    "file_sha256",
    "input_hashes",
    "redact",
    "response_parsing_section",
    "scenario_snapshot",
    "validate_dataset_kind",
    "validate_target_label",
]

GIT_TIMEOUT_SECONDS = 5.0
TRACKED_DEPENDENCIES = ("requests", "urllib3")
_PACKAGE_DIR = Path(__file__).resolve().parent
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")  # SHA-1 veya SHA-256


def redact(value: Any) -> Any:
    """İç içe sözlük/liste yapısında hassas anahtarların değerlerini maskeler (kopya döndürür)."""
    if isinstance(value, dict):
        return {
            key: REDACTED if SENSITIVE_KEY_RE.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def response_parsing_section(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Metadata'nın `response_parsing` bölümü: ayrıştırıcı sürümü, sınırı, tanınan değerler, kural sayıları, istekler."""
    rules: dict[str, int] = {}
    for entry in entries:
        rules[entry["rule_id"]] = rules.get(entry["rule_id"], 0) + 1
    return {
        "parser_version": PARSER_VERSION,
        "max_parse_bytes": MAX_PARSE_BYTES,
        "recognized_business_outcomes": sorted(RECOGNIZED_BUSINESS_OUTCOMES),
        "rules": dict(sorted(rules.items())),
        "requests": [dict(entry) for entry in entries],
    }


def scenario_snapshot(scenario: Scenario) -> dict[str, Any]:
    snapshot = redact(asdict(scenario))
    snapshot["path"] = sanitize_url(scenario.path)
    return snapshot


def config_snapshot(config: LabConfig) -> dict[str, Any]:
    """LabConfig.to_dict() ile aynı alanlar; yollar mutlak değil, yalnızca dosya/dizin adı."""
    snapshot = config.to_dict()
    for key in ("output_dir", "scenarios_file"):
        snapshot[key] = Path(snapshot[key]).name
    return snapshot


def environment_info() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }


def dependency_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in TRACKED_DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def code_info(
    *,
    cwd: Path = _PACKAGE_DIR,
    timeout: float = GIT_TIMEOUT_SECONDS,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    """Kodun Git commit kimliği ve çalışma ağacının temizliği.

    Git yoksa, kod bir depoda değilse veya komut zaman aşımına uğrarsa ilgili değerler None olur;
    bu durumlar hata sayılmaz. Komutlar sabit argümanlarla, kabuk kullanılmadan çalışır.
    """
    unknown: dict[str, Any] = {"git_commit": None, "git_dirty": None}
    options = dict(
        cwd=cwd,
        capture_output=True,
        timeout=timeout,
        check=False,
        shell=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},  # salt okuma: index kilidi alma
    )
    try:
        head = run(["git", "rev-parse", "--verify", "HEAD"], **options)
        if head.returncode != 0:
            return unknown
        commit = head.stdout.decode("ascii", errors="replace").strip()
        if not _GIT_SHA_RE.match(commit):
            return unknown
        status = run(["git", "status", "--porcelain"], **options)
        if status.returncode != 0:
            return {"git_commit": commit, "git_dirty": None}
        # Çıktı yalnızca boş olup olmadığına bakılarak kullanılır; dosya adları saklanmaz.
        return {"git_commit": commit, "git_dirty": bool(status.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        return unknown


def file_sha256(path: Path) -> str:
    """Dosyanın orijinal baytlarının SHA-256 özeti (hex)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hashes(config_path: Path | None, scenarios_path: Path | None) -> dict[str, Any]:
    """Girdi dosyalarının adları ve özetleri.

    Yol verilmemişse ya da okunamıyorsa özet None olur ve `hash_errors` içinde yalnızca
    hata türü (ör. FileNotFoundError) yazılır; mesaj, mutlak yol içerebileceği için yazılmaz.
    """
    result: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for label, path in (("config", config_path), ("scenarios", scenarios_path)):
        result[f"{label}_file"] = Path(path).name if path is not None else None
        if path is None:
            result[f"{label}_sha256"] = None
            errors[label] = "path_not_provided"
            continue
        try:
            result[f"{label}_sha256"] = file_sha256(Path(path))
        except OSError as exc:
            result[f"{label}_sha256"] = None
            errors[label] = type(exc).__name__
    result["hash_errors"] = errors
    return result


def validate_target_label(target_label: object) -> str | None:
    if target_label is not None and (not isinstance(target_label, str) or not target_label.strip()):
        raise ValueError("target_label boş olmayan bir metin olmalı")
    return target_label


def validate_dataset_kind(dataset_kind: object, synthetic: object) -> None:
    if dataset_kind not in DATASET_KINDS:
        raise ValueError(f"dataset_kind bilinmiyor: {dataset_kind!r}")
    if (dataset_kind == DATASET_SYNTHETIC) != (synthetic is not None):
        raise ValueError("synthetic bilgisi yalnızca ve her zaman dataset_kind='synthetic' ile verilir")
    if synthetic is not None and not isinstance(synthetic, dict):
        raise ValueError("synthetic bir sözlük olmalı")


def build_run_metadata(
    config: LabConfig,
    scenarios: Sequence[Scenario],
    started_at: str,
    finished_at: str,
    *,
    config_path: Path | None,
    monotonic_duration_ms: float | None,
    target_label: str | None = None,
    code: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    clock: ClockAnchor | None = None,
    dataset_kind: str = DATASET_MEASUREMENT,
    synthetic: dict[str, Any] | None = None,
    response_parsing: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bir çalıştırmanın metadata'sı.

    `code` ve `inputs` verilmezse burada hesaplanır; çalıştırma akışı bunları istekler başlamadan
    önce hesaplayıp verir. `execution`, çalıştırmanın durumunu (tamamlandı/durduruldu/kesildi) taşır.
    `clock`, runner'ın saat çapasıdır (bkz. clock.py); hiç istek başlamadıysa None yazılır.
    `dataset_kind` ölçüm ile sentetik deneyi ayırır; `synthetic` yalnızca sentetik deneyde dolu olur ve
    planlanan hataları DEĞİL, yalnızca deneyin kimliğini ve özetlerini taşır (bkz. synthetic.py).
    `response_parsing`, runner'ın istek başına yanıt ayrıştırma özetleridir (gövde içermez; bkz. response_parser.py).
    """
    if clock is not None and not isinstance(clock, ClockAnchor):
        raise ValueError(f"clock bir ClockAnchor olmalı (alınan: {type(clock).__name__})")
    validate_dataset_kind(dataset_kind, synthetic)
    if monotonic_duration_ms is not None and (
        isinstance(monotonic_duration_ms, bool)
        or not isinstance(monotonic_duration_ms, (int, float))
        or not math.isfinite(monotonic_duration_ms)
        or monotonic_duration_ms < 0
    ):
        raise ValueError(f"monotonic_duration_ms sonlu ve negatif olmayan bir sayı olmalı: {monotonic_duration_ms!r}")
    validate_target_label(target_label)

    document = {
        "tool_version": __version__,
        "dataset_kind": dataset_kind,
        "target_label": target_label,
        "started_at": started_at,
        "finished_at": finished_at,
        "monotonic_duration_ms": monotonic_duration_ms,
        "clock": clock.to_dict() if clock is not None else None,
        "execution": execution,
        "code": code if code is not None else code_info(),
        "dependencies": dependency_versions(),
        "environment": environment_info(),
        "inputs": inputs if inputs is not None else input_hashes(config_path, config.scenarios_file),
        "config": config_snapshot(config),
        "scenarios": [scenario_snapshot(s) for s in scenarios],
        "response_parsing": response_parsing_section(response_parsing or ()),
    }
    if synthetic is not None:
        document["synthetic"] = synthetic
    return document
