"""Sentetik deneyi uçtan uca yürütür: manifest -> plan -> yerel sunucu -> mevcut çalıştırma akışı -> etiketler.

Çalıştırma, `run` komutunun kullandığı `execute_run` ile AYNEN yapılır: ön kontrol (hedef metni + ad
çözümlemesi, yalnızca loopback), bağlantı katmanında loopback koruması, proxy reddi, yönlendirme izlememe ve
güvenlik sınırları değişmeden uygulanır. Sentetik sunucu yalnızca normal bir `http://127.0.0.1:<port>` hedefidir.

Çıktılar (`<sonuç dizini>`):
* `<run_id>[.partial].csv/json`  : istemci sonuçları (şema v2, metadata'da `dataset_kind = "synthetic"`)
* `synthetic/<stem>.server-events.json` : sunucu tarafı olaylar (ayrı kaynak; uygulanan hatayı içerir)
* `synthetic/<stem>.labels.json` : beklenen / gözlenen / uyum ve deney geçerliliği
Hiçbir dosyanın üzerine yazılmaz; dosyalar varsa hiçbir istek gönderilmeden reddedilir.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .analysis import write_document
from .config import LabConfig
from .execution import PreflightError, RunOutcome, execute_run, generate_run_id
from .models import DATASET_SYNTHETIC, validate_run_id
from .reader import load_run
from .storage import ResultStore
from .synthetic import (
    LABELS_FORMAT,
    LABELS_SCHEMA_VERSION,
    PLAN_ALGORITHM_VERSION,
    SyntheticManifest,
    SyntheticPlan,
    build_labels,
    build_plan,
    check_plan_limits,
    load_manifest,
)
from .synthetic_server import HOLD_METHOD, HOLD_SLICE_SECONDS, SyntheticServer
from .target_guard import Resolver, system_resolver

SYNTHETIC_DIR_NAME = "synthetic"
SERVER_EVENTS_FORMAT = "hgs2-lab-synthetic-server-events"
PROCESS_MODEL_SAME_PROCESS = "same_process"

# Sunucu olaylarındaki zaman alanlarının kesin anlamı (dosyaya da yazılır; README "Gecikme alanları").
SERVER_TIMING_FIELDS = {
    "received_ns": "İstek satırı, başlıklar ve varsa gövde okunduktan sonra plan girdisinin kilit altında ayrıldığı an "
                   "(_claim). TCP kabulü, iş parçacığı başlatma ve başlık ayrıştırma bu andan öncedir.",
    "hold_ms_planned": "Plandaki bekleme talimatı (PlannedRequest.delay_ms). Ölçüm değildir.",
    "hold_started_ns": "Bekleme döngüsünün hemen öncesi (_hold). Yalnızca hold_ms_planned > 0 ise dolu.",
    "hold_ended_ns": "Bekleme döngüsünün hemen sonrası (_hold). Yalnızca hold_ms_planned > 0 ise dolu.",
    "hold_ms_actual": "(hold_ended_ns - hold_started_ns) / 1e6: sunucunun gerçekten beklediği süre. İstek okuma ve "
                      "yanıt yazma dahil DEĞİLDİR; servis süresi ya da istemci yanıt süresi değildir. outcome = "
                      "'stopped' ise sunucu kapanırken kesilmiştir.",
    "completed_ns": "Yanıt sokete yazıldıktan (veya yanıtsız kapatma kararından) sonra kayıt kilidinin alındığı an "
                    "(_finish). Aynı süreçte GIL nedeniyle gecikebilir.",
    "*_offset_ms": "(x_ns - istemci saat çapası monotonic_ns) / 1e6. Yalnızca aynı süreç ve aynı saat "
                   "(time.perf_counter_ns) olduğu için anlamlıdır.",
    "completed_ns - received_ns": "Sunucu tarafı toplam işleme aralığı: bekleme + yanıt yazma + kayıt. Servis süresi "
                                  "olarak kullanılmamalıdır (timing_caveats).",
}


@dataclass
class SyntheticOutcome:
    run: RunOutcome
    valid: bool
    labels_path: Path
    server_events_path: Path
    labels: dict[str, Any]
    server_leftover_threads: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_paths(results_dir: str | Path, run_id: str, partial: bool) -> tuple[Path, Path]:
    stem = f"{run_id}.partial" if partial else run_id
    directory = Path(results_dir) / SYNTHETIC_DIR_NAME
    return directory / f"{stem}.labels.json", directory / f"{stem}.server-events.json"


def prepare(manifest_path: str | Path) -> tuple[SyntheticManifest, str, SyntheticPlan]:
    """Manifesti okur, planı üretir ve plan sınırlarını denetler (istek yok)."""
    manifest, manifest_sha256 = load_manifest(manifest_path)
    plan = build_plan(manifest)
    check_plan_limits(manifest, plan)
    return manifest, manifest_sha256, plan


def _server_events_document(snapshot: dict[str, Any], run_id: str, anchor_ns: int | None,
                            now: Callable[[], str]) -> dict[str, Any]:
    events = []
    for event in snapshot["events"]:
        item = dict(event)
        # Sunucu ve istemci aynı süreçte, aynı saatte (time.perf_counter_ns): çapaya göre ofset anlamlıdır.
        for key in ("received_ns", "hold_started_ns", "hold_ended_ns", "completed_ns"):
            value = item.get(key)
            item[key.replace("_ns", "_offset_ms")] = (value - anchor_ns) / 1e6 \
                if anchor_ns is not None and value is not None else None
        events.append(item)
    return {
        "format": SERVER_EVENTS_FORMAT,
        "schema_version": 1,  # ek alanlar sürüm değiştirmez (README "Sentetik deneyler"); alan silme/anlam değişikliği değiştirir
        "generated_at": now(),
        "dataset_kind": DATASET_SYNTHETIC,
        "run_id": run_id,
        "source": snapshot["source"],
        "note": "Sunucu tarafı kayıtlar; istemci ölçümlerinden ayrı bir kaynaktır ve uygulanan hatayı içerir. "
                "Model girdisi olarak kullanılması etiket sızıntısıdır.",
        "clock": {"source": "time.perf_counter_ns", "offset_reference": "run clock anchor monotonic_ns",
                  "offset_available": anchor_ns is not None},
        # Ölçüm yalıtımı incelemesi (README "Ölçüm yalıtımı"): sunucu istemciyle aynı süreçte, aynı GIL'i
        # paylaşan iş parçacıklarında çalışır. Bu, sunucu zaman damgalarının yorumunu sınırlar.
        "process_model": PROCESS_MODEL_SAME_PROCESS,
        "hold_method": {"name": HOLD_METHOD, "slice_ms": HOLD_SLICE_SECONDS * 1000,
                        "clock": "time.perf_counter_ns (son tarih ve ölçüm)", "sleep": "time.sleep"},
        "timing_fields": SERVER_TIMING_FIELDS,
        "timing_caveats": [
            "completed_ns, yanıt yazıldıktan sonra GIL yeniden alınınca damgalanır; istemcinin işlem süresi araya "
            "girebilir. Bu yüzden (completed_ns - received_ns) milisaniye altı düzeyde şişebilir ve istemci süresinden "
            "uzun görünebilir; sunucu servis süresi olarak kullanılmamalıdır.",
            "hold_ms_actual planlanan gecikmeden (hold_ms_planned) kısa olamaz ama uzun olabilir: işletim sistemi "
            "uyandırma gecikmesi ve iş parçacığı zamanlaması. Enjekte edilen gerçek bekleme için hold_ms_planned değil "
            "hold_ms_actual esas alınmalıdır. Bu bekleme yöntemi (sliced_sleep) ile Windows/Python 3.15'te aşım "
            "medyanı 1 ms'nin altında ölçüldü; başka platformlarda ayrıca ölçülmelidir.",
        ],
        "summary": {k: snapshot[k] for k in ("arrivals", "unexpected_requests", "dropped_events", "errors")},
        "events": events,
    }


def run_synthetic_experiment(
    manifest_path: str | Path,
    *,
    results_dir: str | Path,
    run_id: str | None = None,
    resolver: Resolver = system_resolver,
    server_factory: Callable[[SyntheticPlan], SyntheticServer] = SyntheticServer,
    now: Callable[[], str] = _utc_now_iso,
) -> SyntheticOutcome:
    """Sentetik deneyi yürütür. Manifest hatası ManifestError; ön kontrol PreflightError (istek yok)."""
    manifest_path = Path(manifest_path).resolve()
    manifest, manifest_sha256, plan = prepare(manifest_path)
    try:
        run_id = validate_run_id(run_id) if run_id is not None else generate_run_id()
    except ValueError as exc:
        raise PreflightError(str(exc)) from exc

    existing = ResultStore(results_dir).existing_files(run_id) + [
        p for partial in (False, True) for p in output_paths(results_dir, run_id, partial) if p.exists()
    ]
    if existing:
        raise PreflightError(f"Bu run_id için dosya zaten var, üzerine yazılmaz: {existing[0].name}")

    synthetic_meta = {
        "experiment_id": manifest.experiment_id,
        "experiment_type": manifest.experiment_type,
        "manifest_version": manifest.manifest_version,
        "manifest_sha256": manifest_sha256,
        "seed": manifest.seed,
        "plan_algorithm_version": PLAN_ALGORITHM_VERSION,
        "plan_sha256": plan.sha256,
        "generator_version": __version__,
        "created_at_utc": now(),
        "server": "hgs2_lab.synthetic_server (127.0.0.1, uygulamanın kendi yerel test sunucusu)",
        "labels_location": f"{SYNTHETIC_DIR_NAME}/<run_id>[.partial].labels.json",
        "note": "Sentetik deney; gerçek HGS2 ölçümü değildir. Planlanan hatalar bu dosyada yer almaz.",
    }

    server = server_factory(plan)
    server.start()
    try:
        config = LabConfig(
            base_url=server.base_url, timeout_seconds=manifest.timeout_seconds, output_dir=Path(results_dir),
            scenarios_file=manifest_path, limits=manifest.limits,
        )
        outcome = execute_run(
            config, [s.to_engine_scenario() for s in manifest.scenarios], config_path=manifest_path,
            target_label=f"synthetic:{manifest.experiment_id}", run_id=run_id, resolver=resolver,
            dataset_kind=DATASET_SYNTHETIC, synthetic=synthetic_meta,
        )
    finally:
        leftovers = server.stop()

    # Kaydedilen dosyalar okuyucuyla yeniden okunur: etiketler diske yazılanla birebir eşleşir.
    stored = load_run(results_dir, run_id)
    labels_path, events_path = output_paths(results_dir, run_id, stored.partial)
    snapshot = server.snapshot()
    anchor_ns = stored.clock.monotonic_ns \
        if stored.clock is not None and stored.clock.monotonic_source == "time.perf_counter_ns" else None
    events_doc = _server_events_document(snapshot, run_id, anchor_ns, now)
    write_document(events_doc, events_path)

    content = build_labels(
        manifest, manifest_sha256, plan, run_id=run_id, partial=stored.partial,
        execution_status=stored.execution["status"] if stored.execution else None, results=stored.results,
        result_files=[f.to_dict() for f in stored.files],
        server=snapshot,
        server_events_file={"name": events_path.name, "sha256": hashlib.sha256(events_path.read_bytes()).hexdigest()},
    )
    if leftovers:
        content["verdict"]["reasons"].append(
            {"code": "server_threads_leftover", "message": f"{len(leftovers)} sunucu iş parçacığı kapanmadı"})
        content["verdict"]["valid"] = False
    document = {"format": LABELS_FORMAT, "labels_schema_version": LABELS_SCHEMA_VERSION, "generated_at": now(),
                **content}
    write_document(document, labels_path)
    return SyntheticOutcome(outcome, content["verdict"]["valid"], labels_path, events_path, document, len(leftovers))
