"""Komut satırı giriş noktası.

Komutlar:
* validate: yapılandırma ve senaryoları doğrular (istek göndermez).
* list:     senaryoları listeler (istek göndermez).
* run:      senaryoları YALNIZCA loopback hedefe karşı çalıştırır ve sonuçları kaydeder.
            `run` ve `synthetic run` için `--telemetry`: sistem telemetrisini ayrı dosyaya yazar (bkz. telemetry.py).
* analyze:  kaydedilmiş bir çalıştırmanın CSV/JSON dosyalarını çevrimdışı analiz eder (istek göndermez).
* synthetic validate|plan|run: uygulamanın kendi yerel sentetik sunucusuyla planlı hata deneyleri
  (gerçek HGS2 değildir; bkz. synthetic.py).
* campaign validate|run|verify: toplu sentetik deney kampanyası ve kataloğu (bkz. campaign.py).
* dataset build: doğrulanmış bir kampanya kataloğundan train/validation/test veri seti manifesti (bkz. dataset.py).
* dataset features: doğrulanmış veri setinden deterministik özellik tablosu; features.csv + labels.csv + manifest
  (bkz. features.py). 0 = yazıldı, 1 = doğrulama hatası, 5 = çıktı dizini boş değil / yazılamadı.
* detect robust-z: özellik tablosundan Robust Z-score gecikme dedektörü; train normal satırlarıyla kalibrasyon,
  bölüm bazında değerlendirme (bkz. detection.py). 0 = yazıldı, 1 = doğrulama/kalibrasyon hatası, 5 = çıktı var.
* junit classify: JUnit/Surefire XML raporlarını çevrimdışı ve toplu olarak ayrıştırır (junit_report.py), isteğe
  bağlı beklenti dosyasıyla açık senaryo kimliği üzerinden eşleştirir, her testi kanıta dayalı kurallarla
  sınıflandırır (classify.py, junit_analysis.py) ve tek JSON belgesi yazar. 0 = yazıldı, 1 = yazıldı ama en az bir
  rapor dosyası reddedildi (belgede `file_errors`) ya da beklenti dosyası geçersiz (hiçbir şey yazılmaz),
  5 = çıktı dosyası var / yazılamadı. Hedef sisteme erişmez.
* results classify: kaydedilmiş bir çalıştırmanın ölçüm isteklerini (iş sonucu dahil) TestRecord'a dönüştürür ve aynı
  kurallarla sınıflandırır (result_analysis.py). 0 = yazıldı, 1 = sonuç/beklenti dosyası okunamadı, 5 = çıktı var.
* readiness check: gerçek entegrasyon önkoşullarını çevrimdışı denetler (readiness.py): rapor alan envanteri, senaryo
  kimliği, beklenti sözleşmesi, güvenlik öz-testleri, analiz hattı. 0 = READY / READY_WITH_WARNINGS, 1 = BLOCKED,
  5 = çıktı var. Hedef sisteme, veritabanına veya ağa erişmez; READY hedef sistemin doğru çalıştığını göstermez.
* ingest analyze: veri alım paketini (ingestion.py) doğrular, kabul edilen kayıtları beklentiyle eşleştirip
  sınıflandırır ve JSON yazar. 0 = yazıldı, 1 = yazıldı ama girdi reddedildi ya da paket/beklenti dosyası geçersiz
  (hiçbir şey yazılmaz), 5 = çıktı var.
* expectations validate|show: beklenti sözleşmesini (expectations_version 2; expectations.py) doğrular / listeler.
  Dosyayı yalnızca okur. validate: 0 = geçerli (çelişkiler UYARI olarak), 1 = geçersiz (tüm bulgular listelenir).
* scenario-map validate: senaryo eşleme dosyasını (scenario_mapping_version 1; scenario_mapping.py) doğrular. Dosyayı
  yalnızca okur. 0 = geçerli (çelişkili eşlemeler UYARI olarak), 1 = geçersiz (tüm bulgular listelenir).
  `junit classify` ve `readiness check` için `--scenario-map`: kimlikler testcase özelliği ve eşleme dosyasından
  çözümlenir; çelişki/belirsizlikte kimlik seçilmez. Geçersiz eşleme dosyası `junit classify`'ı 1 ile durdurur
  (hiçbir şey yazılmaz); `readiness check`'te A6 engelleyicidir.

campaign run: 0 = tüm deneyler geçerli, 6 = en az bir deney geçersiz/başarısız (katalogda nedenleriyle),
3 = çıktı dizini boş değil (hiç deney çalışmadı), 130 = Ctrl+C. campaign verify: 0 = sorun yok, 1 = sorun var.
dataset build: 0 = yazıldı (uyarılar dosyada), 1 = doğrulama/politika/bütünlük hatası, 5 = çıktı dosyası var.

Çıkış kodları:
  0   başarılı (run: tüm planlanan istekler yapıldı; analyze: analiz dosyası yazıldı;
      synthetic run: deney tamamlandı ve tüm etiketler doğrulandı)
  1   yapılandırma/senaryo/manifest hatası; analyze: sonuç dosyaları eksik, bozuk veya tutarsız
  2   komut satırı kullanım hatası (argparse; analyze: geçersiz analiz parametresi)
  3   run/synthetic run ön kontrolde reddedildi; hiçbir istek gönderilmedi (hedef, bütçe, dosya çakışması)
  4   run/synthetic run güvenlik sınırıyla durduruldu; kısmi sonuçlar `.partial` dosyalarında
  5   sonuçlar kaydedilemedi; analyze/synthetic plan: çıktı dosyası zaten var veya yazılamadı
  6   synthetic run tamamlandı ama deney geçersiz (gözlenen sonuçlar planla uyuşmadı; gerekçeler etiket dosyasında)
  130 run kullanıcı tarafından (Ctrl+C) durduruldu; kısmi sonuçlar `.partial` dosyalarında
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from .analysis import (
    AnalysisError,
    AnalysisOutputError,
    AnalysisParams,
    build_document,
    default_output_path,
    write_document,
)
from .campaign import CampaignError, load_campaign, verify_campaign
from .campaign_runner import CampaignRejected, run_campaign
from .config import ConfigError, LabConfig, load_config
from .dataset import INVALID_POLICIES, DatasetError, build_dataset_document, parse_ratios
from .detection import DetectionError, write_evaluation
from .features import FEATURE_POLICIES, OBSERVED_V1, FeatureTableError, write_feature_table
from .execution import (
    STATUS_ABORTED,
    STATUS_COMPLETED,
    STATUS_INTERRUPTED,
    PreflightError,
    RunOutcome,
    execute_run,
    summarize,
)
from .junit_analysis import build_junit_analysis_document, parse_reports
from .models import InvalidRunId
from .reader import load_run
from .records import CLASSES, DATASET_KINDS, DATASET_UNKNOWN, EXPECTATION_SCOPES, SCOPE_REAL
from .expectations import load_registry
from .ingestion import IngestionError, build_ingestion_document, parse_ingestion
from .scenario_mapping import MappingError, load_mapping
from .readiness import BLOCKED as READINESS_BLOCKED
from .readiness import run_readiness
from .result_analysis import ExpectationsError, build_run_document, load_expectations, resolve_dataset_kind
from .robust_z import BASELINE_DEGENERATE, CalibrationError
from .scenarios import Scenario, ScenarioError, load_scenarios
from .storage import StorageError
from .synthetic import (
    ManifestError,
    SyntheticManifest,
    SyntheticPlan,
    estimated_min_duration_seconds,
    guard_forecast,
)
from .synthetic_experiment import prepare as prepare_synthetic
from .synthetic_experiment import run_synthetic_experiment
from .target_guard import TargetNotAllowed, check_url
from .telemetry import DEFAULT_INTERVAL_MS, TelemetryError, TelemetryRecorder, validate_interval_ms

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_REJECTED = 3
EXIT_ABORTED = 4
EXIT_STORAGE_ERROR = 5
EXIT_SYNTHETIC_INVALID = 6
EXIT_INTERRUPTED = 130

_EXIT_BY_STATUS = {STATUS_COMPLETED: EXIT_OK, STATUS_ABORTED: EXIT_ABORTED, STATUS_INTERRUPTED: EXIT_INTERRUPTED}


def _interval_ms(text: str) -> int:
    try:
        return validate_interval_ms(int(text))
    except (ValueError, TelemetryError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_telemetry_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--telemetry", action="store_true",
                   help="Sistem telemetrisini (CPU, bellek, disk, TCP) ayrı dosyaya kaydet: "
                        "<sonuç dizini>/telemetry/<run_id>[.partial].telemetry.json; sonuç dosyaları değişmez")
    p.add_argument("--telemetry-interval-ms", type=_interval_ms,
                   help=f"Telemetri örnekleme aralığı, ms (yalnızca --telemetry ile; varsayılan: {DEFAULT_INTERVAL_MS})")


def _telemetry_recorder(args: argparse.Namespace) -> TelemetryRecorder | None:
    if not args.telemetry:
        return None
    interval = args.telemetry_interval_ms if args.telemetry_interval_ms is not None else DEFAULT_INTERVAL_MS
    return TelemetryRecorder(interval_ms=interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hgs2-lab", description="HGS2 performans test aracı")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("validate", "Yapılandırma ve senaryo dosyalarını doğrula (istek göndermez)"),
        ("list", "Tanımlı senaryoları listele (istek göndermez)"),
        ("run", "Senaryoları yalnızca loopback hedefe karşı çalıştır ve sonuçları kaydet"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", default="configs/config.json", help="Yapılandırma dosyası (varsayılan: %(default)s)")
        p.add_argument(
            "--scenarios",
            help="Senaryo dosyası; verilirse yapılandırmadaki scenarios_file yerine kullanılır (çalışma dizinine göre)",
        )
        if name == "run":
            p.add_argument("--target-label", help="Hedef ortam etiketi; metadata'ya target_label olarak yazılır")
            _add_telemetry_arguments(p)

    defaults = AnalysisParams()
    p = sub.add_parser("analyze", help="Kaydedilmiş bir çalıştırmayı çevrimdışı analiz et (istek göndermez)")
    p.add_argument("--run-id", required=True, help="Analiz edilecek run_id (tam veya .partial dosyalar otomatik bulunur)")
    p.add_argument("--results-dir",
                   help="Sonuç dizini; verilmezse yapılandırmadaki output_dir kullanılır (çalışma dizinine göre)")
    p.add_argument("--config", default="configs/config.json",
                   help="--results-dir verilmezse output_dir için okunan yapılandırma (varsayılan: %(default)s)")
    p.add_argument("--output", help="Analiz dosyası; varsayılan <sonuç dizini>/analysis/<run_id>[.partial].analysis.json")
    p.add_argument("--seed", type=int, default=defaults.seed, help="Bootstrap tohumu (varsayılan: %(default)s)")
    p.add_argument("--bootstrap-resamples", type=int, default=defaults.bootstrap_resamples,
                   help="Bootstrap yeniden örnekleme sayısı (varsayılan: %(default)s)")
    p.add_argument("--confidence", type=float, default=defaults.confidence,
                   help="Güven aralığı düzeyi (varsayılan: %(default)s)")
    p.add_argument("--min-tail-samples", type=int, default=defaults.min_tail_samples,
                   help="Kuyruk yüzdeliğinin üstünde beklenen en az gözlem (varsayılan: %(default)s)")

    p = sub.add_parser("synthetic", help="Yerel sentetik test sunucusuyla planlı hata deneyleri (gerçek HGS2 değildir)")
    synthetic_sub = p.add_subparsers(dest="synthetic_command", required=True)
    for name, help_text in (
        ("validate", "Manifesti doğrula ve plan özetini göster (istek göndermez)"),
        ("plan", "Deterministik deney planını göster; --output ile tamamını JSON olarak yaz (istek göndermez)"),
        ("run", "Yerel sentetik sunucuyu 127.0.0.1'de başlat, deneyi çalıştır, etiketleri yaz, sunucuyu kapat"),
    ):
        q = synthetic_sub.add_parser(name, help=help_text)
        q.add_argument("--manifest", required=True, help="Sentetik deney manifesti (JSON)")
        if name == "plan":
            q.add_argument("--output", help="Planın tamamının yazılacağı JSON dosyası (üzerine yazılmaz)")
        if name == "run":
            q.add_argument("--results-dir", required=True, help="Sonuç dizini (sonuçlar, etiketler, sunucu olayları)")
            q.add_argument("--run-id", help="run_id; verilmezse otomatik üretilir")
            _add_telemetry_arguments(q)

    p = sub.add_parser("campaign", help="Toplu sentetik deney kampanyası ve katalog (gerçek HGS2 değildir)")
    campaign_sub = p.add_subparsers(dest="campaign_command", required=True)
    q = campaign_sub.add_parser("validate", help="Kampanya manifestini doğrula ve açılan deneyleri listele (istek yok)")
    q.add_argument("--manifest", required=True, help="Kampanya manifesti (JSON)")
    q = campaign_sub.add_parser("run", help="Tüm deneyleri yerel sentetik sunucuyla çalıştır ve katalog yaz")
    q.add_argument("--manifest", required=True, help="Kampanya manifesti (JSON)")
    q.add_argument("--output-dir", required=True, help="Kampanya dizini (yoksa oluşturulur; varsa boş olmalı)")
    q = campaign_sub.add_parser("verify", help="Kataloğu ve başvurduğu dosyaları doğrula (SHA-256, etiket tutarlılığı)")
    q.add_argument("--campaign-dir", required=True, help="Kampanya dizini")

    p = sub.add_parser("dataset", help="Kampanya kataloğundan veri seti manifesti (model eğitimi yok)")
    dataset_sub = p.add_subparsers(dest="dataset_command", required=True)
    q = dataset_sub.add_parser("build", help="train/validation/test bölmesi; grup bütünlüğü korunur")
    q.add_argument("--campaign-dir", required=True, help="Doğrulanacak kampanya dizini")
    q.add_argument("--output", required=True, help="Veri seti manifesti (JSON; üzerine yazılmaz)")
    q.add_argument("--split-seed", type=int, default=0, help="Bölme tohumu (varsayılan: %(default)s)")
    q.add_argument("--ratios", default="0.6,0.2,0.2", help="train,validation,test oranları (varsayılan: %(default)s)")
    q.add_argument("--invalid-policy", choices=INVALID_POLICIES, default="exclude",
                   help="Geçersiz deneyler: exclude = dışarıda bırak ve listele, fail = veri seti üretme")
    q = dataset_sub.add_parser("features", help="Doğrulanmış veri setinden deterministik özellik tablosu (CSV + manifest)")
    q.add_argument("--campaign-dir", required=True, help="Kampanya dizini")
    q.add_argument("--dataset", required=True, help="`dataset build` ile üretilen veri seti manifesti")
    q.add_argument("--output-dir", required=True, help="Çıktı dizini (yoksa oluşturulur; varsa boş olmalı)")
    q.add_argument("--policy", choices=sorted(FEATURE_POLICIES), default=OBSERVED_V1.name,
                   help="Sütun rolleri politikası (varsayılan: %(default)s)")

    p = sub.add_parser("detect", help="Gecikme anomalisi dedektörü (sentetik özellik tablosu üzerinde; ağ yok)")
    detect_sub = p.add_subparsers(dest="detect_command", required=True)
    q = detect_sub.add_parser("robust-z", help="Robust Z-score: train normal satırlarıyla kalibrasyon, sabit eşik "
                                                "z > 3.5, bölüm bazında değerlendirme")
    q.add_argument("--features-dir", required=True, help="`dataset features` çıktı dizini (salt okunur)")
    q.add_argument("--output", required=True, help="Değerlendirme JSON dosyası (üzerine yazılmaz)")

    p = sub.add_parser("junit", help="JUnit/Surefire XML test raporları (çevrimdışı; hedef sisteme erişmez)")
    junit_sub = p.add_subparsers(dest="junit_command", required=True)
    q = junit_sub.add_parser("classify", help="Raporları TestRecord'a dönüştür ve kanıta dayalı kurallarla sınıflandır")
    q.add_argument("--report", required=True, action="append", help="Rapor dosyası (birden çok kez verilebilir)")
    q.add_argument("--output", required=True, help="Sınıflandırma JSON dosyası (üzerine yazılmaz)")
    q.add_argument("--dataset-kind", choices=sorted(DATASET_KINDS), default=DATASET_UNKNOWN,
                   help="Kayıtların türü: real (gerçek sistem çıktısı), synthetic, fixture, unknown (varsayılan)")
    q.add_argument("--expectations", help="Beklenti dosyası (sürüm 2 registry veya sürüm 1); kayıtlar testcase "
                                          "özelliği hgs2_lab.scenario_id ile birebir eşleştirilir")
    q.add_argument("--scenario-map", help="Senaryo eşleme dosyası (scenario_mapping_version 1): <classname>#<name> → "
                                          "senaryo kimliği; metadata ile çelişirse kimlik seçilmez")

    p = sub.add_parser("readiness", help="Gerçek entegrasyon önkoşul denetimi (çevrimdışı)")
    readiness_sub = p.add_subparsers(dest="readiness_command", required=True)
    q = readiness_sub.add_parser("check", help="Rapor envanteri, senaryo kimliği, beklenti, güvenlik ve hat denetimi")
    q.add_argument("--report", required=True, action="append", help="JUnit/Surefire rapor dosyası (birden çok)")
    q.add_argument("--expectations", help="Beklenti sözleşmesi (sürüm 2)")
    q.add_argument("--scope", choices=sorted(EXPECTATION_SCOPES), default=SCOPE_REAL,
                   help="Denetlenen beklenti kapsamı (varsayılan: %(default)s)")
    q.add_argument("--scenario-map", help="Senaryo eşleme dosyası (scenario_mapping_version 1)")
    q.add_argument("--output", help="Hazırlık raporu JSON dosyası (üzerine yazılmaz)")

    p = sub.add_parser("ingest", help="Test sonucu örnekleri için veri alım sözleşmesi (çevrimdışı)")
    ingest_sub = p.add_subparsers(dest="ingest_command", required=True)
    q = ingest_sub.add_parser("analyze", help="Alım paketini doğrula, beklentiyle eşleştir ve sınıflandır")
    q.add_argument("--file", required=True, help="Alım paketi (JSON, ingestion_version 1)")
    q.add_argument("--expectations", help="Beklenti dosyası (sürüm 2 registry veya sürüm 1)")
    q.add_argument("--output", required=True, help="Sınıflandırma JSON dosyası (üzerine yazılmaz)")

    p = sub.add_parser("expectations", help="Beklenti sözleşmesi (expectations_version 2): doğrula / listele")
    expectations_sub = p.add_subparsers(dest="expectations_command", required=True)
    q = expectations_sub.add_parser("validate", help="Şema, kimlik, kanıt ve doğrulama durumu denetimi (salt okunur)")
    q.add_argument("--file", required=True, help="Beklenti dosyası (JSON)")
    q = expectations_sub.add_parser("show", help="Beklentileri, durumlarını ve kanıt referanslarını listele")
    q.add_argument("--file", required=True, help="Beklenti dosyası (JSON)")
    q.add_argument("--scenario", help="Yalnızca bu senaryo kimliği")

    p = sub.add_parser("scenario-map", help="Senaryo eşleme sözleşmesi (scenario_mapping_version 1): doğrula")
    mapping_sub = p.add_subparsers(dest="scenario_map_command", required=True)
    q = mapping_sub.add_parser("validate", help="Şema, kimlik, yineleme ve çelişki denetimi (salt okunur)")
    q.add_argument("--file", required=True, help="Eşleme dosyası (JSON)")

    p = sub.add_parser("results", help="Kaydedilmiş çalıştırma sonuçlarının test sonucu analizi (çevrimdışı)")
    results_sub = p.add_subparsers(dest="results_command", required=True)
    q = results_sub.add_parser("classify", help="Ölçüm isteklerini TestRecord'a dönüştür ve kanıta dayalı kurallarla "
                                                "sınıflandır (istek göndermez)")
    q.add_argument("--run-id", required=True, help="Sınıflandırılacak çalıştırma")
    q.add_argument("--results-dir", required=True, help="Sonuç dosyalarının dizini (salt okunur)")
    q.add_argument("--output", required=True, help="Sınıflandırma JSON dosyası (üzerine yazılmaz)")
    q.add_argument("--expectations", help="Senaryo başına beklenen sonuç dosyası (yoksa yalnızca senaryonun açık "
                                          "expected_status listesi kullanılır)")
    q.add_argument("--dataset-kind", choices=sorted(DATASET_KINDS),
                   help="Ölçüm çalıştırmasının türü (varsayılan: metadata synthetic ise synthetic, değilse unknown)")
    return parser


def _load(args: argparse.Namespace) -> tuple[LabConfig, list[Scenario]]:
    config = load_config(args.config)
    if args.scenarios:
        config = dataclasses.replace(config, scenarios_file=Path(args.scenarios).resolve())
    return config, load_scenarios(config.scenarios_file)


def _target_note(base_url: str) -> str:
    try:
        check_url(base_url)
    except TargetNotAllowed:
        return "loopback değil; run bu hedefi reddeder"
    return "loopback (run için izinli; çalıştırmada ad çözümlemesi de denetlenir)"


def _print_telemetry(outcome: RunOutcome, telemetry: TelemetryRecorder | None) -> None:
    if telemetry is None:
        return
    if outcome.telemetry_path is None:
        print(f"UYARI: telemetri kaydedilemedi (sonuçlar etkilenmedi): {outcome.telemetry_error}", file=sys.stderr)
        return
    s = telemetry.summary()
    collect = s["collect_ms"]
    cost = f", toplama medyan {collect['median']:.2f} ms / en çok {collect['max']:.2f} ms" if collect else ""
    unavailable = ", ".join(s["unavailable"]) or "yok"
    errors = ", ".join(f"{k} {v}" for k, v in s["probe_errors"].items()) or "yok"
    print(f"  telemetri: {outcome.telemetry_path}")
    print(f"             örnek {s['samples']} (aralık {telemetry.interval_ms} ms, atlanan {s['missed_slots']}){cost}; "
          f"okunamayan grup: {unavailable}; okuma hatası: {errors}")


def _print_outcome(outcome: RunOutcome) -> None:
    s = summarize(outcome.results)
    errors = ", ".join(f"{k} {v}" for k, v in sorted(s["transport_errors"].items())) or "yok"
    print(f"Çalıştırma: {outcome.run_id}  durum: {outcome.status}")
    print(f"  istekler: planlanan {outcome.planned_requests}, tamamlanan {s['total']} "
          f"(ısınma {s['warmup']}, ölçüm {s['measured']})")
    print(f"  HTTP yanıtı: beklenen durum {s['http_ok']}, beklenmeyen durum {s['http_unexpected']}; "
          f"taşıma hatası: {errors}")
    if s["duration_ms_median"] is not None:
        print(f"  ölçüm duration_ms: medyan {s['duration_ms_median']:.2f}, "
              f"en az {s['duration_ms_min']:.2f}, en çok {s['duration_ms_max']:.2f}")
    print(f"  sonuçlar: {outcome.csv_path}")
    print(f"            {outcome.json_path}")
    if not outcome.completed:
        print(f"UYARI: çalıştırma tamamlanmadı ({outcome.status}: {outcome.stop_reason}). {outcome.message}. "
              f"Kayıtlı sonuçlar kısmidir (.partial).", file=sys.stderr)


def _run(args: argparse.Namespace, config: LabConfig, scenarios: list[Scenario]) -> int:
    try:
        telemetry = _telemetry_recorder(args)
        outcome = execute_run(
            config, scenarios, config_path=Path(args.config).resolve(), target_label=args.target_label,
            telemetry=telemetry,
        )
    except PreflightError as exc:
        print(f"Çalıştırma reddedildi, hiçbir istek gönderilmedi: {exc}", file=sys.stderr)
        return EXIT_REJECTED
    except StorageError as exc:
        print(f"Sonuçlar kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    _print_outcome(outcome)
    _print_telemetry(outcome, telemetry)
    return _EXIT_BY_STATUS[outcome.status]


def _fmt_ms(entry: dict) -> str:
    if entry["value"] is not None:
        return f"{entry['value']:.2f}"
    if entry["status"] == "insufficient_sample":
        return f"yetersiz örneklem (en az {entry['min_samples']})"
    return "veri yok"


def _print_analysis(document: dict, path: Path) -> None:
    a = document["analysis"]
    run, overall = a["run"], a["overall"]
    status = run["execution"]["status"] or "bilinmiyor"
    print(f"Analiz: {run['run_id']}  durum: {status}{'  (kısmi)' if run['partial'] else ''}")
    req, m = overall["requests"], overall["measured"]
    print(f"  istekler: toplam {req['total']} (ısınma {req['warmup']}, ölçüm {req['measured']}); ölçümde başarılı "
          f"{m['successful']}, HTTP hatası {m['http_errors']}, taşıma hatası {m['transport_errors']}")
    rt = overall["response_time_ms"]
    print(f"  yanıt süresi (ms, n={rt['n']}): " + ", ".join(
        f"{label} {_fmt_ms(rt[label])}" for label in ("median", "p90", "p95", "p99")))
    tp = overall["throughput"]
    print("  throughput: " + (f"{tp['requests_per_second']:.2f} istek/sn" if tp["status"] == "ok"
                              else f"hesaplanmadı ({tp['reason']})"))
    codes = sorted({w["code"] for w in a["warnings"]})
    print(f"  uyarılar: {len(a['warnings'])}" + (f" ({', '.join(codes)})" if codes else ""))
    print(f"  çıktı: {path}")


def _analyze(args: argparse.Namespace) -> int:
    try:
        params = AnalysisParams(seed=args.seed, bootstrap_resamples=args.bootstrap_resamples,
                                confidence=args.confidence, min_tail_samples=args.min_tail_samples)
    except AnalysisError as exc:
        print(f"Geçersiz analiz parametresi: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.results_dir:
        results_dir = Path(args.results_dir)
    else:
        try:
            results_dir = load_config(args.config).output_dir
        except ConfigError as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            return EXIT_ERROR
    try:
        run = load_run(results_dir, args.run_id)
    except (StorageError, InvalidRunId) as exc:
        print(f"Analiz edilemedi: {exc}", file=sys.stderr)
        return EXIT_ERROR

    output = Path(args.output) if args.output else default_output_path(results_dir, run)
    if output.exists():  # bootstrap hesaplanmadan önce; yazımda yeniden denetlenir
        print(f"Analiz dosyası zaten var, üzerine yazılmaz: {output}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    document = build_document(run, params)
    try:
        write_document(document, output)
    except AnalysisOutputError as exc:
        print(f"Analiz kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    _print_analysis(document, output)
    return EXIT_OK


def _print_plan_summary(manifest: SyntheticManifest, manifest_sha256: str, plan: SyntheticPlan) -> None:
    print(f"Sentetik deney: {manifest.experiment_id}  (dataset_kind: {manifest.dataset_kind}, seed: {manifest.seed})")
    print(f"  manifest_sha256: {manifest_sha256}")
    print(f"  plan_sha256:     {plan.sha256}  ({len(plan.entries)} istek, istemci zaman aşımı "
          f"{manifest.timeout_seconds:g} sn)")
    for s in manifest.scenarios:
        expected = Counter(e.expected_outcome for e in plan.route(s.name))
        onset = f" (ilk {s.fault.onset_after} istek normal)" if s.fault.onset_after else ""
        print(f"  {s.name}\t{s.method} {s.path}\tısınma {s.warmup_repetitions}, ölçüm {s.repetitions}\t"
              f"hata: {s.fault.type}{onset}\tbeklenen: " + ", ".join(f"{k} {v}" for k, v in sorted(expected.items())))
    print(f"  en kısa süre (tahmini): {estimated_min_duration_seconds(manifest, plan):.1f} sn")
    forecast = guard_forecast(plan, manifest.limits)
    if forecast:
        print(f"UYARI: {forecast}; çalıştırma güvenlik sınırıyla durabilir (manifestte limits ile ayarlanabilir).",
              file=sys.stderr)


def _synthetic(args: argparse.Namespace) -> int:
    if args.synthetic_command == "run":
        return _synthetic_run(args)
    try:
        manifest, manifest_sha256, plan = prepare_synthetic(args.manifest)
    except ManifestError as exc:
        print(f"Manifest geçersiz: {exc}", file=sys.stderr)
        return EXIT_ERROR
    _print_plan_summary(manifest, manifest_sha256, plan)
    if args.synthetic_command == "plan" and args.output:
        document = {"format": "hgs2-lab-synthetic-plan", "manifest_sha256": manifest_sha256,
                    "plan_sha256": plan.sha256, **plan.to_dict()}  # zaman damgası yok: aynı manifest = aynı dosya
        try:
            write_document(document, args.output)
        except AnalysisOutputError as exc:
            print(f"Plan kaydedilemedi: {exc}", file=sys.stderr)
            return EXIT_STORAGE_ERROR
        print(f"  plan dosyası: {args.output}")
    return EXIT_OK


def _synthetic_run(args: argparse.Namespace) -> int:
    try:
        telemetry = _telemetry_recorder(args)
        result = run_synthetic_experiment(args.manifest, results_dir=Path(args.results_dir), run_id=args.run_id,
                                          telemetry=telemetry)
    except ManifestError as exc:
        print(f"Manifest geçersiz: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except PreflightError as exc:
        print(f"Sentetik deney reddedildi, hiçbir istek gönderilmedi: {exc}", file=sys.stderr)
        return EXIT_REJECTED
    except (StorageError, AnalysisOutputError) as exc:
        print(f"Sonuçlar kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR

    _print_outcome(result.run)
    _print_telemetry(result.run, telemetry)
    labels = result.labels
    summary = labels["summary"]
    print(f"Sentetik deney: {labels['experiment']['experiment_id']}  (dataset_kind: synthetic; gerçek HGS2 ölçümü değildir)")
    print(f"  etiketler: planlanan {summary['planned']}, doğrulanan {summary['confirmed']}, çelişen "
          f"{summary['contradicted']}, yürütülmeyen {summary['not_executed']}")
    if result.valid:
        print("  deney geçerli: evet")
    else:
        print("  deney geçerli: HAYIR (" + ", ".join(r["code"] for r in labels["verdict"]["reasons"]) + ")")
    print(f"  etiket dosyası:        {result.labels_path}")
    print(f"  sunucu olayları:       {result.server_events_path}")
    print(f"  analiz: hgs2-lab analyze --results-dir {args.results_dir} --run-id {result.run.run_id}")
    if not result.run.completed:
        return _EXIT_BY_STATUS[result.run.status]
    return EXIT_OK if result.valid else EXIT_SYNTHETIC_INVALID


def _campaign(args: argparse.Namespace) -> int:
    if args.campaign_command == "verify":
        try:
            report = verify_campaign(args.campaign_dir)
        except CampaignError as exc:
            print(f"Katalog okunamadı: {exc}", file=sys.stderr)
            return EXIT_ERROR
        catalog = report["catalog"]
        print(f"Kampanya: {catalog['campaign_id']}  deney: {len(catalog['experiments'])}  "
              f"catalog_sha256: {report['catalog_sha256']}")
        if report["ok"]:
            print("  doğrulama: sorun yok (dosya özetleri, sonuçlar, etiketler ve plan tutarlı)")
            return EXIT_OK
        for issue in report["issues"]:
            print(f"  [{issue['experiment_id'] or 'katalog'}] {issue['rule']}: {issue['message']}", file=sys.stderr)
        print(f"  doğrulama: {len(report['issues'])} sorun", file=sys.stderr)
        return EXIT_ERROR

    try:
        campaign, manifest_sha256 = load_campaign(args.manifest)
    except CampaignError as exc:
        print(f"Kampanya manifesti geçersiz: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.campaign_command == "validate":
        print(f"Kampanya: {campaign.campaign_id}  (dataset_kind: synthetic; gerçek HGS2 ölçümü değildir)")
        print(f"  manifest_sha256:      {manifest_sha256}")
        print(f"  campaign_plan_sha256: {campaign.plan_sha256}")
        print(f"  deney: {len(campaign.experiments)} (plan x seed), istek: "
              f"{sum(len(e.plan.entries) for e in campaign.experiments)}, seeds: {list(campaign.seeds)}")
        for e in campaign.experiments:
            faults = ",".join(sorted({s.fault.type for s in e.manifest.scenarios}))
            print(f"  {e.experiment_id}\tgroup={e.group}\tistek={len(e.plan.entries)}\thatalar={faults}")
        return EXIT_OK

    try:
        outcome = run_campaign(args.manifest, output_dir=Path(args.output_dir))
    except CampaignRejected as exc:
        print(f"Kampanya reddedildi, hiçbir deney çalıştırılmadı: {exc}", file=sys.stderr)
        return EXIT_REJECTED
    except (AnalysisOutputError, OSError) as exc:
        print(f"Kampanya dosyaları yazılamadı: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    catalog = outcome.catalog
    print(f"Kampanya: {catalog['campaign_id']}  durum: {catalog['status']}  "
          f"deney: {catalog['summary']['experiments']}, geçerli: {catalog['summary']['valid']}, "
          f"geçersiz: {catalog['summary']['invalid']}  {catalog['summary']['by_status']}")
    for e in catalog["experiments"]:
        if not e["valid"]:
            detail = e["error"]["type"] if e["error"] else ",".join(e["invalid_reasons"])
            print(f"  GEÇERSİZ {e['experiment_id']}: {e['status']} ({detail})")
    print(f"  katalog: {outcome.catalog_path}")
    if outcome.interrupted:
        return EXIT_INTERRUPTED
    return EXIT_OK if outcome.all_valid else EXIT_SYNTHETIC_INVALID


def _dataset_features(args: argparse.Namespace) -> int:
    try:
        document = write_feature_table(args.campaign_dir, args.dataset, args.output_dir, policy=args.policy)
    except (FeatureTableError, CampaignError) as exc:
        print(f"Özellik tablosu oluşturulamadı: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except AnalysisOutputError as exc:
        print(f"Özellik tablosu kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    table = document["table"]
    print(f"Özellik tablosu: kampanya {table['dataset']['campaign_id']}  dataset_id {table['dataset']['dataset_id'][:16]}…  "
          f"politika {table['policy']['name']}  content_sha256={document['content_sha256']}")
    for split in ("train", "validation", "test"):
        c = table["counts"][split]
        print(f"  {split:10s} deney={c['experiments']} satır={c['rows']} (dışarıda bırakılan ısınma {c['warmup_excluded']})")
    for name, info in table["files"].items():
        print(f"  {name}: {info['rows']} satır, sha256 {info['sha256']}")
    print(f"  çıktı: {args.output_dir}")
    return EXIT_OK


def _fmt_ratio(entry: dict) -> str:
    return f"{entry['value']:.3f} ({entry['numerator']}/{entry['denominator']})" if entry["value"] is not None         else f"tanımsız ({entry['status']})"


def _detect(args: argparse.Namespace) -> int:
    if Path(args.output).exists():
        print(f"Değerlendirme dosyası zaten var, üzerine yazılmaz: {args.output}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    try:
        document = write_evaluation(args.features_dir, args.output)
    except (DetectionError, CalibrationError) as exc:
        print(f"Dedektör çalıştırılamadı: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except AnalysisOutputError as exc:
        print(f"Değerlendirme kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    ev = document["evaluation"]
    cal, base = ev["calibration"], ev["calibration"]["baseline"]
    print(f"Robust Z-score ({ev['detector']['version']}): girdi {ev['detector']['input_fields']}, eşik z > "
          f"{ev['detector']['threshold']}  content_sha256={document['content_sha256']}")
    print(f"  kalibrasyon (train normal): n={base['n']}, medyan {base['median_duration_ms']:.3f} ms, "
          f"MAD(ln) {base['mad_log']:.4f}, durum {base['status']}")
    if base["status"] == BASELINE_DEGENERATE:
        print(f"UYARI: {cal['warning']}", file=sys.stderr)
    for split, s in ev["splits"].items():
        rl, ep = s["request_level"], s["episodes"]
        delay = ep["request_detection_delay"]
        print(f"  {split:10s} skorlanan {s['scored_rows']}: precision {_fmt_ratio(rl['precision'])}, recall "
              f"{_fmt_ratio(rl['recall'])}, FPR {_fmt_ratio(rl['false_positive_rate'])}; epizot "
              f"{_fmt_ratio(ep['detection_rate'])}, istek cinsinden tespit gecikmesi medyanı "
              + (f"{delay['median']}" if delay["median"] is not None else "yok")
              + f"; operasyonel hata {s['operational_failures']['rows']} (gecikme metriklerine dahil değil)")
    for item in ev["limitations"]:
        if "temsil edilmeyen" in item or "test bölümündeki" in item:
            print(f"  not: {item}")
    print(f"  çıktı: {args.output}")
    return EXIT_OK


def _junit(args: argparse.Namespace) -> int:
    if Path(args.output).exists():
        print(f"Sınıflandırma dosyası zaten var, üzerine yazılmaz: {args.output}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    expectations, source = None, None
    if args.expectations:  # geçersiz beklenti dosyası sessizce yok sayılmaz: hiçbir şey yazılmaz
        try:
            expectations, source = load_expectations(args.expectations)
        except ExpectationsError as exc:
            print(f"Beklenti dosyası kullanılamadı: {exc}", file=sys.stderr)
            return EXIT_ERROR
    mapping = None
    if args.scenario_map:  # geçersiz eşleme dosyası sessizce yok sayılmaz ve kısmen kullanılmaz: hiçbir şey yazılmaz
        try:
            mapping = load_mapping(args.scenario_map)
        except MappingError as exc:
            print(f"Eşleme dosyası kullanılamadı: {exc}", file=sys.stderr)
            return EXIT_ERROR
    reports, errors, duplicates, given = parse_reports(args.report, dataset_kind=args.dataset_kind)
    document = build_junit_analysis_document(reports, errors, duplicates=duplicates, files_given=given,
                                             expectations=expectations, expectations_source=source,
                                             scenario_mapping=mapping)
    try:
        write_document(document, args.output)
    except AnalysisOutputError as exc:
        print(f"Sınıflandırma kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    summary = document["classification"]["summary"]
    print(f"JUnit sınıflandırma ({document['classification']['classifier_version']}): {summary['files_parsed']} rapor, "
          f"{summary['records']} test, dataset_kind={args.dataset_kind}  content_sha256={document['content_sha256']}")
    print("  kaynak sonuç: " + (", ".join(f"{k}={v}" for k, v in summary["by_test_outcome"].items()) or "yok"))
    print("  sınıflar:     " + (", ".join(f"{c}={summary['by_classification'][c]}" for c in CLASSES
                                         if summary["by_classification"][c]) or "yok"))
    print(f"  inceleme gerektiren: {summary['requires_review']}")
    matching = summary["expectation_matching"]
    print(f"  senaryo kimliği: {matching['records_with_scenario_id']} kayıtta var, "
          f"{matching['records_without_scenario_id']} kayıtta yok"
          + ("; eşleşme: " + (", ".join(f"{k}={v}" for k, v in matching["by_match_status"].items()) or "yok")
             if matching["requested"] else "; beklenti dosyası verilmedi (beklentisiz analiz)"))
    resolution = summary["scenario_resolution"]
    if mapping is not None:
        print("  senaryo çözümlemesi: " + ", ".join(f"{k}={v}" for k, v in resolution["by_status"].items() if v)
              + f"; inceleme gerektiren {resolution['requires_review']}")
        print("  beklenti uygunluğu: " + ", ".join(f"{k}={v}" for k, v in resolution["by_decision_basis"].items())
              + "; değerlendirme: " + ", ".join(f"{k}={v}" for k, v in resolution["by_expectation_assessment"].items()))
        if mapping.conflicts:
            print(f"UYARI: farklı senaryolara eşlenmiş testler (seçilmedi): {len(mapping.conflicts)}", file=sys.stderr)
    for error in errors:
        print(f"Reddedilen rapor: {error.source_file}: {error.code}: {error.message}", file=sys.stderr)
    for dup in duplicates:
        print(f"UYARI: {dup['source_file']} içeriği {dup['duplicate_of']} ile aynı; yeniden işlenmedi.", file=sys.stderr)
    if summary["possible_duplicate_tests"]:
        print(f"UYARI: birden fazla kayıtta görülen test: {len(summary['possible_duplicate_tests'])} "
              "(birleştirilmedi; belgede possible_duplicate_tests)", file=sys.stderr)
    if source is not None and source.get("registry", {}).get("conflicts"):
        print(f"UYARI: birden fazla etkin beklentisi olan senaryolar (eşleştirilmedi): "
              f"{', '.join(sorted(source['registry']['conflicts']))}", file=sys.stderr)
    print(f"  çıktı: {args.output}")
    return EXIT_ERROR if errors else EXIT_OK


def _readiness(args: argparse.Namespace) -> int:
    if args.output and Path(args.output).exists():
        print(f"Hazırlık raporu zaten var, üzerine yazılmaz: {args.output}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    document = run_readiness(args.report, expectations_path=args.expectations, scope=args.scope,
                             mapping_path=args.scenario_map)
    if args.output:
        try:
            write_document(document, args.output)
        except AnalysisOutputError as exc:
            print(f"Hazırlık raporu kaydedilemedi: {exc}", file=sys.stderr)
            return EXIT_STORAGE_ERROR
    print(f"Hazırlık ({document['scope']} kapsamı): {document['status']}")
    for check in document["checks"]:
        print(f"  [{check['status']:4}] {check['id']}: {check['message']}")
    print(f"  not: {document['statement']}")
    if args.output:
        print(f"  çıktı: {args.output}")
    return EXIT_ERROR if document["status"] == READINESS_BLOCKED else EXIT_OK


def _ingest(args: argparse.Namespace) -> int:
    if Path(args.output).exists():
        print(f"Sınıflandırma dosyası zaten var, üzerine yazılmaz: {args.output}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    path = Path(args.file)
    try:
        raw = path.read_bytes()
        result = parse_ingestion(json.loads(raw.decode("utf-8")))
        expectations, source = load_expectations(args.expectations) if args.expectations else (None, None)
    except FileNotFoundError:
        print(f"Alım dosyası bulunamadı: {path.name}", file=sys.stderr)
        return EXIT_ERROR
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print(f"Alım dosyası okunamadı veya geçerli UTF-8 JSON değil: {path.name}", file=sys.stderr)
        return EXIT_ERROR
    except (IngestionError, ExpectationsError) as exc:
        print(f"Alım yapılamadı: {exc}", file=sys.stderr)
        return EXIT_ERROR
    document = build_ingestion_document(result, expectations=expectations, expectations_source=source,
                                        source={"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
    try:
        write_document(document, args.output)
    except AnalysisOutputError as exc:
        print(f"Sınıflandırma kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    summary = document["classification"]["summary"]
    ingestion = summary["ingestion"]
    print(f"Alım ({ingestion['batch_id']}, {ingestion['dataset_kind']}): kabul {ingestion['accepted']}, ret "
          f"{ingestion['rejected']}, tekrar {ingestion['duplicates']}; incelenmemiş etiket "
          f"{ingestion['labels_withheld_unreviewed']}  content_sha256={document['content_sha256']}")
    print("  sınıflar: " + (", ".join(f"{c}={summary['by_classification'][c]}" for c in CLASSES
                                      if summary["by_classification"][c]) or "yok"))
    for item in result.rejected:
        print(f"Reddedilen girdi #{item['index']}: {item['reason']}", file=sys.stderr)
    print(f"  çıktı: {args.output}")
    return EXIT_ERROR if result.rejected else EXIT_OK


def _expectations(args: argparse.Namespace) -> int:
    try:
        registry = load_registry(args.file)
    except ExpectationsError as exc:
        print(f"Beklenti dosyası geçersiz: {Path(args.file).name}", file=sys.stderr)
        for issue in exc.issues:
            print(f"  - {issue}", file=sys.stderr)
        return EXIT_ERROR
    summary = registry.summary()
    if args.expectations_command == "validate":
        print(f"Geçerli: {summary['source']['file']}  registry_id={summary['registry_id'] or '-'}  "
              f"content_sha256={summary['content_sha256']}")
        print(f"  beklenti {summary['expectations']} (senaryo {summary['scenarios']}), kanıt {summary['evidence']}; "
              "durum: " + ", ".join(f"{k}={v}" for k, v in summary["by_status"].items()))
        for scenario, ids in summary["conflicts"].items():
            print(f"UYARI: '{scenario}' için birden fazla etkin beklenti: {', '.join(ids)} (eşleştirilmez)",
                  file=sys.stderr)
        if summary["unused_evidence"]:
            print(f"UYARI: kullanılmayan kanıt: {', '.join(summary['unused_evidence'])}", file=sys.stderr)
        return EXIT_OK
    shown = [e for e in registry.expectations if args.scenario in (None, e.scenario_id)]
    if not shown:
        print(f"Bu senaryo için beklenti yok: {args.scenario}", file=sys.stderr)
        return EXIT_ERROR
    for exp in shown:
        e = exp.expected
        issues = registry.assessments.get(exp.expectation_id, ())
        print(f"{exp.scenario_id}\t{exp.expectation_id} v{exp.version}\t{exp.status}\tkapsam={exp.scope}\t"
              f"http={list(e.status_codes) or '?'} iş={list(e.business_outcomes) or '?'} "
              f"taşıma={e.expected_transport or '?'} kaynak_sonuç={e.expected_test_outcome or '?'}")
        for eid in exp.evidence_ids:
            ref = registry.evidence[eid]
            print(f"    kanıt {eid}: {ref.source_type} {ref.source_ref}" + (f" [{ref.location}]" if ref.location else "")
                  + f" {ref.review_status} {ref.relation} {','.join(ref.supports)}")
        if not exp.evidence_ids:
            print("    kanıt: yok")
        if issues:
            print(f"    kanıt yeterliliği: {', '.join(issues)}")
    return EXIT_OK


def _scenario_map(args: argparse.Namespace) -> int:
    try:
        mapping = load_mapping(args.file)
    except MappingError as exc:
        print(f"Eşleme dosyası geçersiz: {Path(args.file).name}", file=sys.stderr)
        for issue in exc.issues:
            print(f"  - {issue}", file=sys.stderr)
        return EXIT_ERROR
    summary = mapping.summary()
    print(f"Geçerli: {summary['source']['file']}  mapping_set_id={summary['mapping_set_id'] or '-'}  "
          f"content_sha256={summary['content_sha256']}")
    print(f"  eşleme {summary['mappings']} (test {summary['tests']}, etkin senaryo {summary['scenarios']}); durum: "
          + ", ".join(f"{k}={v}" for k, v in summary["by_status"].items()))
    for key, ids in summary["conflicts"].items():
        print(f"UYARI: '{key}' farklı senaryolara eşlenmiş: {', '.join(ids)} (seçilmez)", file=sys.stderr)
    return EXIT_OK


def _results(args: argparse.Namespace) -> int:
    if Path(args.output).exists():
        print(f"Sınıflandırma dosyası zaten var, üzerine yazılmaz: {args.output}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    try:
        run = load_run(args.results_dir, args.run_id)
        expectations, source = load_expectations(args.expectations) if args.expectations else (None, None)
        dataset_kind = resolve_dataset_kind(run, args.dataset_kind)
    except (StorageError, InvalidRunId, ExpectationsError, ValueError) as exc:
        print(f"Sınıflandırılamadı: {exc}", file=sys.stderr)
        return EXIT_ERROR
    document = build_run_document(run, dataset_kind=dataset_kind, expectations=expectations,
                                  expectations_source=source)
    try:
        write_document(document, args.output)
    except AnalysisOutputError as exc:
        print(f"Sınıflandırma kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    content = document["classification"]
    summary, info = content["summary"], content["sources"][0]
    print(f"Sonuç sınıflandırma ({content['classifier_version']}): çalıştırma {run.run_id}"
          f"{' (kısmi)' if run.partial else ''}, {summary['records']} ölçüm isteği (ısınma "
          f"{info['warmup_requests_skipped']} atlandı), dataset_kind={dataset_kind}  "
          f"content_sha256={document['content_sha256']}")
    print("  sınıflar: " + (", ".join(f"{c}={summary['by_classification'][c]}" for c in CLASSES
                                      if summary["by_classification"][c]) or "yok"))
    print(f"  inceleme gerektiren: {summary['requires_review']}  beklenti kaynağı: "
          + ", ".join(f"{k}={v}" for k, v in info["expected_result_sources"].items()))
    if "expectation_matches" in info:
        registry = source["registry"]
        print(f"  beklenti sözleşmesi: {registry['registry_id'] or '(kimliksiz)'} content_sha256="
              f"{registry['content_sha256']}  eşleşme: "
              + ", ".join(f"{k}={v}" for k, v in info["expectation_matches"].items()))
        if registry["conflicts"]:
            print(f"UYARI: birden fazla etkin beklentisi olan senaryolar (eşleştirilmedi): "
                  f"{', '.join(sorted(registry['conflicts']))}", file=sys.stderr)
    elif args.expectations:
        print("UYARI: beklenti dosyası eski biçimde (sürüm 1); doğrulama durumu ve kanıt referansı yok.",
              file=sys.stderr)
    if not info["response_parsing_available"]:
        print("UYARI: metadata'da yanıt ayrıştırma özeti yok (eski dosya); iş sonucu bilgisi yok.", file=sys.stderr)
    if info["unused_expectations"]:
        print(f"UYARI: çalıştırmada bulunmayan senaryo beklentileri: {', '.join(info['unused_expectations'])}",
              file=sys.stderr)
    print(f"  çıktı: {args.output}")
    return EXIT_OK


def _dataset(args: argparse.Namespace) -> int:
    if args.dataset_command == "features":
        return _dataset_features(args)
    try:
        ratios = parse_ratios(args.ratios)
        document = build_dataset_document(args.campaign_dir, split_seed=args.split_seed, ratios=ratios,
                                          invalid_policy=args.invalid_policy)
    except (DatasetError, CampaignError) as exc:
        print(f"Veri seti oluşturulamadı: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        write_document(document, args.output)
    except AnalysisOutputError as exc:
        print(f"Veri seti kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    data = document["dataset"]
    print(f"Veri seti: kampanya {data['source']['campaign_id']}  split_seed={data['parameters']['split_seed']}  "
          f"politika={data['invalid_experiments']['policy']}  content_sha256={document['content_sha256']}")
    for name, split in data["splits"].items():
        c = split["counts"]
        print(f"  {name:10s} grup={len(split['groups'])} deney={c['experiments']} ölçüm isteği={c['measured_requests']} "
              f"sınıflar={c['classification']} regresyon={c['delay_regression_samples']}")
    print(f"  dışarıda bırakılan: {len(data['invalid_experiments']['excluded'])}  "
          f"bütünlük: {'geçti' if data['integrity']['passed'] else 'UYARI'}  uyarılar: "
          + (", ".join(sorted({w['code'] for w in data['warnings']})) or "yok"))
    print(f"  çıktı: {args.output}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "telemetry_interval_ms", None) is not None and not args.telemetry:
        parser.error("--telemetry-interval-ms yalnızca --telemetry ile kullanılabilir")
    if args.command == "analyze":  # senaryo dosyası gerekmez; ağ erişimi yok
        return _analyze(args)
    if args.command == "synthetic":
        return _synthetic(args)
    if args.command == "campaign":
        return _campaign(args)
    if args.command == "dataset":
        return _dataset(args)
    if args.command == "detect":
        return _detect(args)
    if args.command == "junit":
        return _junit(args)
    if args.command == "results":
        return _results(args)
    if args.command == "expectations":
        return _expectations(args)
    if args.command == "readiness":
        return _readiness(args)
    if args.command == "ingest":
        return _ingest(args)
    if args.command == "scenario-map":
        return _scenario_map(args)

    try:
        config, scenarios = _load(args)
    except (ConfigError, ScenarioError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.command == "run":
        return _run(args, config, scenarios)
    if args.command == "validate":
        print(f"Tamam: base_url={config.base_url}, {len(scenarios)} senaryo geçerli.")
        print(f"  senaryo dosyası: {config.scenarios_file}")
        print(f"  çıktı dizini:    {config.output_dir}")
        print(f"  hedef:           {_target_note(config.base_url)}")
    else:
        for s in scenarios:
            expected = ",".join(map(str, s.expected_status)) or "2xx"
            print(f"{s.name}\t{s.method} {s.path}\tx{s.repetitions}\tbeklenen: {expected}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
