"""Sentetik deneyler: manifest doğrulaması, deterministik deney planı ve etiketler (ağ erişimi yok).

Sentetik deney, uygulamanın KENDİ yerel test sunucusuna (synthetic_server.py) karşı, önceden planlanmış
hatalarla yapılan bir çalıştırmadır. Gerçek HGS2 ölçümü değildir; sonuç metadata'sında
`dataset_kind = "synthetic"` ile işaretlenir.

Üç ayrı veri kaynağı vardır ve karıştırılmaz:
* İstemci gözlemleri: normal sonuç dosyaları (şema v2, `RawResult`); planlanan hata BU DOSYALARDA YOKTUR.
* Sunucu olayları: sunucunun aldığı istekler ve uyguladığı hatalar (ayrı dosya).
* Etiketler: plan (beklenen davranış), istemcinin gözlediği sonuç ve ikisinin uyumu (ayrı dosya).

Plan determinizmi: aynı manifest (ve dolayısıyla aynı seed) her zaman aynı planı ve aynı `plan_sha256`
değerini üretir. Bu, gerçek yanıt sürelerinin veya işletim sistemi zamanlamasının aynı olacağı anlamına
GELMEZ; yalnızca sunucuya verilen talimatlar (hangi istekte hangi hata, ne kadar gecikme) aynıdır.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from ._validate import read_json_file
from .config import ConfigError, RunLimits
from .models import DATASET_SYNTHETIC, STATUS_COMPLETED, RawResult
from .scenarios import Scenario

MANIFEST_VERSION = 1
PLAN_ALGORITHM_VERSION = 1
LABELS_FORMAT = "hgs2-lab-synthetic-labels"
LABELS_SCHEMA_VERSION = 1
ROUTE_PREFIX = "/synthetic/"
EXPERIMENT_TYPES = frozenset({"fault_injection"})
SYNTHETIC_METHODS = frozenset({"GET", "POST"})

FAULT_NONE = "none"
FAULT_FIXED_DELAY = "fixed_delay"
FAULT_RANDOM_DELAY = "random_delay"
FAULT_HTTP_ERROR = "http_error"
FAULT_CONNECTION_DROP = "connection_drop"
FAULT_TIMEOUT = "timeout"
_FAULT_PARAMS: dict[str, frozenset[str]] = {
    FAULT_NONE: frozenset(),
    FAULT_FIXED_DELAY: frozenset({"delay_ms"}),
    FAULT_RANDOM_DELAY: frozenset({"min_delay_ms", "max_delay_ms"}),
    FAULT_HTTP_ERROR: frozenset({"status"}),
    FAULT_CONNECTION_DROP: frozenset(),
    FAULT_TIMEOUT: frozenset(),
}
FAULT_TYPES = frozenset(_FAULT_PARAMS)

OUTCOME_SUCCESS = "success"
OUTCOME_HTTP_ERROR = "http_error"
OUTCOME_TRANSPORT_ERROR = "transport_error"

# Sınırlar (aşırı parametreleri reddetmek için)
MAX_SCENARIOS = 20
MAX_REPETITIONS = 1_000
MAX_WARMUP = 100
MAX_TOTAL_REQUESTS = 5_000
MAX_DELAY_MS = 5_000.0
DELAY_TIMEOUT_RATIO = 0.5  # gecikme <= istemci zaman aşımının yarısı: "başarılı ama yavaş" beklentisi belirsiz kalmaz
MIN_TIMEOUT_SECONDS = 0.1
MAX_TIMEOUT_SECONDS = 10.0
MAX_GAP_SECONDS = 10.0
TIMEOUT_HOLD_FACTOR = 1.5  # timeout hatasında sunucu yanıtı en az bu kat kadar bekletir...
TIMEOUT_HOLD_MIN_MARGIN_MS = 250.0  # ...ve zaman aşımından en az bu kadar uzun
LATENCY_TOLERANCE_MS = 1.0  # gözlenen süre >= enjekte edilen gecikme - tolerans
HOLD_TOLERANCE_MS = 0.001  # sunucu beklemesi >= planlanan - tolerans (yalnızca ns -> ms yuvarlaması)
_MAX_SEED = 2**63 - 1
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

# Etiket sızıntısını önlemek için RawResult alanlarının rolleri (tümü sınıflandırılmalıdır; bkz. testler).
MODEL_INPUT_CANDIDATE_FIELDS = (
    "warmup", "offset_ms", "elapsed_ms", "duration_ms", "status_code", "http_ok", "error_type", "response_bytes",
)
IDENTIFIER_FIELDS = ("run_id", "seq", "scenario", "iteration", "method", "url", "started_at")
EXCLUDED_FIELDS = ("business_outcome", "error")  # boş alan ve serbest metin hata mesajı
GROUND_TRUTH_FIELDS = (
    "planned.fault", "planned.status", "planned.delay_ms", "expected.outcome", "expected.status",
    "expected.error_type", "expected.min_duration_ms", "server.planned_fault", "server.status_sent",
    "server.hold_ms_actual", "server.outcome", "agreement.match", "agreement.reasons", "label_status",
)

# Etiket dosyasındaki süre alanlarının kesin anlamı (dosyaya da yazılır; README "Gecikme alanları").
# Dört ayrı kavram tek alanda birleştirilmez: planlanan, sunucuda gerçekleşen, sunucu toplam, istemci toplam.
LABEL_TIMING_FIELDS = {
    "planned.delay_ms": "Planlanan bekleme talimatı (manifest + seed'den). Ölçüm değildir.",
    "expected.min_duration_ms": "Başarılı gecikmeli yanıtta istemci süresi için beklenen alt sınır = planned.delay_ms.",
    "server.hold_ms_actual": "Sunucunun gerçekten beklediği süre (sunucu olayı; yalnızca bekleme döngüsü, istek okuma "
                             "ve yanıt yazma hariç). Gerçekleşen enjeksiyonun büyüklüğü için bu alan esas alınır. "
                             "Gerçek etiket bilgisidir; model girdisi değildir.",
    "observed.duration_ms": "İstemcinin ölçtüğü toplam yanıt süresi (sonuç dosyasındaki RawResult.duration_ms): "
                            "istek gönderiminden yanıt gövdesinin tamamı okunana kadar; sunucu beklemesini içerir.",
    "sunucu toplam işleme": "Etiket dosyasında yoktur; sunucu olay dosyasında completed_ns - received_ns olarak "
                            "hesaplanabilir ve aynı süreçte güvenilir değildir.",
}


class ManifestError(ValueError):
    """Geçersiz sentetik deney manifesti."""


def _fail(message: str) -> ManifestError:
    return ManifestError(message)


def _int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise _fail(f"{name} {low}..{high} aralığında bir tam sayı olmalı (alınan: {value!r})")
    return value


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _fail(f"{name} sonlu bir sayı olmalı (alınan: {value!r})")
    if not low <= value <= high:
        raise _fail(f"{name} {low:g}..{high:g} aralığında olmalı (alınan: {value!r})")
    return float(value)


def _keys(data: Any, allowed: frozenset[str] | set[str], required: set[str], what: str) -> dict:
    if not isinstance(data, dict):
        raise _fail(f"{what} bir nesne olmalı (alınan: {type(data).__name__})")
    unknown = sorted(str(k) for k in data if k not in allowed)
    if unknown:
        raise _fail(f"{what}: bilinmeyen alan(lar): {', '.join(unknown)}")
    missing = sorted(required - set(data))
    if missing:
        raise _fail(f"{what}: eksik alan(lar): {', '.join(missing)}")
    return data


# --- manifest ---
@dataclass(frozen=True)
class FaultSpec:
    type: str
    onset_after: int = 0  # senaryonun ilk N isteği (ısınma dahil) normal; hata sonrakilere uygulanır
    delay_ms: float | None = None
    min_delay_ms: float | None = None
    max_delay_ms: float | None = None
    status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type}
        for name in sorted(_FAULT_PARAMS[self.type]):
            data[name] = getattr(self, name)
        if self.type != FAULT_NONE:
            data["onset_after"] = self.onset_after
        return data


@dataclass(frozen=True)
class SyntheticScenario:
    name: str
    method: str
    warmup_repetitions: int
    repetitions: int
    delay_seconds: float
    fault: FaultSpec

    @property
    def path(self) -> str:
        return ROUTE_PREFIX + self.name

    @property
    def total_requests(self) -> int:
        return self.warmup_repetitions + self.repetitions

    def to_engine_scenario(self) -> Scenario:
        """Motorun senaryosu. Beklenen durum varsayılan (2xx) kalır: planlanan hata motora bildirilmez."""
        return Scenario(name=self.name, method=self.method, path=self.path, repetitions=self.repetitions,
                        delay_seconds=self.delay_seconds, warmup_repetitions=self.warmup_repetitions)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "method": self.method, "warmup_repetitions": self.warmup_repetitions,
                "repetitions": self.repetitions, "delay_seconds": self.delay_seconds, "fault": self.fault.to_dict()}


@dataclass(frozen=True)
class SyntheticManifest:
    experiment_id: str
    seed: int
    timeout_seconds: float
    scenarios: tuple[SyntheticScenario, ...]
    limits: RunLimits = field(default_factory=RunLimits)
    description: str | None = None
    manifest_version: int = MANIFEST_VERSION
    experiment_type: str = "fault_injection"
    dataset_kind: str = DATASET_SYNTHETIC

    @property
    def timeout_ms(self) -> float:
        return self.timeout_seconds * 1000

    def to_dict(self) -> dict[str, Any]:
        """Normalleştirilmiş görünüm (varsayılanlar dahil); etiket dosyasına kopyalanır."""
        return {
            "manifest_version": self.manifest_version, "experiment_id": self.experiment_id,
            "experiment_type": self.experiment_type, "dataset_kind": self.dataset_kind,
            "description": self.description, "seed": self.seed, "timeout_seconds": self.timeout_seconds,
            "limits": self.limits.to_dict(), "scenarios": [s.to_dict() for s in self.scenarios],
        }


def _parse_fault(data: Any, where: str, total: int, timeout_ms: float) -> FaultSpec:
    if not isinstance(data, dict) or "type" not in data:
        raise _fail(f"{where}.fault bir nesne olmalı ve 'type' içermeli")
    kind = data["type"]
    if kind not in FAULT_TYPES:
        raise _fail(f"{where}.fault.type bilinmiyor: {kind!r} (desteklenen: {', '.join(sorted(FAULT_TYPES))})")
    params = _FAULT_PARAMS[kind]
    allowed = {"type"} | params | ({"onset_after"} if kind != FAULT_NONE else set())
    _keys(data, allowed, {"type"} | set(params), f"{where}.fault ({kind})")

    onset = _int(data.get("onset_after", 0), f"{where}.fault.onset_after", 0, total - 1)
    max_delay = min(MAX_DELAY_MS, timeout_ms * DELAY_TIMEOUT_RATIO)
    spec: dict[str, Any] = {"type": kind, "onset_after": onset}
    if kind == FAULT_FIXED_DELAY:
        spec["delay_ms"] = _number(data["delay_ms"], f"{where}.fault.delay_ms", 0, max_delay)
    elif kind == FAULT_RANDOM_DELAY:
        low = _number(data["min_delay_ms"], f"{where}.fault.min_delay_ms", 0, max_delay)
        high = _number(data["max_delay_ms"], f"{where}.fault.max_delay_ms", 0, max_delay)
        if low > high:
            raise _fail(f"{where}.fault.min_delay_ms ({low:g}) max_delay_ms'ten ({high:g}) büyük olamaz")
        spec.update(min_delay_ms=low, max_delay_ms=high)
    elif kind == FAULT_HTTP_ERROR:
        spec["status"] = _int(data["status"], f"{where}.fault.status", 400, 599)
    return FaultSpec(**spec)


def parse_manifest(data: Any) -> SyntheticManifest:
    top_allowed = {"manifest_version", "experiment_id", "experiment_type", "dataset_kind", "description", "seed",
                   "timeout_seconds", "limits", "scenarios"}
    top_required = {"manifest_version", "experiment_id", "experiment_type", "dataset_kind", "seed",
                    "timeout_seconds", "scenarios"}
    _keys(data, top_allowed, top_required, "Manifest")
    if data["manifest_version"] != MANIFEST_VERSION or isinstance(data["manifest_version"], bool):
        raise _fail(f"manifest_version {MANIFEST_VERSION} olmalı (alınan: {data['manifest_version']!r})")
    if data["dataset_kind"] != DATASET_SYNTHETIC:
        raise _fail(f"dataset_kind '{DATASET_SYNTHETIC}' olmalı (alınan: {data['dataset_kind']!r}); bu manifest "
                    "yalnızca sentetik deneyleri tanımlar")
    if data["experiment_type"] not in EXPERIMENT_TYPES:
        raise _fail(f"experiment_type desteklenmiyor: {data['experiment_type']!r}")
    experiment_id = data["experiment_id"]
    if not isinstance(experiment_id, str) or not _ID_RE.match(experiment_id) or experiment_id.endswith("."):
        raise _fail("experiment_id harf/rakamla başlamalı; yalnızca harf, rakam, '.', '_', '-' içermeli (en çok 64)")
    description = data.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 500):
        raise _fail("description en çok 500 karakterlik bir metin olmalı")
    seed = _int(data["seed"], "seed", 0, _MAX_SEED)
    timeout_seconds = _number(data["timeout_seconds"], "timeout_seconds", MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS)

    limits_raw = data.get("limits", {})
    _keys(limits_raw, set(RunLimits.__dataclass_fields__), set(), "limits")
    try:
        limits = RunLimits(**limits_raw)
    except ConfigError as exc:
        raise _fail(str(exc)) from exc

    raw_scenarios = data["scenarios"]
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise _fail("scenarios boş olmayan bir liste olmalı")
    if len(raw_scenarios) > MAX_SCENARIOS:
        raise _fail(f"en çok {MAX_SCENARIOS} senaryo olabilir")
    scenarios = []
    for i, raw in enumerate(raw_scenarios, start=1):
        where = f"scenarios[{i}]"
        _keys(raw, {"name", "method", "warmup_repetitions", "repetitions", "delay_seconds", "fault"},
              {"name", "repetitions", "fault"}, where)
        name = raw["name"]
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise _fail(f"{where}.name küçük harf/rakamla başlamalı; yalnızca a-z, 0-9, '_', '-' (en çok 48)")
        method = raw.get("method", "GET")
        if method not in SYNTHETIC_METHODS:
            raise _fail(f"{where}.method GET veya POST olmalı (alınan: {method!r})")
        warmup = _int(raw.get("warmup_repetitions", 0), f"{where}.warmup_repetitions", 0, MAX_WARMUP)
        repetitions = _int(raw["repetitions"], f"{where}.repetitions", 1, MAX_REPETITIONS)
        gap = _number(raw.get("delay_seconds", 0.0), f"{where}.delay_seconds", 0, MAX_GAP_SECONDS)
        fault = _parse_fault(raw["fault"], where, warmup + repetitions, timeout_seconds * 1000)
        scenarios.append(SyntheticScenario(name, method, warmup, repetitions, gap, fault))

    names = [s.name for s in scenarios]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise _fail(f"senaryo adları benzersiz olmalı (tekrar eden: {', '.join(duplicates)})")
    total = sum(s.total_requests for s in scenarios)
    if total > MAX_TOTAL_REQUESTS:
        raise _fail(f"toplam istek sayısı en çok {MAX_TOTAL_REQUESTS} olabilir (planlanan: {total})")
    if total > limits.max_requests:
        raise _fail(f"planlanan {total} istek limits.max_requests ({limits.max_requests}) değerini aşıyor")
    return SyntheticManifest(experiment_id=experiment_id, seed=seed, timeout_seconds=timeout_seconds,
                             scenarios=tuple(scenarios), limits=limits, description=description)


def load_manifest(path: str | Path) -> tuple[SyntheticManifest, str]:
    """Manifesti dosyadan okur; (manifest, dosyanın orijinal baytlarının SHA-256 özeti) döndürür."""
    path = Path(path)
    data = read_json_file(path, ManifestError, "Manifest dosyası")
    manifest = parse_manifest(data)
    return manifest, hashlib.sha256(path.read_bytes()).hexdigest()


# --- plan ---
@dataclass(frozen=True)
class PlannedRequest:
    index: int  # çalıştırma genelinde 1'den başlayan sıra = beklenen RawResult.seq
    scenario: str
    route_index: int  # senaryo içinde 1'den başlayan sıra (sunucunun bu rotaya gelen k. isteği)
    warmup: bool
    iteration: int  # RawResult.iteration ile aynı anlam
    method: str
    fault: str  # bu isteğe uygulanacak hata (onset öncesi "none")
    status: int | None  # sunucunun göndereceği durum kodu; bağlantı kesme/zaman aşımında None
    delay_ms: float  # sunucunun yanıttan önce beklettiği süre
    expected_outcome: str
    expected_status: int | None
    expected_error_type: str | None
    min_duration_ms: float | None  # başarılı yanıtta gözlenen süre en az bu kadar olmalı

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "scenario": self.scenario, "route_index": self.route_index, "warmup": self.warmup,
            "iteration": self.iteration, "method": self.method,
            "planned": {"fault": self.fault, "status": self.status, "delay_ms": self.delay_ms},
            "expected": {"outcome": self.expected_outcome, "status": self.expected_status,
                         "error_type": self.expected_error_type, "min_duration_ms": self.min_duration_ms},
        }


@dataclass(frozen=True)
class SyntheticPlan:
    experiment_id: str
    seed: int
    timeout_seconds: float
    entries: tuple[PlannedRequest, ...]

    def route(self, scenario: str) -> tuple[PlannedRequest, ...]:
        return tuple(e for e in self.entries if e.scenario == scenario)

    def to_dict(self) -> dict[str, Any]:
        return {"plan_algorithm_version": PLAN_ALGORITHM_VERSION, "experiment_id": self.experiment_id,
                "seed": self.seed, "timeout_seconds": self.timeout_seconds,
                "entries": [e.to_dict() for e in self.entries]}

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def scenario_seed(seed: int, scenario: str) -> int:
    """Senaryo başına kararlı tohum: senaryo eklemek/sıralamak diğer senaryoların planını değiştirmez."""
    return int.from_bytes(hashlib.sha256(f"{seed}:{scenario}".encode("utf-8")).digest()[:8], "big")


def timeout_hold_ms(timeout_seconds: float) -> float:
    timeout_ms = timeout_seconds * 1000
    return max(timeout_ms * TIMEOUT_HOLD_FACTOR, timeout_ms + TIMEOUT_HOLD_MIN_MARGIN_MS)


def build_plan(manifest: SyntheticManifest) -> SyntheticPlan:
    """Manifestten deterministik plan. Rastgelelik yalnızca random.Random(senaryo tohumu).random() ile."""
    entries: list[PlannedRequest] = []
    for scenario in manifest.scenarios:
        rng = random.Random(scenario_seed(manifest.seed, scenario.name))
        f = scenario.fault
        for route_index in range(1, scenario.total_requests + 1):
            warmup = route_index <= scenario.warmup_repetitions
            iteration = route_index if warmup else route_index - scenario.warmup_repetitions
            fault = f.type if route_index > f.onset_after else FAULT_NONE
            status: int | None = 200
            delay = 0.0
            expected = (OUTCOME_SUCCESS, 200, None)
            if fault == FAULT_FIXED_DELAY:
                delay = f.delay_ms
            elif fault == FAULT_RANDOM_DELAY:
                u = rng.random()  # her istek için bir çekiliş; onset öncesinde çekilmez
                delay = round(f.min_delay_ms + (f.max_delay_ms - f.min_delay_ms) * u, 3)
            elif fault == FAULT_HTTP_ERROR:
                status = f.status
                expected = (OUTCOME_HTTP_ERROR, f.status, None)
            elif fault == FAULT_CONNECTION_DROP:
                status = None
                expected = (OUTCOME_TRANSPORT_ERROR, None, "connection_error")
            elif fault == FAULT_TIMEOUT:
                status, delay = None, timeout_hold_ms(manifest.timeout_seconds)
                expected = (OUTCOME_TRANSPORT_ERROR, None, "timeout")
            outcome, expected_status, error_type = expected
            entries.append(PlannedRequest(
                index=len(entries) + 1, scenario=scenario.name, route_index=route_index, warmup=warmup,
                iteration=iteration, method=scenario.method, fault=fault, status=status, delay_ms=delay,
                expected_outcome=outcome, expected_status=expected_status, expected_error_type=error_type,
                min_duration_ms=delay if outcome == OUTCOME_SUCCESS and delay > 0 else None,
            ))
    return SyntheticPlan(manifest.experiment_id, manifest.seed, manifest.timeout_seconds, tuple(entries))


def estimated_min_duration_seconds(manifest: SyntheticManifest, plan: SyntheticPlan) -> float:
    """İstemci açısından en kısa süre: enjekte gecikmeler + zaman aşımı beklemeleri + senaryo aralıkları."""
    waits_ms = sum(manifest.timeout_ms if e.fault == FAULT_TIMEOUT else e.delay_ms for e in plan.entries)
    gaps = sum(s.delay_seconds * (s.total_requests - 1) for s in manifest.scenarios)
    return waits_ms / 1000 + gaps


def check_plan_limits(manifest: SyntheticManifest, plan: SyntheticPlan) -> None:
    estimate = estimated_min_duration_seconds(manifest, plan)
    if estimate >= manifest.limits.max_duration_seconds:
        raise _fail(f"plan en az {estimate:.1f} sn sürer; limits.max_duration_seconds "
                    f"({manifest.limits.max_duration_seconds:g}) yetersiz")


def guard_forecast(plan: SyntheticPlan, limits: RunLimits) -> str | None:
    """Beklenen sonuçlar gerçekleşirse güvenlik koruması (SafetyGuard) çalıştırmayı durdurur mu? Tahmindir."""
    total = failed = consecutive = 0
    for entry in plan.entries:
        total += 1
        transport = entry.expected_outcome == OUTCOME_TRANSPORT_ERROR
        failed += entry.expected_outcome != OUTCOME_SUCCESS
        consecutive = consecutive + 1 if transport else 0
        if consecutive >= limits.max_consecutive_transport_errors:
            return (f"{entry.index}. istekte art arda {consecutive} beklenen taşıma hatası "
                    "limits.max_consecutive_transport_errors sınırını tetikler")
        if total >= limits.error_rate_min_requests and failed / total > limits.max_error_rate:
            return (f"{entry.index}. istekte beklenen hata oranı {failed / total:.2f} limits.max_error_rate "
                    f"({limits.max_error_rate:g}) sınırını aşar")
    return None


# --- etiketler ---
def observed_outcome(result: RawResult) -> dict[str, Any]:
    if result.error_type is not None:
        category = OUTCOME_TRANSPORT_ERROR
    elif result.http_ok:
        category = OUTCOME_SUCCESS
    else:
        category = OUTCOME_HTTP_ERROR
    return {"outcome": category, "status": result.status_code, "error_type": result.error_type,
            "duration_ms": result.duration_ms}


def compare(entry: PlannedRequest, observed: Mapping[str, Any]) -> list[str]:
    """Beklenen ile gözlenen arasındaki uyumsuzluk nedenleri (boş liste = uyumlu)."""
    reasons = []
    if observed["outcome"] != entry.expected_outcome:
        detail = observed["status"] if observed["status"] is not None else observed["error_type"]
        reasons.append(f"beklenen {entry.expected_outcome}, gözlenen {observed['outcome']} ({detail})")
        return reasons
    if entry.expected_status is not None and observed["status"] != entry.expected_status:
        reasons.append(f"beklenen durum {entry.expected_status}, gözlenen {observed['status']}")
    if entry.expected_error_type is not None and observed["error_type"] != entry.expected_error_type:
        reasons.append(f"beklenen taşıma hatası {entry.expected_error_type}, gözlenen {observed['error_type']}")
    if entry.min_duration_ms is not None and observed["duration_ms"] is not None \
            and observed["duration_ms"] < entry.min_duration_ms - LATENCY_TOLERANCE_MS:
        reasons.append(f"gözlenen süre {observed['duration_ms']:.3f} ms, enjekte edilen gecikmeden "
                       f"({entry.min_duration_ms:g} ms) kısa")
    return reasons


def _server_checks(plan: SyntheticPlan, executed: int, server: Mapping[str, Any]) -> tuple[list, dict]:
    """Sunucu olaylarını planla karşılaştırır: (gerekçeler, istek indeksine göre sunucu olayı)."""
    reasons: list[dict[str, str]] = []
    by_route = {(e.get("route"), e.get("route_index")): e for e in server.get("events", []) if e.get("kind") == "planned"}
    matched: dict[int, dict] = {}
    missing = mismatched = 0
    for entry in plan.entries[:executed]:
        event = by_route.get((entry.scenario, entry.route_index))
        if event is None:
            missing += 1
            continue
        matched[entry.index] = event
        if event.get("planned_fault") != entry.fault:
            mismatched += 1
    executed_keys = {(e.scenario, e.route_index) for e in plan.entries[:executed]}
    extra = len(set(by_route) - executed_keys)
    unexpected = server.get("unexpected_requests", 0)
    # Gecikme hatasında sunucu en az planlanan süre beklemiş olmalı (yanıt verildiyse; kapanışta kesilen hariç).
    short_holds = 0
    for index, event in matched.items():
        entry = plan.entries[index - 1]
        if entry.fault in (FAULT_FIXED_DELAY, FAULT_RANDOM_DELAY) and event.get("outcome") != "stopped":
            actual = event.get("hold_ms_actual")
            short_holds += actual is None or actual < entry.delay_ms - HOLD_TOLERANCE_MS
    for count, code, message in (
        (missing, "server_missing_arrival", "istemcinin gönderdiği {n} istek sunucu kayıtlarında yok"),
        (mismatched, "server_fault_mismatch", "{n} istekte sunucunun uyguladığı hata planla uyuşmuyor"),
        (short_holds, "server_hold_short", "{n} gecikme isteğinde sunucunun gerçek beklemesi planlanandan kısa ya da yok"),
        (extra, "server_extra_arrivals", "sunucu, istemcinin kaydetmediği {n} planlı istek aldı"),
        (unexpected, "unexpected_server_requests", "sunucu {n} beklenmeyen istek aldı (bilinmeyen rota, plan dışı vb.)"),
        (server.get("dropped_events", 0), "server_events_truncated", "{n} sunucu olayı kayıt sınırı nedeniyle tutulmadı"),
        (len(server.get("errors", [])), "server_errors", "sunucuda {n} beklenmeyen hata"),
    ):
        if count:
            reasons.append({"code": code, "message": message.format(n=count)})
    return reasons, matched


def build_labels(
    manifest: SyntheticManifest,
    manifest_sha256: str,
    plan: SyntheticPlan,
    *,
    run_id: str,
    partial: bool,
    execution_status: str | None,
    results: Sequence[RawResult],
    result_files: Sequence[Mapping[str, Any]],
    server: Mapping[str, Any],
    server_events_file: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Etiket içeriği: plan (beklenen), gözlenen ve uyum; deney geçerliliği ve gerekçeleri."""
    verdict: list[dict[str, str]] = []
    if execution_status != STATUS_COMPLETED or partial:
        verdict.append({"code": "run_incomplete",
                        "message": f"çalıştırma tamamlanmadı (durum: {execution_status}); "
                                   f"{len(results)}/{len(plan.entries)} istek yürütüldü"})

    join_errors = []
    for entry, result in zip(plan.entries, results):
        if (result.seq, result.scenario, result.warmup, result.iteration) != \
                (entry.index, entry.scenario, entry.warmup, entry.iteration):
            join_errors.append(entry.index)
    if len(results) > len(plan.entries):
        join_errors.append(len(plan.entries) + 1)
    if join_errors:
        verdict.append({"code": "result_plan_mismatch",
                        "message": f"sonuç kayıtları planla eşleşmiyor (ilk: {join_errors[0]}. istek)"})

    server_reasons, server_matched = _server_checks(plan, min(len(results), len(plan.entries)), server)
    verdict.extend(server_reasons)

    requests = []
    counts: Counter[str] = Counter()
    for i, entry in enumerate(plan.entries):
        record = entry.to_dict()
        if i < len(results) and entry.index not in join_errors:
            observed = observed_outcome(results[i])
            reasons = compare(entry, observed)
            status = "confirmed" if not reasons else "contradicted"
            record.update(observed=observed, agreement={"match": not reasons, "reasons": reasons})
        else:
            status = "not_executed" if i >= len(results) else "unjoinable"
            record.update(observed=None, agreement={"match": None, "reasons": []})
        event = server_matched.get(entry.index)
        record["server"] = None if event is None else {
            "planned_fault": event.get("planned_fault"), "status_sent": event.get("status_sent"),
            "hold_ms_actual": event.get("hold_ms_actual"), "outcome": event.get("outcome"),
        }
        record["label_status"] = status
        counts[status] += 1
        requests.append(record)

    if counts["contradicted"]:
        verdict.append({"code": "expectation_mismatch",
                        "message": f"{counts['contradicted']} istekte gözlenen sonuç beklenenle uyuşmuyor"})

    by_fault: dict[str, dict[str, int]] = {}
    for record in requests:
        bucket = by_fault.setdefault(record["planned"]["fault"], Counter())
        bucket[record["label_status"]] += 1
    return {
        "dataset_kind": DATASET_SYNTHETIC,
        "note": "Sentetik deney etiketleri; gerçek HGS2 ölçümü değildir. Beklenen davranış plandan türetilir, "
                "gözlenen davranış istemci sonuç dosyalarından okunur; biri diğerinin yerine kullanılmaz.",
        "run": {"run_id": run_id, "partial": partial, "execution_status": execution_status,
                "result_files": list(result_files), "server_events_file": server_events_file},
        "experiment": {
            "experiment_id": manifest.experiment_id, "experiment_type": manifest.experiment_type,
            "seed": manifest.seed, "manifest_sha256": manifest_sha256, "manifest": manifest.to_dict(),
            "plan_algorithm_version": PLAN_ALGORITHM_VERSION, "plan_sha256": plan.sha256,
            "generator_version": __version__,
        },
        "field_roles": {
            "model_input_candidates": list(MODEL_INPUT_CANDIDATE_FIELDS),
            "identifiers_not_features": list(IDENTIFIER_FIELDS),
            "excluded": list(EXCLUDED_FIELDS),
            "ground_truth_only": list(GROUND_TRUTH_FIELDS),
            "note": "Model girdileri yalnızca sonuç dosyalarındaki gözlem alanlarından seçilmeli. Senaryo adı, URL ve "
                    "sunucu olayları deney tasarımını/uygulanan hatayı yansıtır; model girdisi olarak kullanılması "
                    "etiket sızıntısıdır.",
        },
        "timing_fields": LABEL_TIMING_FIELDS,
        "summary": {
            "planned": len(plan.entries), "executed": min(len(results), len(plan.entries)),
            "confirmed": counts["confirmed"], "contradicted": counts["contradicted"],
            "not_executed": counts["not_executed"], "unjoinable": counts["unjoinable"],
            "by_planned_fault": {k: dict(sorted(v.items())) for k, v in sorted(by_fault.items())},
        },
        "verdict": {"valid": not verdict, "reasons": verdict},
        "requests": requests,
    }
