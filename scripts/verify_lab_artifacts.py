"""Lab Artifacts SHA-256 manifest doğrulaması (salt okunur; ağ ve veritabanı erişimi yok).

projects/lab-artifacts altındaki her `*SHA256SUMS*.txt` ve `MANIFEST*.sha256` dosyasını okur. Manifestler Windows
ters eğik çizgili yollar ve farklı kök dizinler kullanır; her girdi önce manifestin dizinine, sonra (lab-artifacts
köküne kadar) üst dizinlerine göre çözülür.

Çıkış kodu: 0 = uyuşmazlık yok; 1 = en az bir uyuşmazlık. Depoda bulunmayan dosyalar (bilinçli dışlanan ham
çıktılar) uyuşmazlık sayılmaz, ayrı raporlanır.

Kullanım (depo kökünden):  python scripts/verify_lab_artifacts.py [KÖK]
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+?)\r?$")
MANIFEST_NAME = re.compile(r"(SHA256SUMS.*\.txt|MANIFEST.*\.sha256)$")
DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "projects" / "lab-artifacts"


def verify(manifest: Path, root: Path) -> tuple[int, list[str], int]:
    bases = [manifest.parent] + [a for a in manifest.parent.parents if a == root or root in a.parents]
    ok, mismatched, missing = 0, [], 0
    for raw in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LINE.match(raw)
        if not match:
            continue  # yorum veya boş satır
        rel = match.group(2).replace(chr(92), "/").lstrip("*")
        target = next((base / rel for base in bases if (base / rel).is_file()), None)
        if target is None:
            missing += 1
        elif hashlib.sha256(target.read_bytes()).hexdigest() == match.group(1).lower():
            ok += 1
        else:
            mismatched.append(rel)
    return ok, mismatched, missing


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_ROOT
    manifests = sorted(p for p in root.rglob("*") if p.is_file() and MANIFEST_NAME.search(p.name))
    if not manifests:
        print(f"manifest bulunamadı: {root}")
        return 1
    total_bad = 0
    for manifest in manifests:
        ok, mismatched, missing = verify(manifest, root)
        total_bad += len(mismatched)
        print(f"{manifest.relative_to(root).as_posix()}\n    OK={ok}  UYUSMAZLIK={len(mismatched)}  DEPODA_YOK={missing}")
        for rel in mismatched:
            print(f"    UYUSMAZLIK: {rel}")
    print("SONUC:", "BASARILI" if total_bad == 0 else f"{total_bad} UYUSMAZLIK")
    return 0 if total_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
