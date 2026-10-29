"""Dış hedef süreç adı kuralları (N12; ağ ve soket kodu içermez: config.py ve analiz modülleri güvenle içe aktarır).

`target_process`, hedef portu Lab süreci dışında bir süreç dinliyorsa o sürecin dosya adıdır (ör. `python.exe`).
JVM ve PostgreSQL süreçleri her koşulda reddedilir: gerçek HGS2 (Spring Boot) bir JVM'de çalışır; HGS2 test profili ve
kimlik işareti doğrulanana kadar hiçbir HGS2 örneği hedef olamaz. Denetimin kendisi target_guard.check_listener'dadır.
"""

from __future__ import annotations

import ntpath
import re

REFUSED_PROCESS_NAMES = frozenset({"java", "java.exe", "javaw", "javaw.exe", "postgres", "postgres.exe",
                                   "pg_ctl", "pg_ctl.exe"})
_PROCESS_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


def is_refused_process(name: str) -> bool:
    return ntpath.basename(name).lower() in REFUSED_PROCESS_NAMES


def validate_target_process(name: object) -> str:
    """Yapılandırmadaki `target_process` değerini denetler; geçersizse ValueError."""
    if not isinstance(name, str) or not _PROCESS_NAME_RE.match(name):
        raise ValueError("target_process yalnızca harf, rakam, '_', '.', '-' içeren 1–64 karakterlik bir dosya adı "
                         "olmalı (ör. python.exe)")
    if is_refused_process(name):
        raise ValueError(f"target_process {name!r} olamaz: JVM/PostgreSQL süreçleri gerçek HGS2 veya veritabanı "
                         "olabilir ve hedef olarak kabul edilmez")
    return name
