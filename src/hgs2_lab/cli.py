"""Komut satırı giriş noktası.

Komutlar:
* validate: yapılandırma ve senaryoları doğrular (istek göndermez).
* list:     senaryoları listeler (istek göndermez).
* run:      senaryoları YALNIZCA loopback hedefe karşı çalıştırır ve sonuçları kaydeder.

Çıkış kodları:
  0   başarılı (run: tüm planlanan istekler yapıldı)
  1   yapılandırma/senaryo hatası
  2   komut satırı kullanım hatası (argparse)
  3   run ön kontrolde reddedildi; hiçbir istek gönderilmedi (hedef, bütçe, dosya çakışması)
  4   run güvenlik sınırıyla durduruldu; kısmi sonuçlar `.partial` dosyalarında
  5   run sonuçları kaydedilemedi
  130 run kullanıcı tarafından (Ctrl+C) durduruldu; kısmi sonuçlar `.partial` dosyalarında
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path

from .config import ConfigError, LabConfig, load_config
from .execution import (
    STATUS_ABORTED,
    STATUS_COMPLETED,
    STATUS_INTERRUPTED,
    PreflightError,
    RunOutcome,
    execute_run,
    summarize,
)
from .scenarios import Scenario, ScenarioError, load_scenarios
from .storage import StorageError
from .target_guard import TargetNotAllowed, check_url

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REJECTED = 3
EXIT_ABORTED = 4
EXIT_STORAGE_ERROR = 5
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

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
