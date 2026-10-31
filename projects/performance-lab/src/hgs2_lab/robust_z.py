"""Robust Z-score gecikme dedektörü (F5): kalibrasyon ve skorlama; yalnızca sayılar üzerinde çalışır.

Bu modül tablo, etiket, sıra (`seq`, `iteration`, `offset_ms`) veya deney tasarımı GÖRMEZ: girdisi yalnızca
`duration_ms` değerlerinin listesidir. Satır seçimi ve değerlendirme `detection.py`'dedir.

Tanımlar (README "Değerlendirme protokolü"; parametreler değerlendirmeden önce sabitlenmiştir):
* x = ln(duration_ms); duration_ms pozitif ve sonlu bir sayı olmalıdır.
* median = median(x), MAD = median(|x − median|)  (kalibrasyon: train bölümünün doğrulanmış normal ölçümleri)
* z = 0.6745 · (x − median) / MAD
* alarm = z > 3.5  (yalnızca üst kuyruk; düşük gecikme anomali sayılmaz)

MAD = 0: sıfıra bölünmez ve MAD uydurulmaz. Baseline `degenerate_baseline` durumunu alır; hiçbir istek skorlanmaz
(z ve alarm null, durum `degenerate_baseline`). Geçersiz girdi (null, bool, sayı olmayan, NaN, ±inf, ≤ 0) hiçbir zaman
normal sayılmaz: kalibrasyonda hata, skorlamada `invalid_input` durumu.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

DETECTOR_NAME = "robust_z"
DETECTOR_VERSION = "robust-z-v1"
INPUT_FIELDS = ("duration_ms",)  # açık izin listesi; başka hiçbir sütun dedektöre verilmez
TRANSFORM = "natural_log"
Z_CONSTANT = 0.6745
THRESHOLD = 3.5
DIRECTION = "upper"

BASELINE_OK = "ok"
BASELINE_DEGENERATE = "degenerate_baseline"
STATUS_SCORED = "scored"
STATUS_INVALID_INPUT = "invalid_input"
STATUS_DEGENERATE = BASELINE_DEGENERATE


class CalibrationError(ValueError):
    """Kalibrasyon yapılamadı (boş veya geçersiz değer içeren kalibrasyon kümesi)."""


def invalid_reason(value: Any) -> str | None:
    """duration_ms neden geçersiz; geçerliyse None."""
    if value is None:
        return "missing"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "not_a_number"
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "infinite"
    if value <= 0:
        return "non_positive"
    return None


@dataclass(frozen=True)
class Baseline:
    n: int
    median_log: float
    mad_log: float
    status: str  # ok | degenerate_baseline
    median_duration_ms: float  # exp(median_log): yorum kolaylığı için

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Prediction:
    status: str  # scored | invalid_input | degenerate_baseline
    x: float | None
    z: float | None
    alarm: bool | None
    reason: str | None = None


def calibrate(durations: Sequence[Any]) -> Baseline:
    """Normal ölçümlerin duration_ms değerlerinden baseline. Geçersiz değer varsa CalibrationError (dışlanmaz)."""
    if not durations:
        raise CalibrationError("kalibrasyon kümesi boş: train bölümünde doğrulanmış normal ölçüm yok")
    invalid: dict[str, int] = {}
    for value in durations:
        reason = invalid_reason(value)
        if reason is not None:
            invalid[reason] = invalid.get(reason, 0) + 1
    if invalid:
        raise CalibrationError(f"kalibrasyon kümesinde geçersiz duration_ms değerleri var ({invalid}); sessizce "
                               "dışlanmaz")
    xs = [math.log(float(v)) for v in durations]
    median = statistics.median(xs)
    mad = statistics.median([abs(x - median) for x in xs])
    status = BASELINE_OK if mad > 0 else BASELINE_DEGENERATE
    return Baseline(n=len(xs), median_log=median, mad_log=mad, status=status, median_duration_ms=math.exp(median))


def score(baseline: Baseline, duration_ms: Any) -> Prediction:
    """Tek bir duration_ms değerinin skoru; aynı girdi -> aynı sonuç."""
    reason = invalid_reason(duration_ms)
    if reason is not None:
        return Prediction(STATUS_INVALID_INPUT, None, None, None, reason)
    x = math.log(float(duration_ms))
    if baseline.status != BASELINE_OK:
        return Prediction(STATUS_DEGENERATE, x, None, None, "mad_zero")
    z = Z_CONSTANT * (x - baseline.median_log) / baseline.mad_log
    return Prediction(STATUS_SCORED, x, z, z > THRESHOLD)


def threshold_duration_ms(baseline: Baseline) -> float | None:
    """Eşiğin duration_ms karşılığı: z > THRESHOLD ⇔ duration_ms > bu değer (yorum için; karar z ile verilir)."""
    if baseline.status != BASELINE_OK:
        return None
    return math.exp(baseline.median_log + THRESHOLD * baseline.mad_log / Z_CONSTANT)


def describe() -> dict[str, Any]:
    return {
        "name": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "input_fields": list(INPUT_FIELDS),
        "transform": f"x = ln(duration_ms) ({TRANSFORM}); duration_ms pozitif ve sonlu olmalı",
        "formula": f"z = {Z_CONSTANT} * (x - median) / MAD; median = median(x), MAD = median(|x - median|)",
        "threshold": THRESHOLD,
        "direction": f"{DIRECTION}: alarm = z > {THRESHOLD}; düşük gecikme anomali sayılmaz",
        "parameters_fixed_before_evaluation": True,
        "mad_zero": "sıfıra bölünmez, MAD uydurulmaz: baseline.status = degenerate_baseline, hiçbir istek skorlanmaz "
                    "(z = alarm = null), metrikler null",
        "invalid_input": "null, sayı olmayan, NaN, ±inf veya ≤ 0: kalibrasyonda hata; skorlamada status = "
                         "invalid_input (normal sayılmaz, metriklere girmez, ayrıca sayılır)",
    }
