"""Çevrimdışı istatistiksel baseline analizi: kaydedilmiş bir çalıştırmadan özet metrikler.

Yalnızca reader.py'nin okuduğu yerel dosyaları kullanır; ağ erişimi ve HTTP isteği yoktur.
Yalnızca standart kütüphane kullanılır.

Yöntem (ayrıntılar README "Analiz"):
* Gruplar: tüm çalıştırma (`overall`) ve her senaryo. Isınma istekleri ayrı sayılır, hiçbir
  süre/oran/throughput metriğine girmez.
* Yanıt süresi: ölçüm isteklerinden `http_ok=true` olanların `duration_ms` değerleri.
* Yüzdelikler: doğrusal interpolasyon (Hyndman-Fan tip 7); kesirli ağırlık `fractions` ile tam hesaplanır.
* Örneklem yeterliliği: kuyruk yüzdeliği p için en az `ceil(min_tail_samples / (1 - p/100))`
  gözlem; altında değer üretilmez (null + "insufficient_sample").
* Güven aralığı: yüzdelik bootstrap. Her grup kendi rastgele akışını `seed` ve grup adından türetir;
  örnekleme yalnızca `random.Random.random()` ile yapılır (Python sürümleri arasında aynı dizi
  belgelenmiş tek garanti budur).
* Throughput: yalnızca grubun ölçüm istekleri kesintisiz bir `seq` bloğu oluşturuyorsa (pencerede
  başka istek yoksa) hesaplanır.

Determinizm: `analysis` içeriği yalnızca girdi dosyalarına ve parametrelere bağlıdır; üretim zamanı
bu içeriğin DIŞINDA (`generated_at`) tutulur ve `content_sha256` yalnızca içeriği özetler.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

from . import __version__
from .models import DATASET_SYNTHETIC, STATUS_COMPLETED, RawResult
from .reader import RunData

ANALYSIS_FORMAT = "hgs2-lab-analysis"
ANALYSIS_SCHEMA_VERSION = 1
PERCENTILES = (50, 90, 95, 99)
ANALYSIS_DIR_NAME = "analysis"

STATUS_OK = "ok"
STATUS_NO_DATA = "no_data"
STATUS_INSUFFICIENT = "insufficient_sample"
STATUS_NOT_COMPUTED = "not_computed"

_MAX_SEED = 2**63 - 1

STATIC_LIMITATIONS = (
    "Analiz yalnızca kaydedilmiş sonuç dosyalarına dayanır; hedef sisteme erişilmez, ölçüm tekrarlanmaz.",
    "Analiz, hedefin gerçek HGS2 olup olmadığını doğrulamaz; target_label yalnızca bir etikettir.",
    "Anomali tespiti veya makine öğrenmesi modeli içermez; yalnızca betimleyici istatistiklerdir.",
    "duration_ms istemci tarafında ölçülür; ağ ve istemci ek yükünü, yeni bağlantılarda bağlantı kurulumunu "
    "ve ad çözümlemesini içerebilir. Bağlantının yeniden kullanılıp kullanılmadığı kaydedilmez.",
    "İstekler tek iş parçacığında sırayla (kapalı döngü) gönderilir; throughput bu çalıştırmada gözlenen "
    "istek hızıdır (senaryo gecikmeleri dahil), sunucu kapasitesi değildir.",
    "Bootstrap güven aralıkları gözlemlerin bağımsız ve aynı dağılımlı olduğunu varsayar; ardışık istekler "
    "arasındaki bağımlılık (ısınma, önbellek, çöp toplama) aralıkları olduğundan dar gösterebilir.",
    "Tek bir çalıştırma analiz edilir; çalıştırmalar arası değişkenlik ölçülmez.",
)


class AnalysisError(ValueError):
    """Geçersiz analiz parametresi."""


class AnalysisOutputError(Exception):
    """Analiz çıktısı yazılamadı."""


class AnalysisExistsError(AnalysisOutputError):
    """Çıktı dosyası zaten var; üzerine yazılmaz."""


@dataclass(frozen=True)
class AnalysisParams:
    seed: int = 0
    bootstrap_resamples: int = 2000
    confidence: float = 0.95
    min_tail_samples: int = 10  # kuyruk yüzdeliğinin üstünde beklenen en az gözlem
    min_bootstrap_samples: int = 20  # güven aralığı için en az gözlem
    min_throughput_requests: int = 10

    def __post_init__(self) -> None:
        def require_int(name: str, low: int, high: int) -> None:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise AnalysisError(f"{name} {low}..{high} aralığında bir tam sayı olmalı (alınan: {value!r})")

        require_int("seed", 0, _MAX_SEED)
        require_int("bootstrap_resamples", 100, 100_000)
        require_int("min_tail_samples", 1, 1_000)
        require_int("min_bootstrap_samples", 2, 100_000)
        require_int("min_throughput_requests", 2, 100_000)
        c = self.confidence
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or not 0.5 <= c <= 0.999:
            raise AnalysisError(f"confidence 0.5..0.999 aralığında olmalı (alınan: {c!r})")

    @property
    def confidence_fraction(self) -> Fraction:
        return Fraction(repr(float(self.confidence)))  # 0.95 -> 19/20 (ikili kayan nokta hatası olmadan)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- temel istatistikler ---
def quantile(sorted_values: Sequence[float], q: Fraction) -> float:
    """Sıralı veride q-yüzdeliği (Hyndman-Fan tip 7, doğrusal interpolasyon; numpy varsayılanı)."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("boş veride yüzdelik tanımsız")
    if not 0 <= q <= 1:
        raise ValueError(f"q 0..1 aralığında olmalı (alınan: {q})")
    h = (n - 1) * q
    lo = math.floor(h)
    frac = h - lo
    if frac == 0:
        return float(sorted_values[lo])
    a, b = sorted_values[lo], sorted_values[lo + 1]
    return a + float(frac) * (b - a)


def min_samples_for_percentile(p: int, min_tail_samples: int) -> int:
    """p > 50 için ceil(min_tail_samples / (1 - p/100)); medyan ve altı için 1."""
    if p <= 50:
        return 1
    return -(-min_tail_samples * 100 // (100 - p))


def group_seed(seed: int, group_key: str) -> int:
    """Grup başına bağımsız ve kararlı tohum: başka bir grubun eklenmesi bu grubun sonucunu değiştirmez."""
    digest = hashlib.sha256(f"{seed}:{group_key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def bootstrap_percentile_intervals(
    sorted_values: Sequence[float],
    percentiles: Sequence[int],
    *,
    resamples: int,
    confidence: Fraction,
    seed: int,
) -> dict[int, tuple[float, float]]:
    """Yüzdelik bootstrap güven aralıkları; aynı tohumla her çalıştırmada aynı sonuç."""
    n = len(sorted_values)
    rng = random.Random(seed)
    rand = rng.random
    last = n - 1
    estimates: dict[int, list[float]] = {p: [] for p in percentiles}
    qs = {p: Fraction(p, 100) for p in percentiles}
    for _ in range(resamples):
        sample = sorted([sorted_values[min(int(rand() * n), last)] for _ in range(n)])
        for p in percentiles:
            estimates[p].append(quantile(sample, qs[p]))
    alpha = (1 - confidence) / 2
    intervals = {}
    for p in percentiles:
        dist = sorted(estimates[p])
        intervals[p] = (quantile(dist, alpha), quantile(dist, 1 - alpha))
    return intervals


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _label(p: int) -> str:
    return "median" if p == 50 else f"p{p}"


# --- grup metrikleri ---
def _counts(records: Sequence[RawResult]) -> dict[str, Any]:
    http_errors = [r for r in records if r.http_ok is False]
    transport = [r for r in records if r.error_type is not None]
    return {
        "total": len(records),
        "http_responses": sum(r.has_response for r in records),
        "successful": sum(r.http_ok is True for r in records),
        "http_errors": len(http_errors),
        "transport_errors": len(transport),
        "failed": len(http_errors) + len(transport),
        "http_errors_by_status": {str(k): v for k, v in sorted(Counter(r.status_code for r in http_errors).items())},
        "transport_errors_by_type": dict(sorted(Counter(r.error_type for r in transport).items())),
    }


def _rates(counts: dict[str, Any]) -> dict[str, Any]:
    n = counts["total"]
    return {
        "status": STATUS_OK if n else STATUS_NO_DATA,
        "denominator": n,
        "success_rate": _rate(counts["successful"], n),
        "failure_rate": _rate(counts["failed"], n),
        "http_error_rate": _rate(counts["http_errors"], n),
        "transport_error_rate": _rate(counts["transport_errors"], n),
    }


def _response_time(values: list[float], params: AnalysisParams, seed_key: str) -> dict[str, Any]:
    n = len(values)
    entries: dict[str, Any] = {}
    to_bootstrap = []
    for p in PERCENTILES:
        needed = min_samples_for_percentile(p, params.min_tail_samples)
        if n == 0:
            status, value = STATUS_NO_DATA, None
        elif n < needed:
            status, value = STATUS_INSUFFICIENT, None
        else:
            status, value = STATUS_OK, quantile(values, Fraction(p, 100))
        ci_needed = max(needed, params.min_bootstrap_samples)
        if status != STATUS_OK:
            ci = {"status": status, "lower": None, "upper": None, "min_samples": ci_needed}
        elif n < ci_needed:
            ci = {"status": STATUS_INSUFFICIENT, "lower": None, "upper": None, "min_samples": ci_needed}
        else:
            ci = {"status": STATUS_OK, "lower": None, "upper": None, "min_samples": ci_needed}
            to_bootstrap.append(p)
        entries[_label(p)] = {"status": status, "value": value, "min_samples": needed, "ci": ci}

    if to_bootstrap:
        intervals = bootstrap_percentile_intervals(
            values, to_bootstrap, resamples=params.bootstrap_resamples,
            confidence=params.confidence_fraction, seed=group_seed(params.seed, seed_key),
        )
        for p, (lower, upper) in intervals.items():
            entries[_label(p)]["ci"].update(lower=lower, upper=upper)

    return {
        "status": STATUS_OK if n else STATUS_NO_DATA,
        "n": n,
        "min": values[0] if n else None,
        "max": values[-1] if n else None,
        **entries,
    }


def _throughput(measured: Sequence[RawResult], params: AnalysisParams) -> dict[str, Any]:
    n = len(measured)
    result: dict[str, Any] = {
        "status": STATUS_NOT_COMPUTED, "reason": None, "n": n,
        "window_ms": None, "requests_per_second": None, "successful_per_second": None,
    }
    if n < params.min_throughput_requests:
        result["status"] = STATUS_NO_DATA if n == 0 else STATUS_INSUFFICIENT
        result["reason"] = f"en az {params.min_throughput_requests} ölçüm isteği gerekir, n={n}"
        return result
    first_seq = measured[0].seq
    if [r.seq for r in measured] != list(range(first_seq, first_seq + n)):
        result["reason"] = "ölçüm penceresinde başka istekler (ısınma veya başka senaryo) var"
        return result
    if any(b.offset_ms < a.offset_ms for a, b in zip(measured, measured[1:])):
        result["reason"] = "offset_ms değerleri seq sırasıyla artmıyor"
        return result
    start = measured[0].offset_ms
    end = max(r.offset_ms + r.elapsed_ms for r in measured)
    window_ms = end - start
    if window_ms <= 0:
        result["reason"] = "ölçüm penceresi sıfır uzunlukta"
        return result
    seconds = window_ms / 1000
    result.update(
        status=STATUS_OK,
        window_ms=window_ms,
        requests_per_second=n / seconds,
        successful_per_second=sum(r.http_ok is True for r in measured) / seconds,
    )
    return result


def _group(
    records: Sequence[RawResult], scope: str, params: AnalysisParams, warnings: list[dict[str, str]]
) -> dict[str, Any]:
    warmup = [r for r in records if r.warmup]
    measured = [r for r in records if not r.warmup]
    measured_counts = _counts(measured)
    latencies = sorted(r.duration_ms for r in measured if r.http_ok is True and r.duration_ms is not None)
    response_time = _response_time(latencies, params, scope)
    throughput = _throughput(measured, params)

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "scope": scope, "message": message})

    if not measured:
        warn("no_measured_requests", "Ölçüm isteği yok; süre, oran ve throughput hesaplanmadı.")
    else:
        if not latencies:
            warn("no_successful_responses", "Başarılı (http_ok=true) ölçüm yanıtı yok; yanıt süresi hesaplanmadı.")
        if measured_counts["http_errors"]:
            warn("http_errors_present", f"{measured_counts['http_errors']} ölçüm isteği beklenmeyen HTTP durumu "
                                        "aldı; bu yanıtların süreleri yanıt süresi dağılımına girmez.")
        if measured_counts["transport_errors"]:
            warn("transport_errors_present", f"{measured_counts['transport_errors']} ölçüm isteğinde taşıma hatası "
                                             "(yanıt yok); bunların süresi yoktur.")
        short = [
            f"{_label(p)} (gereken {response_time[_label(p)]['min_samples']})"
            for p in PERCENTILES if response_time[_label(p)]["status"] == STATUS_INSUFFICIENT
        ]
        short_ci = [
            _label(p) for p in PERCENTILES
            if response_time[_label(p)]["status"] == STATUS_OK and response_time[_label(p)]["ci"]["status"] != STATUS_OK
        ]
        if short:
            warn("insufficient_sample", f"n={response_time['n']}: {', '.join(short)} için örneklem yetersiz; "
                                        "değer üretilmedi.")
        if short_ci:
            warn("insufficient_sample_ci", f"n={response_time['n']}: {', '.join(short_ci)} için güven aralığı "
                                           f"üretilmedi (en az {params.min_bootstrap_samples} gözlem).")
        if throughput["status"] != STATUS_OK:
            warn("throughput_not_computed", f"Throughput hesaplanmadı: {throughput['reason']}.")

    return {
        "requests": {"total": len(records), "warmup": len(warmup), "measured": len(measured)},
        "warmup": _counts(warmup),
        "measured": measured_counts,
        "rates": _rates(measured_counts),
        "response_time_ms": response_time,
        "throughput": throughput,
    }


# --- çalıştırma düzeyi ---
def _run_section(run: RunData, warnings: list[dict[str, str]], limitations: list[str]) -> dict[str, Any]:
    meta = run.metadata

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "scope": "run", "message": message})

    execution = run.execution
    if execution is None:
        warn("execution_metadata_missing", "Metadata'da execution bilgisi yok (eski v2 dosyası); planlanan istek "
                                           "sayısı ve çalıştırmanın tamamlanıp tamamlanmadığı bilinmiyor.")
        exec_summary = {"available": False, "status": None, "stop_reason": None,
                        "planned_requests": None, "recorded_requests": len(run.results), "not_executed": None}
    else:
        planned = execution["planned_requests"]
        exec_summary = {"available": True, "status": execution["status"], "stop_reason": execution.get("stop_reason"),
                        "planned_requests": planned, "recorded_requests": len(run.results),
                        "not_executed": planned - len(run.results)}
    if run.partial or (execution is not None and execution["status"] != STATUS_COMPLETED):
        status = execution["status"] if execution else "bilinmiyor"
        reason = execution.get("stop_reason") if execution else None
        warn("run_incomplete", f"Çalıştırma tamamlanmadı (durum: {status}, neden: {reason}); metrikler yalnızca "
                               "kaydedilen istekleri kapsar.")
        limitations.append(
            f"Kısmi çalıştırma: {len(run.results)} kayıtlı istek"
            + (f" / {execution['planned_requests']} planlanan" if execution else "")
            + "; sonuçlar planlanan deneyin tamamını temsil etmez."
        )

    code = meta.get("code")
    if not isinstance(code, dict) or code.get("git_commit") is None or code.get("git_dirty") is None:
        warn("code_state_unknown", "Ölçümü yapan kodun Git commit'i veya çalışma ağacı durumu bilinmiyor.")
    elif code["git_dirty"]:
        warn("working_tree_dirty", "Ölçüm, commit edilmemiş değişiklikler içeren bir çalışma ağacıyla yapıldı.")

    inputs = meta.get("inputs")
    if not isinstance(inputs, dict) or inputs.get("hash_errors") or any(
        inputs.get(k) is None for k in ("config_sha256", "scenarios_sha256")
    ):
        warn("input_hash_unavailable", "Ölçümdeki yapılandırma/senaryo dosyalarının özetleri eksik; girdiler "
                                       "tam olarak doğrulanamaz.")

    offsets = [r.offset_ms for r in run.results]
    if any(b < a for a, b in zip(offsets, offsets[1:])):
        warn("offsets_not_monotonic", "offset_ms değerleri seq sırasıyla artmıyor; zaman serisi yorumlanırken "
                                      "dikkat edilmeli.")

    synthetic = None
    if run.dataset_kind == DATASET_SYNTHETIC:
        raw = meta["synthetic"]
        synthetic = {k: raw.get(k) for k in ("experiment_id", "seed", "manifest_sha256", "plan_sha256")}
        warn("synthetic_data", f"Sentetik deney verisi (experiment_id: {raw.get('experiment_id')}); gerçek HGS2 "
                               "ölçümü değildir. Planlanan hatalar ve etiketler ayrı dosyadadır; bu analiz onları "
                               "kullanmaz.")
        limitations.append("Sentetik veri: sonuçlar uygulamanın kendi yerel test sunucusuna karşı planlı hatalarla "
                           "üretildi; HGS2'nin performansı hakkında bilgi vermez.")

    return {
        "run_id": run.run_id,
        "partial": run.partial,
        "dataset_kind": run.dataset_kind,
        "synthetic": synthetic,
        "execution": exec_summary,
        "target_label": meta.get("target_label"),
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "monotonic_duration_ms": meta.get("monotonic_duration_ms"),
        "source_tool_version": meta.get("tool_version"),
        "code": code if isinstance(code, dict) else None,
    }


def _clock_section(run: RunData, warnings: list[dict[str, str]]) -> dict[str, Any]:
    if run.clock is None:
        warnings.append({
            "code": "clock_anchor_missing", "scope": "run",
            "message": "Metadata'da saat çapası (clock) yok; offset_ms değerleri UTC zamana çevrilemez ve "
                       "telemetri hizalaması kullanılamaz.",
        })
        return {"available": False, "anchor": None, "telemetry_alignment": "unavailable",
                "note": "Saat çapası yok (bu özellikten önce yazılmış dosya veya hiç istek başlamadı)."}
    return {
        "available": True,
        "anchor": run.clock.to_dict(),
        "telemetry_alignment": "same_process_only",
        "note": "offset_ms -> UTC dönüşümü yalnızca aynı süreçteki monotonik saat için geçerlidir "
                f"(belirsizlik en çok read_window_ns = {run.clock.read_window_ns} ns). Süreçler veya makineler "
                "arası saat eşitliği doğrulanmamıştır.",
    }


def _method(params: AnalysisParams) -> dict[str, Any]:
    return {
        "parameters": params.to_dict(),
        "groups": "overall (tüm senaryolar) ve her senaryo; senaryolar ilk görüldükleri sırada",
        "warmup": "ısınma istekleri yalnızca sayılır; süre, oran ve throughput metriklerine girmez",
        "response_time": {
            "field": "duration_ms",
            "population": "ölçüm istekleri (warmup=false) içinde http_ok=true olanlar",
            "percentiles": list(PERCENTILES),
            "percentile_method": "doğrusal interpolasyon, Hyndman-Fan tip 7 (numpy varsayılanı)",
            "min_samples_rule": "p > 50 için n >= ceil(min_tail_samples / (1 - p/100)); medyan için n >= 1",
        },
        "rates": "pay / ölçüm isteği sayısı; failed = http_errors + transport_errors",
        "bootstrap": {
            "method": "yüzdelik bootstrap (yerine koyarak yeniden örnekleme)",
            "rng": "random.Random(grup tohumu); grup tohumu = sha256('<seed>:<grup>') ilk 8 bayt; "
                   "indeks = floor(random() * n)",
            "applies_when": "yüzdelik değeri üretildi ve n >= max(yüzdeliğin gerektirdiği n, min_bootstrap_samples)",
        },
        "throughput": "ölçüm istekleri / (son ölçüm isteğinin bitişi - ilk ölçüm isteğinin başlangıcı); "
                      "yalnızca pencerede başka istek yoksa ve n >= min_throughput_requests ise",
    }


def build_analysis(run: RunData, params: AnalysisParams | None = None) -> dict[str, Any]:
    """Deterministik analiz içeriği (üretim zamanı içermez)."""
    params = params or AnalysisParams()
    warnings: list[dict[str, str]] = []
    limitations = list(STATIC_LIMITATIONS)

    run_section = _run_section(run, warnings, limitations)
    clock_section = _clock_section(run, warnings)
    scenario_names = list(dict.fromkeys(r.scenario for r in run.results))
    if len(scenario_names) > 1:
        warnings.append({
            "code": "pooled_scenarios", "scope": "overall",
            "message": f"overall {len(scenario_names)} senaryonun isteklerini birleştirir; farklı uç noktaların "
                       "dağılımları karışır, yorum senaryo bazında yapılmalı.",
        })
    overall = _group(run.results, "overall", params, warnings)
    scenarios = [
        {"scenario": name, **_group([r for r in run.results if r.scenario == name], f"scenario:{name}", params,
                                    warnings)}
        for name in scenario_names
    ]
    return {
        "tool": {"name": "hgs2-lab", "version": __version__},
        "input": {
            "run_id": run.run_id,
            "schema_version": run.schema_version,
            "partial": run.partial,
            "files": [f.to_dict() for f in run.files],
        },
        "method": _method(params),
        "run": run_section,
        "clock": clock_section,
        "overall": overall,
        "scenarios": scenarios,
        "warnings": warnings,
        "limitations": limitations,
    }


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_document(
    run: RunData, params: AnalysisParams | None = None, *, now: Callable[[], str] = _utc_now_iso
) -> dict[str, Any]:
    """Çıktı belgesi: değişken `generated_at` + deterministik `analysis` ve onun özeti."""
    content = build_analysis(run, params)
    return {
        "format": ANALYSIS_FORMAT,
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "generated_at": now(),  # determinizm garantisinin dışında
        "content_sha256": hashlib.sha256(canonical_json(content)).hexdigest(),
        "analysis": content,
    }


def default_output_path(results_dir: str | Path, run: RunData) -> Path:
    """`<results_dir>/analysis/<run_id>[.partial].analysis.json`: ham sonuçlardan ayrı bir dizin."""
    stem = f"{run.run_id}.partial" if run.partial else run.run_id
    return Path(results_dir) / ANALYSIS_DIR_NAME / f"{stem}.analysis.json"


def write_document(document: dict[str, Any], path: str | Path) -> Path:
    """JSON belgesini atomik olarak ve ÜZERİNE YAZMADAN yayımlar (bkz. write_text_exclusive)."""
    text = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"  # diske dokunmadan önce
    return write_text_exclusive(text, path)


def write_text_exclusive(text: str, path: str | Path) -> Path:
    """Metni UTF-8 olarak, satır sonu dönüşümü yapmadan, atomik ve ÜZERİNE YAZMADAN yayımlar.

    Önce geçici dosyaya yazılır, sonra sabit bağlantı (`os.link`) ile hedef adla yayımlanır: hedef
    varsa işlem başarısız olur (`os.replace`'in aksine). Sabit bağlantı desteklenmeyen dosya
    sistemlerinde, hedef yalnızca yoksa oluşturan özel kip (`x`) kullanılır.
    """
    path = Path(path)
    if path.exists():
        raise AnalysisExistsError(f"Analiz dosyası zaten var, üzerine yazılmaz: {path}")
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8", newline="") as f:  # süreç kimliğine özgü geçici dosya
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise
        except OSError:  # sabit bağlantı desteklenmiyor
            _write_exclusive(path, text)
    except FileExistsError as exc:
        raise AnalysisExistsError(f"Analiz dosyası zaten var, üzerine yazılmaz: {path}") from exc
    except OSError as exc:
        raise AnalysisOutputError(f"Analiz dosyası yazılamadı ({path}): {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _write_exclusive(path: Path, text: str) -> None:
    created = False
    try:
        with path.open("x", encoding="utf-8", newline="") as f:
            created = True
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
