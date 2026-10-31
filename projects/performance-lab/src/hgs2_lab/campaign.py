"""Sentetik deney kampanyası: toplu deney planı, deterministik açılım ve katalog doğrulaması (ağ erişimi yok).

Kampanya manifesti birden çok **temel plan** (`plans[]`, her biri bir senaryo listesi) ve bir **seed listesi**
tanımlar. Her (plan, seed) çifti tek bir sentetik deneye açılır: mevcut sentetik manifest biçiminde bir manifest
üretilir ve `synthetic.parse_manifest` ile doğrulanır. Deney kimliği deterministiktir:
`<campaign_id>.<plan_id>.s<seed>` (aynı zamanda run_id). Açılım sırası: planlar manifest sırasında, her planın
içinde seed'ler manifest sırasında.

Aynı kampanya manifesti her zaman aynı deney listesini, aynı deney manifestlerini ve aynı `campaign_plan_sha256`
değerini üretir. Bu yalnızca PLANI kapsar; gerçek yanıt süreleri her çalıştırmada farklıdır. Seed, sentetik
planda yalnızca rastgele gecikme çekilişlerini etkiler (bkz. synthetic.build_plan).

Katalog (`campaign.json`) kampanya çalıştırmasının makine tarafından okunabilir dizinidir (campaign_runner.py
yazar). Bu modüldeki `verify_campaign` kataloğu ve başvurduğu her dosyayı doğrular; dosya yolları yalnızca
kampanya dizini içindeki göreli yollar olabilir (mutlak yol, `..`, dizin dışına çıkan yol reddedilir).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ._validate import read_json_file
from .config import ConfigError, RunLimits
from .models import DATASET_SYNTHETIC
from .reader import load_run
from .storage import StorageError
from .synthetic import (
    LABELS_FORMAT,
    ManifestError,
    SyntheticManifest,
    SyntheticPlan,
    build_plan,
    canonical_json,
    check_plan_limits,
    parse_manifest,
)

CAMPAIGN_VERSION = 1
CATALOG_FORMAT = "hgs2-lab-synthetic-campaign"
CATALOG_SCHEMA_VERSION = 1
CATALOG_NAME = "campaign.json"
MANIFESTS_DIR = "manifests"
RUNS_DIR = "runs"

MAX_PLANS = 50
MAX_SEEDS = 50
MAX_SEED_VALUE = 999_999  # deney kimliği 64 karakter sınırını aşmasın
MAX_EXPERIMENTS = 200
MAX_CAMPAIGN_REQUESTS = 50_000
_CAMPAIGN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$")  # nokta yok: kimlik bileşenleri ayrışabilsin
_PLAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")

# Katalog girdisi durumları
STATUS_NOT_RUN = "not_run"  # kampanya kesildiği için çalıştırılmadı
STATUS_REJECTED = "rejected"  # ön kontrolde reddedildi; istek gönderilmedi
STATUS_ERROR = "error"  # beklenmeyen istisna; kısmi dosyalar olabilir
# Diğer durumlar execution.status ile aynıdır: completed, aborted, interrupted, failed

FILE_ROLES = ("manifest", "results_json", "results_csv", "labels", "server_events")


class CampaignError(ValueError):
    """Geçersiz kampanya manifesti."""


def _fail(message: str) -> CampaignError:
    return CampaignError(message)


@dataclass(frozen=True)
class CampaignExperiment:
    experiment_id: str
    plan_id: str
    group: str  # bölme gruplama anahtarı (varsayılan plan_id)
    seed: int
    manifest_data: dict[str, Any]  # sentetik manifest (JSON'a yazılacak biçim)
    manifest: SyntheticManifest
    plan: SyntheticPlan

    @property
    def design_fingerprint(self) -> str:
        """Seed ve kimlikten bağımsız tasarım özeti: senaryolar + zaman aşımı + sınırlar.

        Farklı gruplarda aynı parmak izi = aynı tasarım; bölümler arasında sızıntı riski olarak raporlanır.
        """
        design = {k: self.manifest_data[k] for k in ("timeout_seconds", "limits", "scenarios")}
        return hashlib.sha256(canonical_json(design)).hexdigest()

    def summary(self) -> dict[str, Any]:
        return {"experiment_id": self.experiment_id, "plan_id": self.plan_id, "group": self.group,
                "seed": self.seed, "plan_sha256": self.plan.sha256, "design_fingerprint": self.design_fingerprint}


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    description: str | None
    seeds: tuple[int, ...]
    experiments: tuple[CampaignExperiment, ...]

    @property
    def plan_sha256(self) -> str:
        """Kampanyanın deterministik plan özeti: açılan tüm deney manifestleri ve sentetik planları."""
        body = {"campaign_version": CAMPAIGN_VERSION, "campaign_id": self.campaign_id,
                "experiments": [{**e.summary(), "manifest": e.manifest_data} for e in self.experiments]}
        return hashlib.sha256(canonical_json(body)).hexdigest()


def _keys(data: Any, allowed: set[str], required: set[str], what: str) -> dict:
    if not isinstance(data, dict):
        raise _fail(f"{what} bir nesne olmalı (alınan: {type(data).__name__})")
    unknown = sorted(str(k) for k in data if k not in allowed)
    if unknown:
        raise _fail(f"{what}: bilinmeyen alan(lar): {', '.join(unknown)}")
    missing = sorted(required - set(data))
    if missing:
        raise _fail(f"{what}: eksik alan(lar): {', '.join(missing)}")
    return data


def parse_campaign(data: Any) -> Campaign:
    _keys(data, {"campaign_version", "campaign_id", "dataset_kind", "description", "seeds", "timeout_seconds",
                 "limits", "plans"},
          {"campaign_version", "campaign_id", "dataset_kind", "seeds", "timeout_seconds", "plans"}, "Kampanya")
    if data["campaign_version"] != CAMPAIGN_VERSION or isinstance(data["campaign_version"], bool):
        raise _fail(f"campaign_version {CAMPAIGN_VERSION} olmalı (alınan: {data['campaign_version']!r})")
    if data["dataset_kind"] != DATASET_SYNTHETIC:
        raise _fail(f"dataset_kind '{DATASET_SYNTHETIC}' olmalı; kampanyalar yalnızca sentetik deneyler üretir")
    campaign_id = data["campaign_id"]
    if not isinstance(campaign_id, str) or not _CAMPAIGN_ID_RE.match(campaign_id):
        raise _fail("campaign_id harf/rakamla başlamalı; yalnızca harf, rakam, '_', '-' (en çok 24, nokta yok)")
    description = data.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 500):
        raise _fail("description en çok 500 karakterlik bir metin olmalı")

    seeds = data["seeds"]
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= MAX_SEEDS:
        raise _fail(f"seeds 1..{MAX_SEEDS} öğeli bir liste olmalı")
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= MAX_SEED_VALUE:
            raise _fail(f"her seed 0..{MAX_SEED_VALUE} aralığında bir tam sayı olmalı (alınan: {seed!r})")
    if len(set(seeds)) != len(seeds):
        raise _fail("seeds tekrarlanamaz")

    limits = data.get("limits", {})
    _keys(limits, set(RunLimits.__dataclass_fields__), set(), "limits")
    try:
        RunLimits(**limits)
    except ConfigError as exc:
        raise _fail(str(exc)) from exc

    plans = data["plans"]
    if not isinstance(plans, list) or not 1 <= len(plans) <= MAX_PLANS:
        raise _fail(f"plans 1..{MAX_PLANS} öğeli bir liste olmalı")
    if len(plans) * len(seeds) > MAX_EXPERIMENTS:
        raise _fail(f"en çok {MAX_EXPERIMENTS} deney açılabilir (planlar x seed'ler = {len(plans) * len(seeds)})")

    experiments: list[CampaignExperiment] = []
    plan_ids: list[str] = []
    for i, raw in enumerate(plans, start=1):
        _keys(raw, {"plan_id", "group", "description", "scenarios"}, {"plan_id", "scenarios"}, f"plans[{i}]")
        plan_id = raw["plan_id"]
        if not isinstance(plan_id, str) or not _PLAN_ID_RE.match(plan_id):
            raise _fail(f"plans[{i}].plan_id küçük harf/rakamla başlamalı; yalnızca a-z, 0-9, '-' (en çok 24)")
        group = raw.get("group", plan_id)
        if not isinstance(group, str) or not _PLAN_ID_RE.match(group):
            raise _fail(f"plans[{i}].group plan_id ile aynı kurala uymalı")
        plan_description = raw.get("description")
        if plan_description is not None and (not isinstance(plan_description, str) or len(plan_description) > 300):
            raise _fail(f"plans[{i}].description en çok 300 karakterlik bir metin olmalı")
        plan_ids.append(plan_id)
        for seed in seeds:
            experiment_id = f"{campaign_id}.{plan_id}.s{seed}"
            manifest_data = {
                "manifest_version": 1, "experiment_id": experiment_id, "experiment_type": "fault_injection",
                "dataset_kind": DATASET_SYNTHETIC,
                "description": f"campaign={campaign_id} plan={plan_id} seed={seed}",
                "seed": seed, "timeout_seconds": data["timeout_seconds"], "limits": limits,
                "scenarios": raw["scenarios"],
            }
            try:
                manifest = parse_manifest(manifest_data)
                plan = build_plan(manifest)
                check_plan_limits(manifest, plan)
            except ManifestError as exc:
                raise _fail(f"plans[{i}] ({plan_id}), seed {seed}: {exc}") from exc
            experiments.append(CampaignExperiment(experiment_id, plan_id, group, seed,
                                                  json.loads(json.dumps(manifest_data)), manifest, plan))

    duplicates = sorted({p for p in plan_ids if plan_ids.count(p) > 1})
    if duplicates:
        raise _fail(f"plan_id'ler benzersiz olmalı (tekrar eden: {', '.join(duplicates)})")
    total = sum(len(e.plan.entries) for e in experiments)
    if total > MAX_CAMPAIGN_REQUESTS:
        raise _fail(f"kampanya en çok {MAX_CAMPAIGN_REQUESTS} istek planlayabilir (planlanan: {total})")
    return Campaign(campaign_id, description, tuple(seeds), tuple(experiments))


def load_campaign(path: str | Path) -> tuple[Campaign, str]:
    """(kampanya, dosyanın orijinal baytlarının SHA-256 özeti)."""
    path = Path(path)
    data = read_json_file(path, CampaignError, "Kampanya manifesti")
    return parse_campaign(data), hashlib.sha256(path.read_bytes()).hexdigest()


# --- güvenli yollar ve dosya özetleri ---
def safe_relative(root: Path, relative: Any) -> Path:
    """Kampanya kökü içindeki göreli POSIX yolunu çözer; dışarı çıkan veya mutlak yolu reddeder (ValueError)."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError(f"geçersiz göreli yol: {relative!r}")
    # Ham bileşenler denetlenir: PurePosixPath "." ve boş bileşenleri sessizce normalleştirir.
    if relative.startswith("/") or any(part in ("..", ".", "") for part in relative.split("/")):
        raise ValueError(f"göreli yol kampanya dizini dışına çıkamaz veya normal biçimde değil: {relative!r}")
    pure = PurePosixPath(relative)
    root = root.resolve()
    resolved = (root / Path(*pure.parts)).resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"yol kampanya dizini dışında: {relative!r}")
    return resolved


def file_record(root: Path, path: Path, role: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {"role": role, "path": path.resolve().relative_to(root.resolve()).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


# --- katalog doğrulaması ---
@dataclass(frozen=True)
class VerificationIssue:
    experiment_id: str | None
    rule: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"experiment_id": self.experiment_id, "rule": self.rule, "message": self.message}


def load_catalog(campaign_dir: str | Path) -> tuple[dict[str, Any], str]:
    """Kataloğu okur; (katalog, SHA-256). Biçim hatasında CampaignError."""
    path = Path(campaign_dir) / CATALOG_NAME
    try:
        raw = path.read_bytes()
        catalog = json.loads(raw.decode("utf-8"))
    except FileNotFoundError as exc:
        raise _fail(f"katalog bulunamadı: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(f"katalog okunamadı ({path.name}): {exc}") from exc
    if not isinstance(catalog, dict) or catalog.get("format") != CATALOG_FORMAT:
        raise _fail(f"katalog biçimi tanınmadı (beklenen format: {CATALOG_FORMAT})")
    if catalog.get("catalog_schema_version") != CATALOG_SCHEMA_VERSION:
        raise _fail(f"desteklenmeyen catalog_schema_version: {catalog.get('catalog_schema_version')!r}")
    if not isinstance(catalog.get("experiments"), list):
        raise _fail("katalogda 'experiments' listesi yok")
    return catalog, hashlib.sha256(raw).hexdigest()


def _read_verified(root: Path, entry: dict[str, Any], record: Any,
                   issues: list[VerificationIssue]) -> Path | None:
    """Dosya kaydını doğrular (güvenli yol, varlık, boyut, SHA-256); geçerliyse çözülmüş yolu döndürür."""
    eid = entry.get("experiment_id")
    if not isinstance(record, dict) or record.get("role") not in FILE_ROLES:
        issues.append(VerificationIssue(eid, "catalog_format", f"dosya kaydı geçersiz: {record!r:.120}"))
        return None
    try:
        path = safe_relative(root, record.get("path"))
    except ValueError as exc:
        issues.append(VerificationIssue(eid, "path_unsafe", str(exc)))
        return None
    if not path.is_file():
        issues.append(VerificationIssue(eid, "file_missing", f"{record.get('role')}: {record.get('path')} yok"))
        return None
    data = path.read_bytes()
    if len(data) != record.get("size_bytes"):
        issues.append(VerificationIssue(eid, "file_size_mismatch",
                                        f"{record.get('path')}: boyut {len(data)} != katalog {record.get('size_bytes')}"))
    if hashlib.sha256(data).hexdigest() != record.get("sha256"):
        issues.append(VerificationIssue(eid, "file_hash_mismatch", f"{record.get('path')}: SHA-256 katalogla uyuşmuyor"))
        return None
    return path


def verify_entry(root: Path, entry: dict[str, Any]) -> tuple[list[VerificationIssue], dict[str, Any] | None]:
    """Bir katalog girdisini doğrular; (sorunlar, tamamlanmış ve geçerliyse etiket belgesi)."""
    issues: list[VerificationIssue] = []
    eid = entry.get("experiment_id") if isinstance(entry, dict) else None
    if not isinstance(entry, dict) or not isinstance(eid, str) or not isinstance(entry.get("files"), list):
        return [VerificationIssue(eid, "catalog_format", "katalog girdisi eksik alan içeriyor")], None
    roles: dict[str, Path] = {}
    for record in entry["files"]:
        path = _read_verified(root, entry, record, issues)
        if path is not None:
            roles[record["role"]] = path
    if issues or entry.get("status") != "completed":
        return issues, None

    for role in FILE_ROLES:
        if role not in roles:
            issues.append(VerificationIssue(eid, "file_missing", f"tamamlanmış deneyde {role} dosyası kayıtlı değil"))
    if issues:
        return issues, None

    try:
        manifest = parse_manifest(json.loads(roles["manifest"].read_text(encoding="utf-8")))
    except (ManifestError, ValueError) as exc:
        return [VerificationIssue(eid, "manifest_invalid", str(exc))], None
    if manifest.experiment_id != eid:
        issues.append(VerificationIssue(eid, "manifest_invalid", "manifest experiment_id katalogla uyuşmuyor"))
    plan_sha = build_plan(manifest).sha256
    if plan_sha != entry.get("plan_sha256"):
        issues.append(VerificationIssue(eid, "manifest_invalid", "manifestten üretilen plan_sha256 katalogla uyuşmuyor"))

    run_id = entry.get("run_id")
    try:
        run = load_run(roles["results_json"].parent, run_id)
    except (StorageError, ValueError) as exc:
        return issues + [VerificationIssue(eid, "results_invalid", str(exc))], None
    if run.files[0].name != roles["results_json"].name or run.files[1].name != roles["results_csv"].name:
        issues.append(VerificationIssue(eid, "results_inconsistent", "okunan sonuç dosyaları katalogdakilerle aynı değil"))
    synthetic = run.metadata.get("synthetic") or {}
    if run.dataset_kind != DATASET_SYNTHETIC or synthetic.get("experiment_id") != eid \
            or synthetic.get("plan_sha256") != plan_sha:
        issues.append(VerificationIssue(eid, "results_inconsistent",
                                        "sonuç metadata'sı (dataset_kind / synthetic) deneyle uyuşmuyor"))

    try:
        labels = json.loads(roles["labels"].read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return issues + [VerificationIssue(eid, "labels_invalid", str(exc))], None
    checks = (
        (isinstance(labels, dict) and labels.get("format") == LABELS_FORMAT, "etiket biçimi tanınmadı"),
        (isinstance(labels, dict) and (labels.get("run") or {}).get("run_id") == run_id, "etiket run_id uyuşmuyor"),
        (isinstance(labels, dict) and (labels.get("experiment") or {}).get("plan_sha256") == plan_sha,
         "etiket plan_sha256 uyuşmuyor"),
        (isinstance(labels, dict) and (labels.get("verdict") or {}).get("valid") == entry.get("valid"),
         "etiket geçerlilik kararı katalogla uyuşmuyor"),
        (isinstance(labels, dict) and isinstance(labels.get("requests"), list)
         and len(labels["requests"]) == len(build_plan(manifest).entries), "etiket istek sayısı planla uyuşmuyor"),
    )
    for ok, message in checks:
        if not ok:
            issues.append(VerificationIssue(eid, "labels_inconsistent", message))
    if not issues and isinstance(labels, dict):
        summary = labels.get("summary") or {}
        if entry.get("labels_summary") != {k: summary.get(k) for k in ("planned", "executed", "confirmed",
                                                                         "contradicted", "not_executed")}:
            issues.append(VerificationIssue(eid, "labels_inconsistent", "etiket özet sayıları katalogla uyuşmuyor"))
    return issues, (labels if not issues else None)


def verify_campaign(campaign_dir: str | Path) -> dict[str, Any]:
    """Kataloğu ve başvurduğu tüm dosyaları doğrular. Sonuç: {ok, catalog_sha256, issues, labels}."""
    root = Path(campaign_dir)
    catalog, catalog_sha = load_catalog(root)
    issues: list[VerificationIssue] = []
    labels: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()

    # Kampanya manifesti kopyası: özet tutmalı ve yeniden açıldığında aynı planı ve deney listesini vermeli.
    record = catalog.get("campaign_manifest") or {}
    try:
        manifest_path = safe_relative(root, record.get("path"))
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != record.get("sha256"):
            raise ValueError("campaign manifesti SHA-256 katalogla uyuşmuyor")
        campaign, _ = load_campaign(manifest_path)
        if campaign.plan_sha256 != catalog.get("campaign_plan_sha256"):
            raise ValueError("manifestten yeniden üretilen campaign_plan_sha256 katalogla uyuşmuyor")
        expected = [e.experiment_id for e in campaign.experiments]
        listed = [e.get("experiment_id") for e in catalog["experiments"] if isinstance(e, dict)]
        if sorted(expected) != sorted(listed):
            raise ValueError("katalogdaki deney listesi manifestten açılan listeyle aynı değil")
    except (ValueError, OSError) as exc:  # CampaignError da ValueError'dır
        issues.append(VerificationIssue(None, "campaign_manifest_invalid", str(exc)))
    for entry in catalog["experiments"]:
        eid = entry.get("experiment_id") if isinstance(entry, dict) else None
        if eid in seen:
            issues.append(VerificationIssue(eid, "catalog_format", "deney kimliği katalogda tekrar ediyor"))
            continue
        seen.add(eid)
        entry_issues, doc = verify_entry(root, entry)
        issues.extend(entry_issues)
        if doc is not None:
            labels[eid] = doc
    return {"ok": not issues, "catalog": catalog, "catalog_sha256": catalog_sha,
            "issues": [i.to_dict() for i in issues], "labels": labels}
