"""Komut satırı giriş noktası.

Çıkış kodları: 0 başarılı, 1 yapılandırma/senaryo hatası, 2 argparse kullanım
hatası, 3 `run` komutu bu sürümde devre dışı.

İlk sürümde yalnızca yapılandırma/senaryo doğrulama ve listeleme vardır.
`run` komutu bilinçli olarak devre dışıdır (HGS2'ye istek göndermez).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .config import ConfigError, load_config
from .scenarios import ScenarioError, load_scenarios

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_RUN_DISABLED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hgs2-lab", description="HGS2 performans test aracı")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("validate", "Yapılandırma ve senaryo dosyalarını doğrula"),
        ("list", "Tanımlı senaryoları listele"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", default="configs/config.json", help="Yapılandırma dosyası (varsayılan: %(default)s)")

    sub.add_parser("run", help="Senaryoları çalıştır (bu sürümde devre dışı)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "run":
        print("'run' bu sürümde etkin değil: HGS2'ye istek gönderimi henüz uygulanmadı.", file=sys.stderr)
        return EXIT_RUN_DISABLED

    try:
        config = load_config(args.config)
        scenarios = load_scenarios(config.scenarios_file)
    except (ConfigError, ScenarioError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.command == "validate":
        print(f"Tamam: base_url={config.base_url}, {len(scenarios)} senaryo geçerli.")
        print(f"  senaryo dosyası: {config.scenarios_file}")
        print(f"  çıktı dizini:    {config.output_dir}")
    else:
        for s in scenarios:
            expected = ",".join(map(str, s.expected_status)) or "2xx"
            print(f"{s.name}\t{s.method} {s.path}\tx{s.repetitions}\tbeklenen: {expected}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
