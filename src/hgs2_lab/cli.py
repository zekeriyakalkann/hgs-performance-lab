"""Komut satırı giriş noktası.

Komutlar:
* validate: yapılandırma ve senaryoları doğrular (istek göndermez).
* list:     senaryoları listeler (istek göndermez).
* run:      senaryoları YALNIZCA loopback hedefe karşı çalıştırır ve sonuçları kaydeder.
* analyze:  kaydedilmiş bir çalıştırmanın CSV/JSON dosyalarını çevrimdışı analiz eder (istek göndermez).
* synthetic validate|plan|run: uygulamanın kendi yerel sentetik sunucusuyla planlı hata deneyleri
  (gerçek HGS2 değildir; bkz. synthetic.py).
* campaign validate|run|verify: toplu sentetik deney kampanyası ve kataloğu (bkz. campaign.py).
* dataset build: doğrulanmış bir kampanya kataloğundan train/validation/test veri seti manifesti (bkz. dataset.py).
* dataset features: doğrulanmış veri setinden deterministik özellik tablosu; features.csv + labels.csv + manifest
  (bkz. features.py). 0 = yazıldı, 1 = doğrulama hatası, 5 = çıktı dizini boş değil / yazılamadı.

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
from .models import InvalidRunId
from .reader import load_run
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

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_REJECTED = 3
EXIT_ABORTED = 4
EXIT_STORAGE_ERROR = 5
EXIT_SYNTHETIC_INVALID = 6
EXIT_INTERRUPTED = 130

_EXIT_BY_STATUS = {STATUS_COMPLETED: EXIT_OK, STATUS_ABORTED: EXIT_ABORTED, STATUS_INTERRUPTED: EXIT_INTERRUPTED}


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
        outcome = execute_run(
            config, scenarios, config_path=Path(args.config).resolve(), target_label=args.target_label
        )
    except PreflightError as exc:
        print(f"Çalıştırma reddedildi, hiçbir istek gönderilmedi: {exc}", file=sys.stderr)
        return EXIT_REJECTED
    except StorageError as exc:
        print(f"Sonuçlar kaydedilemedi: {exc}", file=sys.stderr)
        return EXIT_STORAGE_ERROR
    _print_outcome(outcome)
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
        result = run_synthetic_experiment(args.manifest, results_dir=Path(args.results_dir), run_id=args.run_id)
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
    args = build_parser().parse_args(argv)
    if args.command == "analyze":  # senaryo dosyası gerekmez; ağ erişimi yok
        return _analyze(args)
    if args.command == "synthetic":
        return _synthetic(args)
    if args.command == "campaign":
        return _campaign(args)
    if args.command == "dataset":
        return _dataset(args)

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
