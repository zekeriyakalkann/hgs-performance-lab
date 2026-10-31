"""Kampanya kataloğundan train / validation / test veri seti manifesti (ağ erişimi yok; model eğitimi yok).

Kurallar (README "Veri seti bölme"):
* Önce katalog ve başvurduğu tüm dosyalar doğrulanır (campaign.verify_campaign); sorun varsa veri seti üretilmez.
* Bölme birimi = deney çalıştırması (run_id). Bir çalıştırmanın istekleri asla bölünmez.
* Gruplama anahtarı = kampanya planındaki `group` (varsayılan `plan_id`): aynı temel planın tüm seed tekrarları
  aynı bölüme gider. Gruplar `sha256("<split_seed>:<group>")` sırasıyla, hedef orana göre en büyük açığı olan
  bölüme atanır (eşitlikte train, validation, test sırası). Deterministiktir; seed ve tüm kararlar kaydedilir.
* Grup bütünlüğü nedeniyle hedef oranlar tutmazsa kayıtlar başka bölüme TAŞINMAZ; sapma uyarı olarak raporlanır.
* Geçersiz deney politikası: `exclude` (geçersiz/tamamlanmamış deneyler dışarıda kalır ve nedenleriyle listelenir)
  ya da `fail` (böyle bir deney varsa veri seti üretilmez).
* Özellik ve etiket kaynakları ayrıdır: özellikler yalnızca sonuç dosyalarından (RawResult gözlem alanları),
  etiketler yalnızca etiket dosyalarından. Veri seti manifesti kayıtları kopyalamaz; dosyalara SHA-256 ile başvurur.
* İki hedef ayrı tanımlanır: sınıflandırma (`planned.fault`) ve gecikme regresyonu (`server.hold_ms_actual`).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

from . import __version__
from .campaign import CATALOG_NAME, safe_relative, verify_campaign
from .models import DATASET_SYNTHETIC, STATUS_COMPLETED, RawResult
from .synthetic import (
    FAULT_FIXED_DELAY,
    FAULT_RANDOM_DELAY,
    GROUND_TRUTH_FIELDS,
    IDENTIFIER_FIELDS,
    MODEL_INPUT_CANDIDATE_FIELDS,
    canonical_json,
)

DATASET_FORMAT = "hgs2-lab-synthetic-dataset"
DATASET_SCHEMA_VERSION = 1
SPLITS = ("train", "validation", "test")
DEFAULT_RATIOS = {"train": Fraction(3, 5), "validation": Fraction(1, 5), "test": Fraction(1, 5)}
INVALID_POLICIES = ("exclude", "fail")
RATIO_TOLERANCE = Fraction(1, 10)
DELAY_FAULTS = frozenset({FAULT_FIXED_DELAY, FAULT_RANDOM_DELAY})
# Sonuç dosyalarında (özellik kaynağı) bulunmaması gereken etiket anahtarları.
LABEL_KEYS = frozenset({"planned", "expected", "agreement", "label_status", "hold_ms_actual", "hold_ms_planned",
                        "delay_ms", "min_duration_ms", "onset_after", "planned_fault", "status_sent"})


class DatasetError(ValueError):
    """Veri seti üretilemedi (doğrulama, politika veya bütünlük hatası)."""


def parse_ratios(text: str) -> dict[str, Fraction]:
    """'0.6,0.2,0.2' -> {train, validation, test}; toplam tam olarak 1, train > 0."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 3:
        raise DatasetError("oranlar 'train,validation,test' biçiminde üç sayı olmalı")
    try:
        values = [Fraction(p) for p in parts]
    except (ValueError, ZeroDivisionError) as exc:
        raise DatasetError(f"oranlar sayı olmalı: {text!r}") from exc
    if any(v < 0 for v in values) or values[0] <= 0 or sum(values) != 1:
        raise DatasetError(f"oranlar negatif olamaz, train > 0 olmalı ve toplam 1 olmalı: {text!r}")
    return dict(zip(SPLITS, values))


def group_order_key(split_seed: int, group: str) -> tuple[str, str]:
    return hashlib.sha256(f"{split_seed}:{group}".encode("utf-8")).hexdigest(), group


def assign_groups(weights: Mapping[str, int], ratios: Mapping[str, Fraction], split_seed: int) -> dict[str, str]:
    """Grupları bölümlere atar (grup bölünmez). Deterministik: sıra seed'li özetle, seçim en büyük açıkla."""
    total = sum(weights.values())
    assigned = {s: 0 for s in SPLITS}
    result: dict[str, str] = {}
    for group in sorted(weights, key=lambda g: group_order_key(split_seed, g)):
        deficits = {s: ratios[s] * total - assigned[s] for s in SPLITS}
        best = max(SPLITS, key=lambda s: (deficits[s], -SPLITS.index(s)))
        result[group] = best
        assigned[best] += weights[group]
    return result


def _json_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _json_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _json_keys(item)


def _label_counts(labels: Mapping[str, Any]) -> dict[str, Any]:
    measured = [r for r in labels["requests"] if not r["warmup"]]
    classes = Counter(r["planned"]["fault"] for r in measured)
    regression = sum(1 for r in measured if r["planned"]["fault"] in DELAY_FAULTS
                     and (r.get("server") or {}).get("hold_ms_actual") is not None)
    return {"measured_requests": len(measured), "classification": dict(sorted(classes.items())),
            "delay_regression_samples": regression}


def _ratio(part: int, whole: int) -> float | None:
    return float(Fraction(part, whole)) if whole else None


def build_dataset(
    campaign_dir: str | Path,
    *,
    split_seed: int = 0,
    ratios: Mapping[str, Fraction] | None = None,
    invalid_policy: str = "exclude",
) -> dict[str, Any]:
    """Deterministik veri seti içeriği (üretim zamanı içermez)."""
    if isinstance(split_seed, bool) or not isinstance(split_seed, int) or not 0 <= split_seed <= 2**63 - 1:
        raise DatasetError(f"split_seed negatif olmayan bir tam sayı olmalı (alınan: {split_seed!r})")
    if invalid_policy not in INVALID_POLICIES:
        raise DatasetError(f"invalid_policy {', '.join(INVALID_POLICIES)} olmalı (alınan: {invalid_policy!r})")
    ratios = dict(ratios or DEFAULT_RATIOS)
    root = Path(campaign_dir)

    verification = verify_campaign(root)
    if not verification["ok"]:
        details = "; ".join(f"[{i['experiment_id'] or 'katalog'}] {i['rule']}: {i['message']}"
                            for i in verification["issues"][:20])
        raise DatasetError(f"katalog doğrulaması başarısız ({len(verification['issues'])} sorun): {details}")
    catalog, labels_by_id = verification["catalog"], verification["labels"]

    eligible, excluded = [], []
    for entry in catalog["experiments"]:
        if entry["status"] == STATUS_COMPLETED and entry["valid"]:
            eligible.append(entry)
        else:
            excluded.append({"experiment_id": entry["experiment_id"], "group": entry["group"],
                             "status": entry["status"], "reasons": entry["invalid_reasons"]})
    if excluded and invalid_policy == "fail":
        ids = ", ".join(e["experiment_id"] for e in excluded)
        raise DatasetError(f"invalid_policy=fail: geçersiz veya tamamlanmamış deney(ler) var: {ids}")
    if not eligible:
        raise DatasetError("veri setine alınabilecek geçerli deney yok")

    weights = Counter(e["group"] for e in eligible)
    assignment = assign_groups(weights, ratios, split_seed)

    def files_of(entry: Mapping[str, Any], role: str) -> dict[str, str]:
        (record,) = [f for f in entry["files"] if f["role"] == role]
        return {"path": record["path"], "sha256": record["sha256"]}

    splits: dict[str, dict[str, Any]] = {s: {"groups": [], "experiments": []} for s in SPLITS}
    for group in sorted(assignment, key=lambda g: group_order_key(split_seed, g)):
        splits[assignment[group]]["groups"].append(group)
    for entry in eligible:  # katalog sırası (deterministik)
        counts = _label_counts(labels_by_id[entry["experiment_id"]])
        splits[assignment[entry["group"]]]["experiments"].append({
            "experiment_id": entry["experiment_id"], "run_id": entry["run_id"], "group": entry["group"],
            "plan_id": entry["plan_id"], "seed": entry["seed"], "plan_sha256": entry["plan_sha256"],
            "design_fingerprint": entry["design_fingerprint"],
            "features": {"results_json": files_of(entry, "results_json"), "results_csv": files_of(entry, "results_csv")},
            "labels": files_of(entry, "labels"),
            "counts": counts,
        })

    all_classes: set[str] = set()
    for split in splits.values():
        classes: Counter[str] = Counter()
        regression = measured = 0
        for item in split["experiments"]:
            classes.update(item["counts"]["classification"])
            regression += item["counts"]["delay_regression_samples"]
            measured += item["counts"]["measured_requests"]
        split["counts"] = {"experiments": len(split["experiments"]), "measured_requests": measured,
                           "classification": dict(sorted(classes.items())), "delay_regression_samples": regression}
        all_classes |= set(classes)

    warnings: list[dict[str, Any]] = []
    total_exp = len(eligible)
    total_req = sum(s["counts"]["measured_requests"] for s in splits.values())
    achieved = {
        "by_experiments": {s: _ratio(splits[s]["counts"]["experiments"], total_exp) for s in SPLITS},
        "by_measured_requests": {s: _ratio(splits[s]["counts"]["measured_requests"], total_req) for s in SPLITS},
    }
    for s in SPLITS:
        count = splits[s]["counts"]["experiments"]
        if count == 0 and ratios[s] > 0:
            warnings.append({"code": "empty_split", "split": s,
                             "message": f"{s} bölümü boş: {len(weights)} grup var; gruplar bölünmediği için bu bölüme "
                                        "grup kalmadı. Kayıtlar başka bölümden taşınmadı."})
        deviation = abs(Fraction(count, total_exp) - ratios[s])
        if deviation > RATIO_TOLERANCE:
            warnings.append({"code": "ratio_deviation", "split": s,
                             "message": f"{s}: hedef {float(ratios[s]):.2f}, gerçekleşen {count / total_exp:.2f} "
                                        f"(deney sayısına göre). Grup bütünlüğü korunduğu için kayıtlar yeniden "
                                        "dağıtılmadı; daha fazla grup (plan) tanımlayın."})
        missing = sorted(all_classes - set(splits[s]["counts"]["classification"]))
        if count and missing:
            warnings.append({"code": "missing_classes", "split": s, "classes": missing,
                             "message": f"{s} bölümünde şu sınıflar yok: {', '.join(missing)}. Bu sınıflar için "
                                        "bu bölümde değerlendirme yapılamaz."})
        if count and splits[s]["counts"]["delay_regression_samples"] == 0:
            warnings.append({"code": "missing_regression_samples", "split": s,
                             "message": f"{s} bölümünde gecikme regresyonu örneği yok."})

    checks = _integrity_checks(root, splits)
    errors = [c for c in checks if c["severity"] == "error" and not c["passed"]]
    if errors:
        raise DatasetError("bütünlük denetimi başarısız: " + "; ".join(f"{c['rule']}: {c['details']}" for c in errors))
    for check in checks:
        if not check["passed"]:
            warnings.append({"code": check["rule"], "message": check["details"]})

    return {
        "dataset_kind": DATASET_SYNTHETIC,
        "note": "Sentetik veri seti; gerçek HGS2 ölçümü değildir. Model eğitimi içermez; yalnızca bölme kararları ve "
                "dosya başvurularıdır. Dosya yolları kampanya dizinine göredir.",
        "tool": {"name": "hgs2-lab", "version": __version__},
        "source": {
            "campaign_id": catalog["campaign_id"], "campaign_plan_sha256": catalog["campaign_plan_sha256"],
            "catalog": {"path": CATALOG_NAME, "sha256": verification["catalog_sha256"]},
            "experiment_ids": [e["experiment_id"] for e in catalog["experiments"]],
        },
        "parameters": {
            "split_seed": split_seed, "target_ratios": {s: float(ratios[s]) for s in SPLITS},
            "target_ratios_exact": {s: str(ratios[s]) for s in SPLITS},
            "invalid_policy": invalid_policy,
            "split_unit": "deney çalıştırması (run_id); bir çalıştırmanın istekleri bölünmez",
            "grouping_key": "group (kampanya planı; varsayılan plan_id): aynı grubun tüm seed tekrarları aynı bölümde",
            "assignment": "gruplar sha256('<split_seed>:<group>') sırasıyla, hedef orana göre en büyük açığı olan "
                          "bölüme atanır; eşitlikte train > validation > test; ağırlık = gruptaki geçerli deney sayısı",
            "ratio_tolerance": float(RATIO_TOLERANCE),
        },
        "targets": {
            "classification": {"field": "planned.fault", "source": "labels", "unit": "ölçüm isteği (warmup=false)",
                               "classes": sorted(all_classes)},
            "delay_regression": {"field": "server.hold_ms_actual", "source": "labels",
                                 "applies_to": "planned.fault in {fixed_delay, random_delay}",
                                 "note": "planned.delay_ms ve istemci duration_ms hedef değildir."},
        },
        "feature_contract": {
            "feature_fields": list(MODEL_INPUT_CANDIDATE_FIELDS),
            "identifier_fields_not_features": list(IDENTIFIER_FIELDS),
            "feature_sources": "yalnızca sonuç dosyaları (features.results_csv/json)",
            "label_sources": "yalnızca etiket dosyaları (labels)",
            "join_key": "sonuç (run_id, seq) = etiket (run.run_id, requests[].index)",
            "excluded_sources": "sunucu olay dosyaları (uygulanan hatayı içerir) ve katalog/manifest alanları",
        },
        "invalid_experiments": {"policy": invalid_policy, "excluded": excluded},
        "splits": splits,
        "achieved_ratios": achieved,
        "integrity": {"passed": all(c["passed"] for c in checks), "checks": checks},
        "warnings": warnings,
    }


def _integrity_checks(root: Path, splits: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    def where(attr: str) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for name, split in splits.items():
            for item in split["experiments"]:
                found.setdefault(item[attr], set()).add(name)
        return found

    checks = []
    for attr, rule in (("run_id", "run_in_single_split"), ("experiment_id", "experiment_in_single_split"),
                       ("group", "group_in_single_split")):
        shared = sorted(k for k, v in where(attr).items() if len(v) > 1)
        checks.append({"rule": rule, "severity": "error", "passed": not shared,
                       "details": f"birden çok bölümde: {shared}" if shared else "her biri tek bölümde"})
    shared_designs = sorted(k[:12] for k, v in where("design_fingerprint").items() if len(v) > 1)
    checks.append({"rule": "design_in_single_split", "severity": "warning", "passed": not shared_designs,
                   "details": f"aynı tasarım (seed hariç) farklı gruplarda ve bölümlerde: {shared_designs}; plan "
                              "tanımları özdeşse aynı group altında toplayın" if shared_designs
                   else "özdeş tasarım bölümler arasında paylaşılmıyor"})

    leaked = []
    for split in splits.values():
        for item in split["experiments"]:
            path = safe_relative(root, item["features"]["results_json"]["path"])
            keys = set(_json_keys(json.loads(path.read_text(encoding="utf-8"))))
            csv_path = safe_relative(root, item["features"]["results_csv"]["path"])
            header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
            bad = sorted((keys | set(header)) & LABEL_KEYS)
            if bad:
                leaked.append(f"{item['experiment_id']}: {bad}")
    checks.append({"rule": "labels_absent_from_features", "severity": "error", "passed": not leaked,
                   "details": f"sonuç dosyalarında etiket anahtarı: {leaked}" if leaked
                   else "sonuç (özellik) dosyalarında etiket anahtarı yok"})

    # Etiket alanları ad alanlıdır (planned.*, expected.*, server.*): gözlem alanıyla aynı son ad (ör. error_type)
    # çakışma değildir; yalnızca tam ad karşılaştırılır.
    fields = set(MODEL_INPUT_CANDIDATE_FIELDS)
    contract_ok = fields <= set(RawResult.field_names()) and not fields & set(GROUND_TRUTH_FIELDS)
    checks.append({"rule": "feature_fields_are_observations", "severity": "error", "passed": contract_ok,
                   "details": "özellik alanları yalnızca RawResult gözlem alanları ve etiket alanlarıyla kesişmiyor"
                   if contract_ok else "özellik sözleşmesi etiket alanı içeriyor"})
    return checks


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_dataset_document(campaign_dir: str | Path, *, now: Callable[[], str] = _utc_now_iso,
                           **kwargs: Any) -> dict[str, Any]:
    """Çıktı belgesi: değişken `generated_at` + deterministik `dataset` içeriği ve onun özeti."""
    content = build_dataset(campaign_dir, **kwargs)
    return {"format": DATASET_FORMAT, "dataset_schema_version": DATASET_SCHEMA_VERSION, "generated_at": now(),
            "content_sha256": hashlib.sha256(canonical_json(content)).hexdigest(), "dataset": content}
