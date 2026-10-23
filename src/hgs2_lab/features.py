"""Doğrulanmış bir veri seti manifestinden deterministik özellik tablosu (ağ erişimi yok; model eğitimi yok).

Girdi: kampanya dizini + `dataset build` çıktısı. Çıktı dizini (yoksa oluşturulur, varsa BOŞ olmalı):
* `features.csv`         : anahtar + tanımlayıcılar + YALNIZCA gözlenen özellikler (istemci sonuç dosyalarından)
* `labels.csv`           : aynı anahtar ve satır sırası + deney tasarımı metadata'sı + etiket/hedef alanları
* `feature-manifest.json`: kaynaklar, bölme, politika, sütun rolleri, sayımlar, CSV özetleri

Etiketler ve tasarım metadata'sı özellik dosyasına hiç yazılmaz (ayrı dosya). `hold_ms_actual` yalnızca
`labels.csv`'de, gecikme regresyonu hedefi olarak bulunur. Sütun rolleri adlandırılmış bir politikayla
(`FEATURE_POLICIES`) tanımlanır; başka görevler için yeni politika eklenebilir.

Doğrulama sırası (hepsi geçmeden hiçbir dosya yazılmaz):
1. Veri seti manifestinin biçimi ve kendi `content_sha256` değeri.
2. Veri seti, kaydedilen parametrelerle (split_seed, oranlar, geçersiz deney politikası) yeniden üretilir: bu
   kampanya kataloğunu ve tüm dosyaları doğrular (campaign.verify_campaign) ve kaynak deney kimlikleri ile bölme
   kararları manifestteki içerikle BİREBİR aynı olmalıdır.
3. Her deneyin sonuç ve etiket dosyaları bir kez bayt olarak okunur; okunan baytların SHA-256 özeti veri
   setindeki başvuruyla aynı olmalı; sonuç kayıtları etiket kayıtlarıyla (seq = index) birebir eşleşmeli.

Determinizm: aynı girdi dosyaları ve aynı politika -> bayt bayt aynı CSV'ler ve aynı `content_sha256`.
Üretim zamanı yalnızca manifest zarfındadır (`generated_at`), CSV'lerde ve özet kapsamında değildir.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

from . import __version__
from .analysis import AnalysisOutputError, write_document, write_text_exclusive
from .campaign import safe_relative
from .dataset import DATASET_FORMAT, DATASET_SCHEMA_VERSION, SPLITS, DatasetError, build_dataset
from .models import DATASET_SYNTHETIC, RawResult
from .reader import load_run
from .storage import StorageError
from .synthetic import FAULT_FIXED_DELAY, FAULT_RANDOM_DELAY, canonical_json

FEATURE_TABLE_FORMAT = "hgs2-lab-feature-table"
FEATURE_SCHEMA_VERSION = 1
FEATURES_FILE = "features.csv"
LABELS_FILE = "labels.csv"
MANIFEST_FILE = "feature-manifest.json"

ROLE_KEY = "key"  # birleştirme anahtarı; özellik değil
ROLE_IDENTIFIER = "identifier_not_feature"  # kaynak/gruplama bilgisi; özellik değil
ROLE_OBSERVED = "observed_feature"  # istemcinin ölçtüğü değer
ROLE_DESIGN = "design_metadata"  # deney tasarımı; özellik değil (sızıntı)
ROLE_TARGET = "target"  # etiket/hedef; özellik değil
ROLE_LABEL_QUALITY = "label_quality"  # etiketin güvenilirliği; özellik değil
NOT_FEATURE_ROLES = frozenset({ROLE_KEY, ROLE_IDENTIFIER, ROLE_DESIGN, ROLE_TARGET, ROLE_LABEL_QUALITY})


class FeatureTableError(ValueError):
    """Özellik tablosu üretilemedi (doğrulama veya bütünlük hatası)."""


@dataclass(frozen=True)
class Column:
    name: str
    role: str
    type: str  # string | int | float | bool
    description: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "role": self.role, "type": self.type, "description": self.description}


_KEY = (
    Column("split", ROLE_KEY, "string", "Veri seti bölümü: train | validation | test"),
    Column("run_id", ROLE_KEY, "string", "Deney çalıştırması (sonuç dosyası run_id)"),
    Column("seq", ROLE_KEY, "int", "Çalıştırma içi sıra (RawResult.seq = etiket requests[].index)"),
)


@dataclass(frozen=True)
class FeaturePolicy:
    name: str
    description: str
    features: tuple[Column, ...]
    labels: tuple[Column, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "columns": {FEATURES_FILE: [c.to_dict() for c in self.features],
                            LABELS_FILE: [c.to_dict() for c in self.labels]}}


OBSERVED_V1 = FeaturePolicy(
    name="observed-v1",
    description="Yalnızca istemcinin gözlediği alanlar özelliktir. Tasarım metadata'sı ve etiketler ayrı labels.csv "
                "dosyasındadır. Satırlar: ölçüm istekleri (warmup=false).",
    features=_KEY + (
        Column("campaign_id", ROLE_IDENTIFIER, "string", "Kaynak kampanya"),
        Column("group_id", ROLE_IDENTIFIER, "string", "Bölme gruplama anahtarı (kampanya planı group)"),
        Column("plan_id", ROLE_IDENTIFIER, "string", "Temel plan"),
        Column("seed", ROLE_IDENTIFIER, "int", "Deneyin plan seed'i"),
        Column("iteration", ROLE_IDENTIFIER, "int", "Senaryo içi ölçüm sırası (RawResult.iteration)"),
        Column("offset_ms", ROLE_OBSERVED, "float", "İsteğin başlangıcı, çalıştırmanın monotonik başlangıcına göre (ms)"),
        Column("elapsed_ms", ROLE_OBSERVED, "float", "send çağrısından dönüşe kadar istemci süresi (ms)"),
        Column("duration_ms", ROLE_OBSERVED, "float", "İstemcinin ölçtüğü HTTP yanıt süresi (ms); yanıt yoksa boş"),
        Column("status_code", ROLE_OBSERVED, "int", "HTTP durum kodu; yanıt yoksa boş"),
        Column("success", ROLE_OBSERVED, "bool", "true yalnızca http_ok=true ise; HTTP hatası veya taşıma hatasında false"),
        Column("error_type", ROLE_OBSERVED, "string", "Taşıma hatası türü (timeout | connection_error | "
                                                     "transport_error); yoksa boş"),
        Column("response_bytes", ROLE_OBSERVED, "int", "Çözülmüş yanıt gövdesi baytı; yanıt yoksa boş"),
    ),
    labels=_KEY + (
        Column("scenario", ROLE_DESIGN, "string", "Senaryo adı (tasarımı yansıtır; özellik değil)"),
        Column("planned_fault", ROLE_TARGET, "string", "Sınıflandırma hedefi: bu isteğe planlanan hata türü"),
        Column("planned_status", ROLE_DESIGN, "int", "Sunucunun göndermesi planlanan durum; bağlantı kesme/zaman "
                                                    "aşımında boş"),
        Column("planned_delay_ms", ROLE_DESIGN, "float", "Planlanan bekleme talimatı (ölçüm değil)"),
        Column("expected_outcome", ROLE_DESIGN, "string", "Plandan türetilen beklenen sonuç kategorisi"),
        Column("hold_ms_actual", ROLE_TARGET, "float", "Gecikme regresyonu hedefi: sunucuda gerçekleşen bekleme (ms); "
                                                      "yalnızca planned_fault in {fixed_delay, random_delay} için hedef; "
                                                      "bekleme yoksa boş"),
        Column("label_status", ROLE_LABEL_QUALITY, "string", "confirmed | contradicted | ... (etiket güvenilirliği)"),
    ),
)
FEATURE_POLICIES = {OBSERVED_V1.name: OBSERVED_V1}

FORMAT_RULES = {
    "encoding": "UTF-8, BOM yok",
    "line_terminator": "\\n (LF)",
    "delimiter": ",",
    "quoting": "csv.QUOTE_MINIMAL (yalnızca gerektiğinde çift tırnak)",
    "header": "ilk satır; sütun sırası manifestteki 'columns' sırasıyla sabit",
    "null": "boş hücre",
    "bool": "true | false",
    "int": "ondalık tam sayı",
    "float": "Python repr(float): en kısa gidiş-dönüş gösterimi (kaynak JSON değeriyle aynı)",
    "row_order": "bölüm (train, validation, test) -> veri seti manifestindeki deney sırası -> seq artan",
    "row_filter": "yalnızca ölçüm istekleri (warmup=false); ısınma satırları sayılır ama yazılmaz",
}


def format_cell(value: Any, kind: str) -> str:
    if value is None:
        return ""
    if kind == "bool":
        if not isinstance(value, bool):
            raise FeatureTableError(f"bool beklenen değer: {value!r}")
        return "true" if value else "false"
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise FeatureTableError(f"int beklenen değer: {value!r}")
        return str(value)
    if kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FeatureTableError(f"float beklenen değer: {value!r}")
        return repr(float(value))
    return str(value)


def render_csv(columns: Sequence[Column], rows: Sequence[Mapping[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([c.name for c in columns])
    for row in rows:
        writer.writerow([format_cell(row[c.name], c.type) for c in columns])
    return buffer.getvalue()


def _fail(issues: list[str]) -> FeatureTableError:
    shown = "; ".join(issues[:20]) + (f"; ... (+{len(issues) - 20})" if len(issues) > 20 else "")
    return FeatureTableError(f"özellik tablosu üretilemedi ({len(issues)} sorun): {shown}")


def load_dataset_manifest(path: str | Path) -> dict[str, Any]:
    """Veri seti manifestini okur; biçimi ve kendi content_sha256 değerini doğrular."""
    path = Path(path)
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeatureTableError(f"[veri seti] dataset_manifest_unreadable: {path.name}: {exc}") from exc
    if not isinstance(document, dict) or document.get("format") != DATASET_FORMAT \
            or document.get("dataset_schema_version") != DATASET_SCHEMA_VERSION or not isinstance(document.get("dataset"), dict):
        raise FeatureTableError(f"[veri seti] dataset_manifest_format: {path.name} bir {DATASET_FORMAT} "
                                f"v{DATASET_SCHEMA_VERSION} belgesi değil")
    if hashlib.sha256(canonical_json(document["dataset"])).hexdigest() != document.get("content_sha256"):
        raise FeatureTableError(f"[veri seti] dataset_manifest_tampered: {path.name} içeriği content_sha256 ile "
                                "uyuşmuyor")
    return document


def _verify_reproducible(campaign_dir: Path, data: Mapping[str, Any]) -> None:
    params = data["parameters"]
    try:
        ratios = {s: Fraction(params["target_ratios_exact"][s]) for s in SPLITS}
        rebuilt = build_dataset(campaign_dir, split_seed=params["split_seed"], ratios=ratios,
                                invalid_policy=params["invalid_policy"])
    except DatasetError as exc:
        raise FeatureTableError(f"[kampanya] dataset_rebuild_failed: {exc}") from exc
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise FeatureTableError(f"[veri seti] dataset_parameters_invalid: {exc}") from exc
    if rebuilt == data:
        return
    issues = []
    if rebuilt["source"] != data["source"]:
        issues.append("[kampanya] catalog_changed: kaynak katalog/kampanya veri setinin üretildiği kaynakla aynı değil")
    old = {e["experiment_id"]: name for name, s in data["splits"].items() for e in s["experiments"]}
    new = {e["experiment_id"]: name for name, s in rebuilt["splits"].items() for e in s["experiments"]}
    for eid in sorted(set(old) | set(new)):
        if old.get(eid) != new.get(eid):
            issues.append(f"[{eid}] split_mismatch: manifestte {old.get(eid)}, yeniden üretimde {new.get(eid)}")
    if not issues:
        issues.append("[veri seti] dataset_not_reproducible: aynı parametrelerle yeniden üretilen içerik farklı")
    raise _fail(issues)


def _rows_for(root: Path, split: str, item: Mapping[str, Any], campaign_id: str,
              issues: list[str]) -> tuple[list[dict], list[dict], int]:
    eid, run_id = item["experiment_id"], item["run_id"]
    refs = item["features"]
    try:
        results_json = safe_relative(root, refs["results_json"]["path"])
        results_csv = safe_relative(root, refs["results_csv"]["path"])
        labels_path = safe_relative(root, item["labels"]["path"])
    except ValueError as exc:
        issues.append(f"[{eid}] path_unsafe: {exc}")
        return [], [], 0
    try:
        run = load_run(results_json.parent, run_id)
    except (StorageError, ValueError) as exc:
        issues.append(f"[{eid}] results_invalid: {exc}")
        return [], [], 0
    by_role = {f.role: f for f in run.files}
    for role, path, ref in (("json", results_json, refs["results_json"]), ("csv", results_csv, refs["results_csv"])):
        source = by_role[role]
        if source.name != path.name or source.sha256 != ref["sha256"]:
            issues.append(f"[{eid}] feature_source_mismatch: {path.name} okunan özeti veri setindekiyle aynı değil")
    try:
        raw = labels_path.read_bytes()
    except OSError as exc:
        issues.append(f"[{eid}] file_missing: {item['labels']['path']}: {type(exc).__name__}")
        return [], [], 0
    if hashlib.sha256(raw).hexdigest() != item["labels"]["sha256"]:
        issues.append(f"[{eid}] label_source_mismatch: {labels_path.name} özeti veri setindekiyle aynı değil")
        return [], [], 0
    requests = json.loads(raw.decode("utf-8"))["requests"]

    features, labels, warmup = [], [], 0
    for result in run.results:
        label = requests[result.seq - 1] if 0 < result.seq <= len(requests) else None
        if label is None or (label["index"], label["scenario"], label["warmup"], label["iteration"]) != \
                (result.seq, result.scenario, result.warmup, result.iteration):
            issues.append(f"[{eid}] label_join_mismatch: seq {result.seq} etiket kaydıyla eşleşmiyor")
            continue
        if result.warmup:
            warmup += 1
            continue
        features.append(_feature_row(split, run_id, result, campaign_id, item))
        labels.append(_label_row(split, run_id, result.seq, label))
    return features, labels, warmup


def _feature_row(split: str, run_id: str, r: RawResult, campaign_id: str, item: Mapping[str, Any]) -> dict[str, Any]:
    return {"split": split, "run_id": run_id, "seq": r.seq, "campaign_id": campaign_id, "group_id": item["group"],
            "plan_id": item["plan_id"], "seed": item["seed"], "iteration": r.iteration, "offset_ms": r.offset_ms,
            "elapsed_ms": r.elapsed_ms, "duration_ms": r.duration_ms, "status_code": r.status_code,
            "success": r.http_ok is True, "error_type": r.error_type, "response_bytes": r.response_bytes}


def _label_row(split: str, run_id: str, seq: int, label: Mapping[str, Any]) -> dict[str, Any]:
    server = label.get("server") or {}
    return {"split": split, "run_id": run_id, "seq": seq, "scenario": label["scenario"],
            "planned_fault": label["planned"]["fault"], "planned_status": label["planned"]["status"],
            "planned_delay_ms": label["planned"]["delay_ms"], "expected_outcome": label["expected"]["outcome"],
            "hold_ms_actual": server.get("hold_ms_actual"), "label_status": label["label_status"]}


def build_feature_table(campaign_dir: str | Path, dataset_path: str | Path,
                        policy: str = OBSERVED_V1.name) -> tuple[dict[str, Any], str, str]:
    """(deterministik manifest içeriği, features.csv metni, labels.csv metni). Doğrulama hatasında FeatureTableError."""
    if policy not in FEATURE_POLICIES:
        raise FeatureTableError(f"bilinmeyen özellik politikası: {policy!r} (desteklenen: {', '.join(FEATURE_POLICIES)})")
    feature_policy = FEATURE_POLICIES[policy]
    root = Path(campaign_dir)
    document = load_dataset_manifest(dataset_path)
    data = document["dataset"]
    _verify_reproducible(root, data)

    campaign_id = data["source"]["campaign_id"]
    issues: list[str] = []
    feature_rows: list[dict] = []
    label_rows: list[dict] = []
    experiments: list[dict] = []
    counts: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        split_counts = {"experiments": 0, "rows": 0, "warmup_excluded": 0}
        for item in data["splits"][split]["experiments"]:
            f_rows, l_rows, warmup = _rows_for(root, split, item, campaign_id, issues)
            f_rows.sort(key=lambda r: r["seq"])
            l_rows.sort(key=lambda r: r["seq"])
            feature_rows += f_rows
            label_rows += l_rows
            split_counts["experiments"] += 1
            split_counts["rows"] += len(f_rows)
            split_counts["warmup_excluded"] += warmup
            experiments.append({
                "experiment_id": item["experiment_id"], "run_id": item["run_id"], "split": split,
                "group_id": item["group"], "plan_id": item["plan_id"], "seed": item["seed"], "rows": len(f_rows),
                "warmup_excluded": warmup,
                "sources": {"results_csv": item["features"]["results_csv"], "results_json": item["features"]["results_json"],
                            "labels": item["labels"]},
            })
        counts[split] = split_counts
    if issues:
        raise _fail(issues)

    # Bütünlük: her çalıştırma tek bölümde; özellik dosyasında etiket/tasarım sütunu yok.
    split_of: dict[str, set[str]] = {}
    for row in feature_rows:
        split_of.setdefault(row["run_id"], set()).add(row["split"])
    shared = sorted(r for r, s in split_of.items() if len(s) > 1)
    feature_names = [c.name for c in feature_policy.features]
    leaked = sorted(set(feature_names) & {c.name for c in feature_policy.labels if c.role not in (ROLE_KEY,)})
    if shared or leaked:
        raise _fail([f"[bütünlük] run_in_multiple_splits: {shared}"] * bool(shared)
                    + [f"[bütünlük] label_column_in_features: {leaked}"] * bool(leaked))

    features_text = render_csv(feature_policy.features, feature_rows)
    labels_text = render_csv(feature_policy.labels, label_rows)
    file_info = {
        name: {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "size_bytes": len(text.encode("utf-8")),
               "rows": len(rows)}
        for name, text, rows in ((FEATURES_FILE, features_text, feature_rows), (LABELS_FILE, labels_text, label_rows))
    }
    empty = [e["experiment_id"] for e in experiments if e["rows"] == 0]
    params = data["parameters"]
    content = {
        "tool": {"name": "hgs2-lab", "version": __version__},
        "dataset_kind": DATASET_SYNTHETIC,
        "note": "Sentetik veriden özellik tablosu; gerçek HGS2 ölçümü değildir. Model eğitimi içermez.",
        "dataset": {"dataset_id": document["content_sha256"], "file_name": Path(dataset_path).name,
                    "campaign_id": campaign_id, "campaign_plan_sha256": data["source"]["campaign_plan_sha256"],
                    "catalog_sha256": data["source"]["catalog"]["sha256"]},
        "split": {k: params[k] for k in ("split_seed", "target_ratios_exact", "invalid_policy", "split_unit",
                                         "grouping_key", "assignment")},
        "policy": feature_policy.to_dict(),
        "not_for_features": sorted(c.name for c in feature_policy.features + feature_policy.labels
                                   if c.role in NOT_FEATURE_ROLES),
        "targets": {
            "classification": f"{LABELS_FILE}:planned_fault",
            "delay_regression": f"{LABELS_FILE}:hold_ms_actual (yalnızca planned_fault in "
                                f"{{{FAULT_FIXED_DELAY}, {FAULT_RANDOM_DELAY}}})",
        },
        "join_key": [c.name for c in _KEY],
        "format_rules": FORMAT_RULES,
        "experiments": experiments,
        "excluded_experiments": data["invalid_experiments"],
        "empty_experiments": empty,
        "counts": {**counts, "total": {k: sum(c[k] for c in counts.values()) for k in ("experiments", "rows",
                                                                                         "warmup_excluded")}},
        "files": file_info,
    }
    return content, features_text, labels_text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_feature_table(campaign_dir: str | Path, dataset_path: str | Path, output_dir: str | Path, *,
                        policy: str = OBSERVED_V1.name, now: Callable[[], str] = _utc_now_iso) -> dict[str, Any]:
    """Doğrular, üretir ve yazar. Çıktı dizini varsa boş olmalı; hiçbir dosyanın üzerine yazılmaz."""
    out = Path(output_dir)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise AnalysisOutputError(f"çıktı dizini boş değil, üzerine yazılmaz: {out}")
    content, features_text, labels_text = build_feature_table(campaign_dir, dataset_path, policy)  # önce doğrula
    out.mkdir(parents=True, exist_ok=True)
    write_text_exclusive(features_text, out / FEATURES_FILE)
    write_text_exclusive(labels_text, out / LABELS_FILE)
    document = {"format": FEATURE_TABLE_FORMAT, "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "generated_at": now(), "content_sha256": hashlib.sha256(canonical_json(content)).hexdigest(),
                "table": content}
    write_document(document, out / MANIFEST_FILE)  # en son: manifestin varlığı tamamlanmış çıktı demektir
    return document
