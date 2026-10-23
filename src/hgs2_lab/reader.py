"""Kaydedilmiş bir çalıştırmayı analiz için okur ve doğrular (salt okuma; ağ erişimi yok).

* Dosya keşfi: `<run_id>.json/.csv` (tamamlanmış) ya da `<run_id>.partial.json/.csv` (kısmi).
  İkisinden biri eksikse veya hem tam hem kısmi dosyalar varsa açık bir hatayla reddedilir.
* Her dosya TEK kez bayt olarak okunur; SHA-256 özeti ve ayrıştırma aynı baytlardan yapılır.
* Şema sürümü storage.py'deki politikaya göre denetlenir (READABLE_SCHEMA_VERSIONS).
* JSON ve CSV aynı kayıtları aynı sırayla taşımalıdır.
* Kayıt bütünlüğü: her kaydın run_id'si dosyanınkiyle aynı, `seq` 1'den başlayıp kesintisiz artar.
* Metadata için en küçük güvenli doğrulama (`validate_metadata`): yalnızca analizin kullandığı
  alanların türü ve sonuçlarla tutarlılığı. Tanınmayan metadata anahtarları yok sayılır (ileriye
  uyumluluk); `execution` ve `clock` eski v2 dosyalarında bulunmayabilir ve bu hata değildir.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .clock import ClockAnchor, ClockAnchorError
from .models import DATASET_KINDS, DATASET_SYNTHETIC, EXECUTION_STATUSES, STATUS_COMPLETED, RawResult
from .storage import ResultStore, StorageError, parse_csv_text, parse_json_document


class RunDataError(StorageError):
    """Sonuç dosyaları eksik, bozuk veya birbiriyle tutarsız."""


@dataclass(frozen=True)
class InputFile:
    role: str  # "json" | "csv"
    name: str  # yalnızca dosya adı; mutlak yol tutulmaz
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "name": self.name, "sha256": self.sha256, "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class RunData:
    run_id: str
    partial: bool  # dosya adından: <run_id>.partial.*
    schema_version: int
    metadata: dict[str, Any]  # results hariç tüm üst düzey alanlar
    results: tuple[RawResult, ...]
    files: tuple[InputFile, ...]
    execution: dict[str, Any] | None  # eski v2 dosyalarında yok
    clock: ClockAnchor | None  # saat çapası yoksa None
    dataset_kind: str | None = None  # "measurement" | "synthetic"; bu alandan önceki dosyalarda None (bilinmiyor)


def find_run_files(results_dir: str | Path, run_id: str) -> tuple[bool, Path, Path]:
    """(partial, csv_path, json_path); dosyalar eksik ya da belirsizse RunDataError."""
    store = ResultStore(results_dir)  # run_id doğrulaması paths() içinde
    complete = store.paths(run_id, partial=False)
    partial = store.paths(run_id, partial=True)
    complete_found = [p for p in complete if p.is_file()]
    partial_found = [p for p in partial if p.is_file()]
    if complete_found and partial_found:
        raise RunDataError(f"{run_id!r} için hem tam hem kısmi (.partial) sonuç dosyaları var; hangisinin "
                           "analiz edileceği belirsiz")
    for is_partial, pair, found in ((False, complete, complete_found), (True, partial, partial_found)):
        if len(found) == 2:
            return is_partial, pair[0], pair[1]
        if found:
            missing = next(p.name for p in pair if p not in found)
            raise RunDataError(f"{run_id!r} için sonuç dosyası eksik: {missing} ({Path(results_dir)})")
    raise RunDataError(f"{run_id!r} için sonuç dosyası bulunamadı: {Path(results_dir)}")


def _read(path: Path, role: str) -> tuple[str, InputFile]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RunDataError(f"{role.upper()} sonuç dosyası okunamadı ({path.name}): {type(exc).__name__}") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunDataError(f"{role.upper()} sonuç dosyası UTF-8 değil ({path.name}): {exc}") from exc
    return text, InputFile(role, path.name, hashlib.sha256(data).hexdigest(), len(data))


def load_run(results_dir: str | Path, run_id: str) -> RunData:
    """Bir çalıştırmanın JSON ve CSV dosyalarını okur, doğrular ve birlikte döndürür."""
    is_partial, csv_path, json_path = find_run_files(results_dir, run_id)
    json_text, json_file = _read(json_path, "json")
    csv_text, csv_file = _read(csv_path, "csv")

    stored = parse_json_document(json_text, run_id=run_id, source=json_path.name)
    csv_results = parse_csv_text(csv_text, source=csv_path.name)
    _check_same_records(stored.results, csv_results)
    _check_records(run_id, stored.results)
    execution, clock = validate_metadata(stored.metadata, stored.results, partial=is_partial)
    dataset_kind = _validate_dataset_kind(stored.metadata)
    return RunData(
        run_id=run_id,
        partial=is_partial,
        schema_version=stored.metadata["schema_version"],
        metadata=stored.metadata,
        results=tuple(stored.results),
        files=(json_file, csv_file),
        execution=execution,
        clock=clock,
        dataset_kind=dataset_kind,
    )


def _validate_dataset_kind(metadata: dict[str, Any]) -> str | None:
    """`dataset_kind` yoksa None (eski dosya); varsa bilinen bir değer ve `synthetic` bölümüyle tutarlı olmalı."""
    kind = metadata.get("dataset_kind")
    synthetic = metadata.get("synthetic")
    if kind is not None and kind not in DATASET_KINDS:
        raise _fail(f"dataset_kind bilinmiyor: {kind!r}")
    if kind == DATASET_SYNTHETIC:
        if not isinstance(synthetic, dict):
            raise _fail("dataset_kind 'synthetic' ama synthetic bölümü yok")
        for key in ("experiment_id", "plan_sha256", "manifest_sha256"):
            if not isinstance(synthetic.get(key), str) or not synthetic[key]:
                raise _fail(f"synthetic.{key} boş olmayan bir metin olmalı")
        if not _is_int(synthetic.get("seed")):
            raise _fail("synthetic.seed bir tam sayı olmalı")
    elif synthetic is not None:
        raise _fail(f"synthetic bölümü var ama dataset_kind {kind!r}; sentetik veri açıkça işaretlenmeli")
    return kind


def _check_same_records(json_results: Sequence[RawResult], csv_results: Sequence[RawResult]) -> None:
    if len(json_results) != len(csv_results):
        raise RunDataError(f"CSV ve JSON kayıt sayıları uyuşmuyor (JSON {len(json_results)}, CSV {len(csv_results)})")
    for index, (a, b) in enumerate(zip(json_results, csv_results), start=1):
        if a != b:
            fields = [name for name in RawResult.field_names() if getattr(a, name) != getattr(b, name)]
            raise RunDataError(f"CSV ve JSON {index}. kayıtta uyuşmuyor (alanlar: {', '.join(fields)})")


def _check_records(run_id: str, results: Sequence[RawResult]) -> None:
    for index, result in enumerate(results, start=1):
        if result.run_id != run_id:
            raise RunDataError(f"{index}. kaydın run_id'si ({result.run_id!r}) dosyanınkiyle ({run_id!r}) uyuşmuyor")
        if result.seq != index:
            raise RunDataError(f"seq kesintisiz değil: {index}. kayıtta {result.seq} (beklenen {index})")


def _fail(message: str) -> RunDataError:
    return RunDataError(f"Metadata geçersiz: {message}")


def _optional_str(metadata: dict[str, Any], key: str) -> None:
    value = metadata.get(key)
    if value is not None and not isinstance(value, str):
        raise _fail(f"{key} metin ya da null olmalı (alınan: {type(value).__name__})")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_utc_timestamp(metadata: dict[str, Any], key: str) -> None:
    value = metadata.get(key)
    if value is None:
        return
    if not isinstance(value, str):
        raise _fail(f"{key} metin olmalı")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value  # Python 3.10 'Z' son ekini ayrıştırmaz
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _fail(f"{key} ISO 8601 zaman damgası değil: {value!r}") from exc
    if moment.tzinfo is None:
        raise _fail(f"{key} saat dilimi içermeli (UTC): {value!r}")


def _validate_execution(raw: Any, results: Sequence[RawResult], *, partial: bool) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _fail("execution bir nesne olmalı")
    status = raw.get("status")
    if status not in EXECUTION_STATUSES:
        raise _fail(f"execution.status bilinmiyor: {status!r}")
    for key in ("planned_requests", "completed_requests"):
        if not _is_int(raw.get(key)) or raw[key] < 0:
            raise _fail(f"execution.{key} negatif olmayan bir tam sayı olmalı (alınan: {raw.get(key)!r})")
    for key in ("stop_reason", "message"):
        if raw.get(key) is not None and not isinstance(raw[key], str):
            raise _fail(f"execution.{key} metin ya da null olmalı")
    planned, completed = raw["planned_requests"], raw["completed_requests"]
    if completed != len(results):
        raise _fail(f"execution.completed_requests ({completed}) kayıt sayısıyla ({len(results)}) uyuşmuyor")
    if completed > planned:
        raise _fail(f"execution.completed_requests ({completed}) planned_requests'ten ({planned}) büyük")
    if status == STATUS_COMPLETED:
        if partial:
            raise _fail("dosya kısmi (.partial) ama execution.status 'completed'")
        if completed != planned:
            raise _fail(f"execution.status 'completed' ama {completed}/{planned} istek kaydedilmiş")
        if raw.get("stop_reason") is not None:
            raise _fail("execution.status 'completed' iken stop_reason dolu olamaz")
    elif not partial:
        raise _fail(f"execution.status {status!r} ama dosya kısmi (.partial) olarak adlandırılmamış")
    return raw


def validate_metadata(
    metadata: dict[str, Any], results: Sequence[RawResult], *, partial: bool
) -> tuple[dict[str, Any] | None, ClockAnchor | None]:
    """Analizin kullandığı metadata alanlarını doğrular; (execution, clock) döndürür."""
    for key in ("tool_version", "target_label"):
        _optional_str(metadata, key)
    for key in ("started_at", "finished_at"):
        _check_utc_timestamp(metadata, key)

    duration = metadata.get("monotonic_duration_ms")
    if duration is not None and (
        not isinstance(duration, (int, float)) or isinstance(duration, bool)
        or not math.isfinite(duration) or duration < 0
    ):
        raise _fail(f"monotonic_duration_ms negatif olmayan sonlu bir sayı olmalı (alınan: {duration!r})")

    code = metadata.get("code")
    if code is not None:
        if not isinstance(code, dict):
            raise _fail("code bir nesne olmalı")
        if code.get("git_commit") is not None and not isinstance(code["git_commit"], str):
            raise _fail("code.git_commit metin ya da null olmalı")
        if code.get("git_dirty") is not None and not isinstance(code["git_dirty"], bool):
            raise _fail("code.git_dirty true/false ya da null olmalı")

    inputs = metadata.get("inputs")
    if inputs is not None and (not isinstance(inputs, dict) or not isinstance(inputs.get("hash_errors", {}), dict)):
        raise _fail("inputs bir nesne, inputs.hash_errors da bir nesne olmalı")

    scenarios = metadata.get("scenarios")
    if scenarios is not None:
        if not isinstance(scenarios, list) or not all(
            isinstance(s, dict) and isinstance(s.get("name"), str) for s in scenarios
        ):
            raise _fail("scenarios, 'name' alanı metin olan nesnelerin listesi olmalı")
        known = {s["name"] for s in scenarios}
        unknown = sorted({r.scenario for r in results} - known)
        if unknown:
            raise _fail(f"sonuçlarda metadata'da tanımlı olmayan senaryo(lar) var: {', '.join(unknown)}")

    execution = _validate_execution(metadata.get("execution"), results, partial=partial)

    clock = None
    if metadata.get("clock") is not None:
        try:
            clock = ClockAnchor.from_dict(metadata["clock"])
        except ClockAnchorError as exc:
            raise _fail(str(exc)) from exc
    return execution, clock
