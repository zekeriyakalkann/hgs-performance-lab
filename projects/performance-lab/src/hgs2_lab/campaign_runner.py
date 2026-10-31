"""Sentetik deney kampanyasını yürütür ve katalog (`campaign.json`) yazar.

Her deney, tek deney akışıyla (`synthetic_experiment.run_synthetic_experiment`) AYNEN yürütülür: yerel sentetik
sunucu yalnızca 127.0.0.1'de, ön kontrol + loopback koruması + proxy reddi + yönlendirme izlememe değişmeden.

Kampanya dizini (`--output-dir`; yoksa oluşturulur, varsa BOŞ olmalıdır):
* `campaign-manifest.json`        : kampanya manifestinin bayt bayt kopyası
* `manifests/<deney>.json`        : açılan deney manifestleri (deterministik; çalıştırmadan önce yazılır)
* `runs/`                         : tüm deneylerin sonuç dizini (sonuçlar, `synthetic/` etiketleri ve sunucu olayları)
* `campaign.json`                 : katalog (çalıştırma sonunda, kesintide de yazılır)

Hata yalıtımı: her deney kendi try bloğunda çalışır ve kendi run_id'li dosyalarını yazar; bir deneyin
reddedilmesi veya hata vermesi diğerlerini etkilemez, katalogda durum ve nedenle gösterilir. Ctrl+C kampanyayı
durdurur; kalan deneyler `not_run` olarak kaydedilir.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .analysis import write_document
from .campaign import (
    CATALOG_FORMAT,
    CATALOG_NAME,
    CATALOG_SCHEMA_VERSION,
    MANIFESTS_DIR,
    RUNS_DIR,
    STATUS_ERROR,
    STATUS_NOT_RUN,
    STATUS_REJECTED,
    CampaignExperiment,
    file_record,
    load_campaign,
)
from .execution import PreflightError
from .metadata import code_info, dependency_versions, environment_info
from .models import DATASET_SYNTHETIC, STATUS_COMPLETED, STATUS_INTERRUPTED
from .sanitize import sanitize_text
from .storage import ResultStore
from .synthetic_experiment import PROCESS_MODEL_SAME_PROCESS, output_paths, run_synthetic_experiment
from .synthetic_server import HOLD_METHOD, SyntheticServer
from .target_guard import Resolver, system_resolver

CAMPAIGN_MANIFEST_COPY = "campaign-manifest.json"


class CampaignRejected(Exception):
    """Kampanya başlamadan reddedildi (ör. çıktı dizini boş değil); hiçbir deney çalıştırılmadı."""


@dataclass
class CampaignOutcome:
    catalog: dict[str, Any]
    catalog_path: Path

    @property
    def interrupted(self) -> bool:
        return self.catalog["status"] == STATUS_INTERRUPTED

    @property
    def all_valid(self) -> bool:
        return all(e["valid"] for e in self.catalog["experiments"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prepare_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        if not output_dir.is_dir():
            raise CampaignRejected(f"çıktı yolu bir dizin değil: {output_dir}")
        if any(output_dir.iterdir()):
            raise CampaignRejected(f"çıktı dizini boş değil, üzerine yazılmaz: {output_dir}")
    (output_dir / MANIFESTS_DIR).mkdir(parents=True, exist_ok=True)
    (output_dir / RUNS_DIR).mkdir(exist_ok=True)


def _collect_files(root: Path, experiment: CampaignExperiment) -> list[dict[str, Any]]:
    """Deneye ait var olan tüm dosyalar (tam veya kısmi), sabit rol sırasıyla."""
    runs = root / RUNS_DIR
    records = [file_record(root, root / MANIFESTS_DIR / f"{experiment.experiment_id}.json", "manifest")]
    for partial in (False, True):
        csv_path, json_path = ResultStore(runs).paths(experiment.experiment_id, partial)
        labels_path, events_path = output_paths(runs, experiment.experiment_id, partial)
        for role, path in (("results_json", json_path), ("results_csv", csv_path), ("labels", labels_path),
                           ("server_events", events_path)):
            if path.is_file():
                records.append(file_record(root, path, role))
    return records


def _entry(root: Path, experiment: CampaignExperiment, *, status: str, started: str | None, finished: str | None,
           outcome: Any = None, error: BaseException | None = None) -> dict[str, Any]:
    labels = outcome.labels if outcome is not None else None
    results = outcome.run.results if outcome is not None else []
    if labels is not None:
        valid = bool(labels["verdict"]["valid"]) and status == STATUS_COMPLETED
        reasons = [r["code"] for r in labels["verdict"]["reasons"]]
        summary = {k: labels["summary"][k] for k in ("planned", "executed", "confirmed", "contradicted", "not_executed")}
    else:
        valid, reasons, summary = False, [status], None
    error_info = None
    if error is not None:
        message = sanitize_text(str(error)).replace(str(root.resolve()), "<campaign_dir>")[:300]
        error_info = {"type": type(error).__name__, "message": message}
    return {
        "experiment_id": experiment.experiment_id,
        "run_id": experiment.experiment_id,
        "plan_id": experiment.plan_id,
        "group": experiment.group,
        "seed": experiment.seed,
        "plan_sha256": experiment.plan.sha256,
        "design_fingerprint": experiment.design_fingerprint,
        "scenarios": [{"name": s.name, "fault": s.fault.to_dict()} for s in experiment.manifest.scenarios],
        "status": status,
        "valid": valid,
        "invalid_reasons": [] if valid else reasons,
        "error": error_info,
        "started_at_utc": started,
        "finished_at_utc": finished,
        "requests": {
            "planned": len(experiment.plan.entries),
            "recorded": len(results),
            "http_errors": sum(r.http_ok is False for r in results),
            "transport_errors": sum(r.error_type is not None for r in results),
        },
        "labels_summary": summary,
        "files": _collect_files(root, experiment) if status != STATUS_NOT_RUN else
        [file_record(root, root / MANIFESTS_DIR / f"{experiment.experiment_id}.json", "manifest")],
    }


def run_campaign(
    manifest_path: str | Path,
    *,
    output_dir: str | Path,
    resolver: Resolver = system_resolver,
    server_factory: Callable[..., SyntheticServer] = SyntheticServer,
    run_experiment: Callable[..., Any] = run_synthetic_experiment,
    now: Callable[[], str] = _utc_now_iso,
    code: dict[str, Any] | None = None,
) -> CampaignOutcome:
    """Kampanyayı yürütür. Manifest hatası CampaignError; çıktı dizini uygun değilse CampaignRejected."""
    manifest_path = Path(manifest_path)
    campaign, manifest_sha256 = load_campaign(manifest_path)
    root = Path(output_dir)
    _prepare_output_dir(root)

    shutil.copyfile(manifest_path, root / CAMPAIGN_MANIFEST_COPY)
    for experiment in campaign.experiments:  # plan, çalıştırmadan önce diske yazılır
        write_document(experiment.manifest_data, root / MANIFESTS_DIR / f"{experiment.experiment_id}.json")

    catalog: dict[str, Any] = {
        "format": CATALOG_FORMAT,
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "dataset_kind": DATASET_SYNTHETIC,
        "note": "Sentetik deney kampanyası; gerçek HGS2 ölçümü değildir. Etiket ayrıntıları etiket dosyalarındadır; "
                "katalog yalnızca dizin ve özet tutar.",
        "campaign_id": campaign.campaign_id,
        "description": campaign.description,
        "campaign_plan_sha256": campaign.plan_sha256,
        "campaign_manifest": {"role": "campaign_manifest", "path": CAMPAIGN_MANIFEST_COPY, "sha256": manifest_sha256},
        "seeds": list(campaign.seeds),
        "groups": sorted({e.group for e in campaign.experiments}),
        "tool": {"name": "hgs2-lab", "version": __version__},
        "environment": environment_info(),
        "dependencies": dependency_versions(),
        "code": code if code is not None else code_info(),
        "process_model": PROCESS_MODEL_SAME_PROCESS,
        "hold_method": HOLD_METHOD,
        "started_at_utc": now(),
        "finished_at_utc": None,
        "status": STATUS_COMPLETED,
        "experiments": [],
    }
    entries: list[dict[str, Any]] = catalog["experiments"]
    try:
        for experiment in campaign.experiments:
            if catalog["status"] == STATUS_INTERRUPTED:
                entries.append(_entry(root, experiment, status=STATUS_NOT_RUN, started=None, finished=None))
                continue
            started = now()
            try:
                outcome = run_experiment(root / MANIFESTS_DIR / f"{experiment.experiment_id}.json",
                                         results_dir=root / RUNS_DIR, run_id=experiment.experiment_id,
                                         resolver=resolver, server_factory=server_factory, now=now)
            except PreflightError as exc:
                entries.append(_entry(root, experiment, status=STATUS_REJECTED, started=started, finished=now(),
                                      error=exc))
            except KeyboardInterrupt as exc:
                catalog["status"] = STATUS_INTERRUPTED
                entries.append(_entry(root, experiment, status=STATUS_INTERRUPTED, started=started, finished=now(),
                                      error=exc))
            except Exception as exc:  # noqa: BLE001 - bir deneyin hatası kampanyayı durdurmaz, katalogda gösterilir
                entries.append(_entry(root, experiment, status=STATUS_ERROR, started=started, finished=now(),
                                      error=exc))
            else:
                status = outcome.run.status
                entries.append(_entry(root, experiment, status=status, started=started, finished=now(),
                                      outcome=outcome))
                if status == STATUS_INTERRUPTED:  # Ctrl+C çalıştırma içinde yakalandı: kampanya durur
                    catalog["status"] = STATUS_INTERRUPTED
    finally:
        done = {e["experiment_id"] for e in entries}
        for experiment in campaign.experiments:  # beklenmeyen bir kesintide de her deney katalogda yer alır
            if experiment.experiment_id not in done:
                entries.append(_entry(root, experiment, status=STATUS_NOT_RUN, started=None, finished=None))
        statuses = [e["status"] for e in entries]
        catalog["finished_at_utc"] = now()
        catalog["summary"] = {
            "experiments": len(entries),
            "valid": sum(e["valid"] for e in entries),
            "invalid": sum(not e["valid"] for e in entries),
            "by_status": {s: statuses.count(s) for s in sorted(set(statuses))},
        }
        catalog_path = root / CATALOG_NAME
        write_document(catalog, catalog_path)
    return CampaignOutcome(catalog, catalog_path)
