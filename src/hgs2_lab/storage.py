"""Sonuç dosyası yönetimi: ham sonuçları CSV ve JSON olarak kaydeder/okur.

* Var olan bir run_id'nin dosyalarının üzerine yazılmaz.
* Yazım önce geçici dosyalara yapılır, sonra `os.replace` ile yayımlanır;
  ikinci yayımlama başarısız olursa birincisi geri alınır. (Kontrol ile
  yayımlama arasındaki çok kısa yarış penceresi, aynı run_id'yi aynı anda
  yazan iki süreç için kalır.)
* CSV ve JSON aynı `RawResult` alanlarını aynı sırayla taşır. CSV'de None boş
  hücre, bool ise `true`/`false` olarak yazılır; `load_csv` tipleri geri kazanır.
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, NamedTuple

from .models import RawResult, validate_run_id

SCHEMA_VERSION = 1
_RESERVED_METADATA_KEYS = frozenset({"schema_version", "run_id", "results"})


class StorageError(Exception):
    """Sonuç dosyası yazılamadı veya okunamadı."""


class ResultExistsError(StorageError):
    """Bu run_id için sonuç dosyaları zaten var."""


class StoredRun(NamedTuple):
    metadata: dict[str, Any]
    results: list[RawResult]


def _parse_bool(text: str) -> bool:
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"'true' veya 'false' bekleniyordu: {text!r}")


def _optional(parser: Callable[[str], Any]) -> Callable[[str], Any]:
    return lambda text: None if text == "" else parser(text)


_CSV_PARSERS: dict[str, Callable[[str], Any]] = {
    "run_id": str,
    "scenario": str,
    "iteration": int,
    "method": str,
    "url": str,
    "started_at": str,
    "elapsed_ms": float,
    "duration_ms": _optional(float),
    "status_code": _optional(int),
    "http_ok": _optional(_parse_bool),
    "business_outcome": _optional(str),
    "error_type": _optional(str),
    "error": _optional(str),
    "response_bytes": _optional(int),
}


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _render_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RawResult.field_names(), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(value) for key, value in row.items()})
    return buffer.getvalue()


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


class ResultStore:
    def __init__(self, output_dir: str | Path) -> None:
        self._dir = Path(output_dir)

    def paths(self, run_id: str) -> tuple[Path, Path]:
        validate_run_id(run_id)
        return self._dir / f"{run_id}.csv", self._dir / f"{run_id}.json"

    def save(
        self,
        run_id: str,
        results: Iterable[RawResult],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Path, Path]:
        csv_path, json_path = self.paths(run_id)  # run_id doğrulaması burada
        metadata = dict(metadata or {})
        reserved = sorted(_RESERVED_METADATA_KEYS & metadata.keys())
        if reserved:
            raise ValueError(f"Üst veri ayrılmış anahtarlar içeremez: {', '.join(reserved)}")

        results = list(results)
        for result in results:
            if result.run_id != run_id:
                raise StorageError(
                    f"Sonuç run_id'si ({result.run_id!r}) kaydedilen run_id ({run_id!r}) ile uyuşmuyor"
                )
        rows = [r.to_dict() for r in results]

        # Diske dokunmadan önce her şeyi bellekte üret: serileştirme hatası dosya bırakmaz.
        document = {"schema_version": SCHEMA_VERSION, "run_id": run_id, **metadata, "results": rows}
        json_text = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False)
        csv_text = _render_csv(rows)

        for path in (csv_path, json_path):
            if path.exists():
                raise ResultExistsError(f"Sonuç dosyası zaten var, üzerine yazılmaz: {path}")

        tmp_csv = csv_path.with_name(f"{csv_path.name}.{os.getpid()}.tmp")
        tmp_json = json_path.with_name(f"{json_path.name}.{os.getpid()}.tmp")
        published: list[Path] = []
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            _write_text(tmp_csv, csv_text)
            _write_text(tmp_json, json_text)
            os.replace(tmp_csv, csv_path)
            published.append(csv_path)
            os.replace(tmp_json, json_path)
            published.append(json_path)
        except OSError as exc:
            for path in published:
                path.unlink(missing_ok=True)
            raise StorageError(f"Sonuç dosyaları yazılamadı: {exc}") from exc
        finally:
            tmp_csv.unlink(missing_ok=True)
            tmp_json.unlink(missing_ok=True)
        return csv_path, json_path

    def load_json(self, run_id: str) -> StoredRun:
        _, json_path = self.paths(run_id)
        try:
            document = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise StorageError(f"JSON sonuç dosyası okunamadı ({json_path}): {exc}") from exc
        except json.JSONDecodeError as exc:
            raise StorageError(f"JSON sonuç dosyası geçerli değil ({json_path}): {exc}") from exc

        if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
            raise StorageError(f"Desteklenmeyen veya eksik schema_version (beklenen {SCHEMA_VERSION}): {json_path}")
        if document.get("run_id") != run_id:
            raise StorageError(f"Dosyadaki run_id ({document.get('run_id')!r}) istenen run_id ile uyuşmuyor")
        rows = document.get("results")
        if not isinstance(rows, list):
            raise StorageError(f"'results' listesi eksik: {json_path}")
        try:
            results = [RawResult.from_dict(row) for row in rows]
        except (TypeError, ValueError) as exc:
            raise StorageError(f"Geçersiz sonuç kaydı ({json_path}): {exc}") from exc
        metadata = {k: v for k, v in document.items() if k != "results"}
        return StoredRun(metadata=metadata, results=results)

    def load_csv(self, run_id: str) -> list[RawResult]:
        csv_path, _ = self.paths(run_id)
        try:
            with csv_path.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != RawResult.field_names():
                    raise StorageError(f"CSV başlığı beklenen alanlarla uyuşmuyor: {csv_path}")
                results = []
                for row in reader:
                    if None in row or None in row.values():
                        raise StorageError(f"CSV satır {reader.line_num}: sütun sayısı hatalı ({csv_path})")
                    try:
                        values = {name: _CSV_PARSERS[name](text) for name, text in row.items()}
                        results.append(RawResult.from_dict(values))
                    except ValueError as exc:
                        raise StorageError(f"CSV satır {reader.line_num} geçersiz ({csv_path}): {exc}") from exc
                return results
        except (OSError, UnicodeDecodeError) as exc:
            raise StorageError(f"CSV sonuç dosyası okunamadı ({csv_path}): {exc}") from exc
