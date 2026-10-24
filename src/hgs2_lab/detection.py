"""Robust Z-score dedektörünün özellik tablosu üzerinde kalibrasyonu ve değerlendirmesi (F5; ağ erişimi yok).

Girdi: `dataset features` çıktı dizini (`features.csv`, `labels.csv`, `feature-manifest.json`). Dosyalar yalnızca
okunur; manifestin kendi özeti, CSV özetleri, politika ve sütunlar doğrulanır. Çıktı: tek bir JSON belgesi
(üzerine yazılmaz).

Görev (README "Değerlendirme protokolü"): **gecikme anomalisi**. Kapsam = doğrulanmış etiketli (`label_status =
confirmed`), `success = true` ve `planned_fault ∈ {none, fixed_delay, random_delay}` ölçüm satırları; pozitif sınıf
`planned_fault ∈ {fixed_delay, random_delay}`. HTTP/taşıma hataları (`success = false`) dedektöre verilmez ve metriklere
girmez; ayrıca sayılır.

Sızıntı sınırı:
* Dedektöre yalnızca `robust_z.INPUT_FIELDS` (= `duration_ms`) verilir (`detector_input`). Manifestteki sütun rolleri
  özellik seçimi için KULLANILMAZ (`observed-v1` `offset_ms`'i `observed_feature` olarak işaretler).
* Kalibrasyon yalnızca train bölümünün `planned_fault = none`, `label_status = confirmed`, `success = true`
  satırlarından yapılır. Validation ve test hiçbir parametreye girmez; eşik ve sabitler değerlendirmeden önce sabittir.
* `seq`, `offset_ms`, `run_id`, `scenario`, `plan_id` ve etiketler yalnızca satır seçimi, epizot sınırları ve
  değerlendirme için kullanılır.

Gecikme epizodu (README protokolü): aynı çalıştırmada aynı senaryonun `seq` sırasıyla ardışık, planda gecikme anomalisi
(`fixed_delay`/`random_delay`) taşıyan ölçüm istekleri; başlangıç = ilk böyle istek; senaryoda gecikme olmayan ilk
istekte veya senaryo sonunda biter. HTTP hatası, bağlantı kopması ve timeout planlı istekler epizoda girmez ve epizodu
bitirir. Epizot en çok bir kez, ilk skorlanmış alarmla tespit edilmiş sayılır.

Tespit gecikmesi yalnızca istek cinsinden (`request_detection_delay`) hesaplanır. Dedektör çevrimdışıdır ve alarm
üretim zamanı kaydedilmez; bu yüzden wall-clock tespit gecikmesi null'dır (`not_available`), uydurulmaz.
`start_to_alarm_request_offset_ms` yalnızca iki isteğin BAŞLANGIÇLARI arasındaki farktır; alarm gecikmesi değildir.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from . import robust_z
from .analysis import write_document
from .dataset import SPLITS
from .features import (
    FEATURE_POLICIES,
    FEATURE_SCHEMA_VERSION,
    FEATURE_TABLE_FORMAT,
    FEATURES_FILE,
    LABELS_FILE,
    MANIFEST_FILE,
)
from .synthetic import FAULT_FIXED_DELAY, FAULT_NONE, FAULT_RANDOM_DELAY, canonical_json

EVALUATION_FORMAT = "hgs2-lab-detector-evaluation"
EVALUATION_SCHEMA_VERSION = 2  # 2: delay_* alanları yeniden adlandırıldı; wall-clock gecikmesi null; operational_failures
LATENCY_FAULTS = (FAULT_FIXED_DELAY, FAULT_RANDOM_DELAY)
LABEL_CONFIRMED = "confirmed"
SPLIT_ROLES = {
    "train": "calibration_in_sample: baseline bu bölümün normal satırlarından hesaplandı; metrikler örneklem içidir",
    "validation": "validation: önceden sabitlenmiş parametrelerle değerlendirme; parametre seçimi yapılmadı",
    "test": "final_test: yalnızca nihai değerlendirme",
}

SCOPE_IN = "in_scope"
SCOPE_UNCONFIRMED = "excluded_unconfirmed_label"
SCOPE_UNSUCCESSFUL = "excluded_unsuccessful"  # HTTP veya taşıma hatası: gecikme görevinin dışında
SCOPE_OTHER_FAULT = "excluded_other_fault"
WALL_CLOCK_UNAVAILABLE = {
    "value": None, "status": "not_available",
    "reason": "Alarm üretim zamanı kaydedilmiyor (dedektör kayıtlı veriyi çevrimdışı skorlar). offset_ms istek "
              "başlangıcıdır, alarm zamanı değildir. Bu metrik için alarm anının epizot başlangıcıyla aynı monotonik "
              "zaman tabanında kaydedilmesi gerekir.",
}


class DetectionError(ValueError):
    """Özellik tablosu okunamadı veya doğrulanamadı."""


@dataclass(frozen=True)
class TableRow:
    split: str
    run_id: str
    seq: int
    features: Mapping[str, Any]  # features.csv satırı (anahtar + tanımlayıcı + gözlem)
    labels: Mapping[str, Any]  # labels.csv satırı (tasarım + hedef + etiket kalitesi)

    @property
    def key(self) -> tuple[str, str, int]:
        return self.split, self.run_id, self.seq


def detector_input(row: TableRow) -> dict[str, Any]:
    """Dedektörün gördüğü TEK girdi: açık izin listesi (duration_ms). Etiket ve konum alanları buraya giremez."""
    return {name: row.features[name] for name in robust_z.INPUT_FIELDS}


# --- özellik tablosunun okunması -------------------------------------------------------------------------------

def _fail(code: str, message: str) -> DetectionError:
    return DetectionError(f"[özellik tablosu] {code}: {message}")


def _parse_cell(text: str, kind: str, where: str) -> Any:
    if text == "":
        return None
    try:
        if kind == "bool":
            if text not in ("true", "false"):
                raise ValueError(text)
            return text == "true"
        if kind == "int":
            return int(text)
        if kind == "float":
            return float(text)  # 'nan'/'inf' okunur; dedektör bunları geçersiz sayar
    except ValueError as exc:
        raise _fail("cell_invalid", f"{where}: {kind} beklenen hücre {text!r}") from exc
    return text


def _read_csv(path: Path, columns: Sequence[Mapping[str, Any]], expected_sha256: str) -> list[dict[str, Any]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _fail("file_missing", f"{path.name}: {exc}") from exc
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise _fail("file_hash_mismatch", f"{path.name} manifestteki SHA-256 ile uyuşmuyor")
    reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=""))
    names = [c["name"] for c in columns]
    header = next(reader, None)
    if header != names:
        raise _fail("header_mismatch", f"{path.name} başlığı politikayla uyuşmuyor: {header}")
    rows = []
    for number, cells in enumerate(reader, start=2):
        if len(cells) != len(names):
            raise _fail("row_width", f"{path.name}:{number}: {len(cells)} hücre, beklenen {len(names)}")
        rows.append({c["name"]: _parse_cell(cell, c["type"], f"{path.name}:{number}:{c['name']}")
                     for c, cell in zip(columns, cells)})
    return rows


def load_feature_table(directory: str | Path) -> tuple[dict[str, Any], list[TableRow]]:
    """Manifesti ve iki CSV'yi okur, doğrular ve birleştirir (salt okunur)."""
    root = Path(directory)
    try:
        document = json.loads((root / MANIFEST_FILE).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail("manifest_unreadable", f"{MANIFEST_FILE}: {exc}") from exc
    if not isinstance(document, dict) or document.get("format") != FEATURE_TABLE_FORMAT \
            or document.get("feature_schema_version") != FEATURE_SCHEMA_VERSION \
            or not isinstance(document.get("table"), dict):
        raise _fail("manifest_format", f"{MANIFEST_FILE} bir {FEATURE_TABLE_FORMAT} v{FEATURE_SCHEMA_VERSION} belgesi "
                                       "değil")
    table = document["table"]
    if hashlib.sha256(canonical_json(table)).hexdigest() != document.get("content_sha256"):
        raise _fail("manifest_tampered", f"{MANIFEST_FILE} içeriği content_sha256 ile uyuşmuyor")
    policy = FEATURE_POLICIES.get(table.get("policy", {}).get("name"))
    if policy is None or table["policy"] != policy.to_dict():
        raise _fail("policy_unknown", "özellik politikası tanınmıyor veya tanımıyla uyuşmuyor")
    columns = table["policy"]["columns"]
    try:
        features = _read_csv(root / FEATURES_FILE, columns[FEATURES_FILE], table["files"][FEATURES_FILE]["sha256"])
        labels = _read_csv(root / LABELS_FILE, columns[LABELS_FILE], table["files"][LABELS_FILE]["sha256"])
    except (KeyError, TypeError) as exc:
        raise _fail("manifest_format", f"files/columns eksik: {exc}") from exc
    if len(features) != len(labels):
        raise _fail("row_count_mismatch", f"{FEATURES_FILE} {len(features)} satır, {LABELS_FILE} {len(labels)} satır")
    rows = []
    for number, (f, lab) in enumerate(zip(features, labels), start=2):
        key = (f["split"], f["run_id"], f["seq"])
        if key != (lab["split"], lab["run_id"], lab["seq"]):
            raise _fail("join_mismatch", f"satır {number}: {key} != {(lab['split'], lab['run_id'], lab['seq'])}")
        if f["split"] not in SPLITS:
            raise _fail("split_unknown", f"satır {number}: {f['split']!r}")
        rows.append(TableRow(f["split"], f["run_id"], f["seq"], f, lab))
    split_of: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        split_of[row.run_id].add(row.split)
    shared = sorted(r for r, s in split_of.items() if len(s) > 1)
    if shared:
        raise _fail("run_in_multiple_splits", ", ".join(shared))
    if len({r.key for r in rows}) != len(rows):
        raise _fail("duplicate_key", "aynı (split, run_id, seq) birden çok kez")
    return document, rows


# --- kalibrasyon ---------------------------------------------------------------------------------------------

CALIBRATION_RULE = ("split = train AND planned_fault = none AND label_status = confirmed AND success = true "
                    "(ısınma satırları özellik tablosunda yoktur)")


def is_calibration_row(row: TableRow) -> bool:
    return (row.split == "train" and row.labels["planned_fault"] == FAULT_NONE
            and row.labels["label_status"] == LABEL_CONFIRMED and row.features["success"] is True)


def calibrate_from_rows(rows: Sequence[TableRow]) -> tuple[robust_z.Baseline, dict[str, Any]]:
    """Yalnızca train normal satırlarından baseline; diğer bölümler hiç okunmaz."""
    train = [r for r in rows if r.split == "train"]
    selected = [r for r in train if is_calibration_row(r)]
    excluded = Counter()
    for r in train:
        if is_calibration_row(r):
            continue
        if r.labels["planned_fault"] != FAULT_NONE:
            excluded["not_normal"] += 1
        elif r.labels["label_status"] != LABEL_CONFIRMED:
            excluded["unconfirmed_label"] += 1
        else:
            excluded["unsuccessful"] += 1
    baseline = robust_z.calibrate([detector_input(r)["duration_ms"] for r in selected])
    info = {
        "splits_used": ["train"],
        "rule": CALIBRATION_RULE,
        "train_rows": len(train),
        "selected_rows": len(selected),
        "selected_runs": len({r.run_id for r in selected}),
        "excluded_train_rows": dict(sorted(excluded.items())),
        "baseline": baseline.to_dict(),
        "alarm_threshold_duration_ms": robust_z.threshold_duration_ms(baseline),
    }
    if baseline.status == robust_z.BASELINE_DEGENERATE:
        info["warning"] = ("MAD = 0: baseline ayırt edici değil; hiçbir istek skorlanmadı, metrikler null "
                           "(degenerate_baseline)")
    return baseline, info


# --- değerlendirme -------------------------------------------------------------------------------------------

def task_scope(row: TableRow) -> str:
    if row.labels["label_status"] != LABEL_CONFIRMED:
        return SCOPE_UNCONFIRMED
    if row.features["success"] is not True:
        return SCOPE_UNSUCCESSFUL
    if row.labels["planned_fault"] not in (FAULT_NONE,) + LATENCY_FAULTS:
        return SCOPE_OTHER_FAULT
    return SCOPE_IN


def _ratio(numerator: int, denominator: int, empty_status: str) -> dict[str, Any]:
    return {"value": numerator / denominator if denominator else None, "numerator": numerator,
            "denominator": denominator, "status": "ok" if denominator else empty_status}


def _summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


def _confusion(pairs: Iterable[tuple[bool, bool]]) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for truth, alarm in pairs:
        if truth:
            tp += alarm
            fn += not alarm
        else:
            fp += alarm
            tn += not alarm
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": _ratio(tp, tp + fp, "no_alarms"),
        "recall": _ratio(tp, tp + fn, "no_positive_rows"),
        "false_positive_rate": _ratio(fp, fp + tn, "no_normal_rows"),
    }


def episodes_of(rows: Sequence[TableRow]) -> list[list[TableRow]]:
    """Protokol tanımı: (run_id, scenario) içinde seq sırasıyla ardışık gecikme anomalisi satırları."""
    by_series: dict[tuple[str, str], list[TableRow]] = defaultdict(list)
    for row in rows:
        by_series[(row.run_id, row.labels["scenario"])].append(row)
    episodes = []
    for key in sorted(by_series):
        current: list[TableRow] = []
        for row in sorted(by_series[key], key=lambda r: r.seq):
            if row.labels["planned_fault"] in LATENCY_FAULTS:
                current.append(row)
            elif current:
                episodes.append(current)
                current = []
        if current:
            episodes.append(current)
    return episodes


def _episode_record(episode: Sequence[TableRow], predictions: Mapping[tuple, robust_z.Prediction]) -> dict[str, Any]:
    start = episode[0]
    scored = [r for r in episode if r.key in predictions and predictions[r.key].status == robust_z.STATUS_SCORED]
    alarms = [r for r in scored if predictions[r.key].alarm]
    first = alarms[0] if alarms else None
    families = sorted({r.labels["planned_fault"] for r in episode})
    offset_diff = None
    if first is not None and first.features["offset_ms"] is not None and start.features["offset_ms"] is not None:
        offset_diff = first.features["offset_ms"] - start.features["offset_ms"]
    return {
        "run_id": start.run_id, "plan_id": start.features["plan_id"], "scenario": start.labels["scenario"],
        "family": families[0] if len(families) == 1 else "mixed",
        "start_seq": start.seq, "end_seq": episode[-1].seq, "length": len(episode), "scored_rows": len(scored),
        "unsuccessful_rows": sum(r.features["success"] is not True for r in episode),  # epizotta ama skorlanmaz
        "evaluable": bool(scored),
        "detected": bool(alarms) if scored else None,
        "first_alarm_seq": first.seq if first else None,
        "request_detection_delay": first.seq - start.seq if first else None,
        "start_to_alarm_request_offset_ms": offset_diff,
        "wall_clock_detection_delay_ms": None,
    }


def _rate_block(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evaluable = [e for e in records if e["evaluable"]]
    detected = [e for e in evaluable if e["detected"]]
    return {
        "episodes": len(records),
        "evaluable": len(evaluable),
        "detected": len(detected),
        "detection_rate": _ratio(len(detected), len(evaluable), "no_evaluable_episodes"),
        "request_detection_delay": _summary([e["request_detection_delay"] for e in detected]),
        "start_to_alarm_request_offset_ms": _summary([e["start_to_alarm_request_offset_ms"] for e in detected
                                                      if e["start_to_alarm_request_offset_ms"] is not None]),
        "wall_clock_detection_delay_ms": WALL_CLOCK_UNAVAILABLE,
    }


def evaluate_split(split: str, rows: Sequence[TableRow],
                   predictions: Mapping[tuple, robust_z.Prediction]) -> dict[str, Any]:
    split_rows = [r for r in rows if r.split == split]
    scopes = {r.key: task_scope(r) for r in split_rows}
    in_scope = [r for r in split_rows if scopes[r.key] == SCOPE_IN]
    scored = [r for r in in_scope if predictions[r.key].status == robust_z.STATUS_SCORED]
    scored_keys = {r.key for r in scored}

    def truth(r: TableRow) -> bool:
        return r.labels["planned_fault"] in LATENCY_FAULTS

    unscored = Counter(f"{predictions[r.key].status}:{predictions[r.key].reason}" for r in in_scope
                       if predictions[r.key].status != robust_z.STATUS_SCORED)
    excluded = defaultdict(Counter)
    for r in split_rows:
        if scopes[r.key] != SCOPE_IN:
            excluded[scopes[r.key]][r.labels["planned_fault"]] += 1
    failed = [r for r in split_rows if r.features["success"] is not True]
    observed = Counter(r.features["error_type"] or (f"http_{r.features['status_code']}"
                                                    if r.features["status_code"] is not None else "unknown")
                       for r in failed)

    by_family = {}
    for family in LATENCY_FAULTS:
        fam_rows = [r for r in scored if r.labels["planned_fault"] == family]
        tp = sum(predictions[r.key].alarm for r in fam_rows)
        by_family[family] = {"represented": any(r.labels["planned_fault"] == family for r in in_scope),
                             "scored_rows": len(fam_rows), "detected_rows": tp,
                             "recall": _ratio(tp, len(fam_rows), "not_represented")}
    normal_rows = [r for r in scored if not truth(r)]
    fp = sum(predictions[r.key].alarm for r in normal_rows)
    by_family[FAULT_NONE] = {"represented": bool(normal_rows), "scored_rows": len(normal_rows), "false_alarms": fp,
                             "false_positive_rate": _ratio(fp, len(normal_rows), "no_normal_rows")}

    episode_records = [_episode_record(e, predictions) for e in episodes_of(split_rows)]
    episodes = _rate_block(episode_records)
    episodes["by_family"] = {f: _rate_block([e for e in episode_records if e["family"] == f]) for f in LATENCY_FAULTS}
    episodes["records"] = episode_records

    runs: dict[str, list[TableRow]] = defaultdict(list)
    for r in split_rows:
        runs[r.run_id].append(r)
    normal_runs = []
    for run_id in sorted(runs):
        if all(r.labels["planned_fault"] == FAULT_NONE for r in runs[run_id]):
            run_scored = [r for r in runs[run_id] if r.key in scored_keys]
            normal_runs.append({"run_id": run_id, "plan_id": runs[run_id][0].features["plan_id"],
                                "scored_rows": len(run_scored),
                                "false_alarms": sum(predictions[r.key].alarm for r in run_scored)})

    plans = sorted({r.features["plan_id"] for r in split_rows})
    by_plan = {}
    for plan in plans:
        plan_scored = [r for r in scored if r.features["plan_id"] == plan]
        plan_conf = _confusion((truth(r), bool(predictions[r.key].alarm)) for r in plan_scored)
        plan_eps = [e for e in episode_records if e["plan_id"] == plan]
        by_plan[plan] = {"runs": len({r.run_id for r in split_rows if r.features["plan_id"] == plan}),
                         "scored_rows": len(plan_scored), **plan_conf,
                         "episodes": len(plan_eps), "episodes_detected": sum(bool(e["detected"]) for e in plan_eps)}

    represented = [f for f in LATENCY_FAULTS if by_family[f]["represented"]]
    return {
        "role": SPLIT_ROLES[split],
        "rows": len(split_rows),
        "runs": len(runs),
        "in_scope_rows": len(in_scope),
        "scored_rows": len(scored),
        "unscored_in_scope": dict(sorted(unscored.items())),
        "excluded": {scope: dict(sorted(c.items())) for scope, c in sorted(excluded.items())},
        "operational_failures": {
            "rows": len(failed),
            "by_planned_fault": dict(sorted(Counter(r.labels["planned_fault"] for r in failed).items())),
            "by_observed_outcome": dict(sorted(observed.items())),
            "latency_planned_rows_failed": sum(r.labels["planned_fault"] in LATENCY_FAULTS for r in failed),
            "note": "success = false istekler (HTTP hatası, bağlantı hatası, timeout): dedektöre verilmez, normal "
                    "sınıfa eklenmez ve hiçbir gecikme metriğinin (recall paydası dahil) parçası değildir. Gecikme "
                    "planlı ama başarısız istekler epizot sınırlarında yer alır, skorlanmaz.",
        },
        "request_level": _confusion((truth(r), bool(predictions[r.key].alarm)) for r in scored),
        "normal_false_alarms": {
            "false_alarms": fp, "normal_scored_rows": len(normal_rows),
            "rate": _ratio(fp, len(normal_rows), "no_normal_rows"),
            "normal_only_runs": {"runs": len(normal_runs),
                                 "runs_with_false_alarm": sum(r["false_alarms"] > 0 for r in normal_runs),
                                 "false_alarms_per_run": _summary([r["false_alarms"] for r in normal_runs]),
                                 "records": normal_runs},
        },
        "episodes": episodes,
        "by_family": by_family,
        "by_plan": by_plan,
        "coverage": {"latency_families_represented": represented,
                     "latency_families_not_represented": [f for f in LATENCY_FAULTS if f not in represented],
                     "note": "Temsil edilmeyen aileler için sonuç 'değerlendirilemedi'dir; sıfır başarı değildir."},
    }


METRIC_DEFINITIONS = {
    "scope": "Gecikme görevi satırları: label_status = confirmed, success = true, planned_fault ∈ {none, fixed_delay, "
             "random_delay}. Pozitif = planned_fault ∈ {fixed_delay, random_delay}. Yalnızca status = scored satırlar "
             "(geçerli duration_ms) karışıklık matrisine girer; invalid_input ve degenerate_baseline ayrıca sayılır.",
    "recall_denominator": "TP + FN = skorlanan (success = true, geçerli duration_ms) gecikme planlı satırlar. Başarısız "
                          "gecikme planlı satırlar paydada değildir; operational_failures.latency_planned_rows_failed "
                          "altında sayılır.",
    "operational_failures": "success = false satırların ayrı sayımı (planlanan hataya ve gözlenen sonuca göre); gecikme "
                            "metriklerine girmez.",
    "precision": "TP / (TP + FP); alarm yoksa null (status no_alarms)",
    "recall": "TP / (TP + FN); pozitif satır yoksa null (status no_positive_rows)",
    "false_positive_rate": "FP / (FP + TN) = normal satırlarda alarm / skorlanan normal satır; normal satır yoksa null",
    "normal_false_alarms": "Skorlanan normal satırlardaki alarm sayısı ve oranı; ayrıca tüm satırları planned_fault = none "
                           "olan çalıştırmalarda çalıştırma başına yanlış alarm",
    "episode": "Gecikme epizodu: aynı çalıştırmada aynı senaryonun seq sırasıyla ardışık, planda fixed_delay/"
               "random_delay taşıyan ölçüm istekleri (plana göre; başarısızlar dahil ama skorlanmaz); başlangıç = ilk "
               "böyle istek; senaryoda gecikme olmayan ilk istekte (normal, HTTP hatası, kopma veya timeout) ya da "
               "senaryo sonunda biter. Diğer hata türleri epizoda girmez.",
    "episode_detection_rate": "Tespit edilen / değerlendirilebilir epizot. Değerlendirilebilir = en az bir skorlanan "
                              "satırı olan epizot; hiç skorlanan satırı olmayan epizot gecikme dedektörüyle "
                              "değerlendirilemez ve paydada değildir (episodes - evaluable). Tespit = epizot içindeki "
                              "skorlanan satırlardan en az birinde alarm; epizot en çok bir kez sayılır, ilk alarm "
                              "esastır. Tespit edilmeyen değerlendirilebilir epizotlar paydadadır. Epizot dışındaki "
                              "alarmlar yanlış alarmdır (normal satır FP'si). Epizot yoksa null",
    "request_detection_delay": "İlk alarmı üreten isteğin seq'i − epizot başlangıç isteğinin seq'i (istek sayısı; "
                               "yalnızca tespit edilen epizotlar). 0 = alarm epizodun ilk isteğine ait; 0 ms demek "
                               "değildir",
    "start_to_alarm_request_offset_ms": "Alarmı üreten isteğin offset_ms'i − epizot başlangıç isteğinin offset_ms'i: iki "
                                        "isteğin BAŞLANGIÇLARI arası süre. Alarm gecikmesi değildir (alarmı üreten "
                                        "isteğin kendi süresini ve skorlama zamanını içermez)",
    "wall_clock_detection_delay_ms": "Epizot başlangıcından alarmın gerçekten üretildiği ana kadar geçen süre. Alarm "
                                     "zamanı kaydedilmediği için hesaplanmaz: null, status not_available",
    "summaries": "n, min, median, max; değer yoksa null",
}


def _limitations(splits: Mapping[str, Mapping[str, Any]]) -> list[str]:
    items = [
        "Sentetik veri: aynı süreçteki yerel sentetik sunucu; gerçek HGS2 ölçümü değildir ve HGS2 hakkında başarı "
        "iddiası desteklemez.",
        "Tek bir sabit eşik (z > 3,5) ve tek baseline; eşik veya başka parametre validation/test sonuçlarına göre "
        "ayarlanmadı. Train metrikleri örneklem içidir.",
        "Belirsizlik (grup düzeyinde bootstrap) ve seed'ler arası değişkenlik bu çıktıda hesaplanmaz.",
        "HTTP ve taşıma hataları bu dedektörün görevi değildir; excluded altında sayılır, metriklere girmez.",
    ]
    for split in SPLITS:
        missing = splits[split]["coverage"]["latency_families_not_represented"]
        if missing:
            items.append(f"{split}: temsil edilmeyen gecikme aileleri {missing}; bu aileler için {split} sonucu "
                         "değerlendirilemedi.")
    test_plans = sorted(p for p, v in splits["test"]["by_plan"].items() if v["episodes"])
    items.append(f"test bölümündeki gecikme anomalisi planları: {test_plans or 'yok'}; test sonuçları yalnızca bu "
                 "plan(lar)ın tasarımı için geçerlidir.")
    return items


def build_evaluation(features_dir: str | Path) -> dict[str, Any]:
    """Deterministik değerlendirme içeriği (üretim zamanı içermez)."""
    document, rows = load_feature_table(features_dir)
    table = document["table"]
    baseline, calibration = calibrate_from_rows(rows)  # validation/test okunmadan önce ve onlardan bağımsız

    predictions: dict[tuple, robust_z.Prediction] = {}
    for row in rows:
        if task_scope(row) == SCOPE_IN:
            predictions[row.key] = robust_z.score(baseline, detector_input(row)["duration_ms"])
    splits = {split: evaluate_split(split, rows, predictions) for split in SPLITS}
    return {
        "tool": {"name": "hgs2-lab", "version": __version__},
        "dataset_kind": table.get("dataset_kind"),
        "note": "Gecikme anomalisi dedektörünün sentetik veri üzerinde değerlendirmesi; gerçek HGS2 ölçümü değildir.",
        "detector": robust_z.describe(),
        "source": {
            "features_dir": Path(features_dir).name,
            "feature_manifest": {"file": MANIFEST_FILE, "content_sha256": document["content_sha256"],
                                 "policy": table["policy"]["name"]},
            "files": {name: table["files"][name]["sha256"] for name in (FEATURES_FILE, LABELS_FILE)},
            "dataset": table["dataset"],
            "split": table["split"],
            "input_policy": "Dedektör girdisi açık izin listesiyle (input_fields) seçilir; manifestteki sütun rolleri "
                            "kullanılmaz.",
        },
        "task": {
            "name": "latency_anomaly",
            "positive_classes": list(LATENCY_FAULTS),
            "negative_class": FAULT_NONE,
            "excluded": "HTTP/taşıma hataları (success = false), doğrulanmamış etiketler ve diğer hata türleri",
        },
        "calibration": calibration,
        "metric_definitions": METRIC_DEFINITIONS,
        "splits": splits,
        "limitations": _limitations(splits),
        "predictions": [
            {"split": r.split, "run_id": r.run_id, "seq": r.seq, "status": p.status, "x": p.x, "z": p.z,
             "alarm": p.alarm, "reason": p.reason}
            for r in rows if (p := predictions.get(r.key)) is not None
        ],
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_evaluation(features_dir: str | Path, output: str | Path, *,
                     now: Callable[[], str] = _utc_now_iso) -> dict[str, Any]:
    """Değerlendirir ve yazar; çıktı varsa AnalysisExistsError (üzerine yazılmaz)."""
    content = build_evaluation(features_dir)
    document = {"format": EVALUATION_FORMAT, "evaluation_schema_version": EVALUATION_SCHEMA_VERSION,
                "generated_at": now(), "content_sha256": hashlib.sha256(canonical_json(content)).hexdigest(),
                "evaluation": content}
    write_document(document, output)
    return document
