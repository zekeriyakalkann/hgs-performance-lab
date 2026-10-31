"""Yapılandırma, senaryo ve sonuç modelleri için ortak doğrulama yardımcıları.

Her yardımcı, hata durumunda çağıranın verdiği istisna sınıfını fırlatır.
"""

from __future__ import annotations

import json
import math
from collections.abc import Collection
from pathlib import Path
from typing import Any


def read_json_file(path: str | Path, error: type[Exception], what: str) -> Any:
    """JSON dosyasını okur; okuma ve ayrıştırma hatalarını `error` olarak bildirir."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise error(f"{what} bulunamadı: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise error(f"{what} okunamadı ({path}): {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise error(f"{what} geçerli JSON değil ({path}): {exc}") from exc


def reject_unknown_keys(data: dict, allowed: Collection[str], error: type[Exception], what: str) -> None:
    unknown = sorted(str(k) for k in data if k not in allowed)
    if unknown:
        raise error(f"{what}: bilinmeyen anahtar(lar): {', '.join(unknown)}")


def require_str(value: Any, field: str, error: type[Exception], *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise error(f"{field} metin olmalı (alınan: {type(value).__name__})")
    if not allow_empty and not value:
        raise error(f"{field} boş olamaz")
    return value


def require_int(value: Any, field: str, error: type[Exception], *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error(f"{field} tam sayı olmalı (alınan: {type(value).__name__})")
    if minimum is not None and value < minimum:
        raise error(f"{field} en az {minimum} olmalı (alınan: {value})")
    return value


def require_number(
    value: Any,
    field: str,
    error: type[Exception],
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error(f"{field} sayı olmalı (alınan: {type(value).__name__})")
    if not math.isfinite(value):
        raise error(f"{field} sonlu bir sayı olmalı (alınan: {value})")
    if positive and value <= 0:
        raise error(f"{field} pozitif olmalı (alınan: {value})")
    if non_negative and value < 0:
        raise error(f"{field} negatif olamaz (alınan: {value})")
    return float(value)
