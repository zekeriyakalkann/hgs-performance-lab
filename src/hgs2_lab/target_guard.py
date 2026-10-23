"""Hedef güvenliği: isteklerin yalnızca loopback adreslerine gitmesini sağlar.

Kontrol üç katmanda yapılır (bkz. README "Güvenlik sınırları"):

1. Metin: şema yalnızca http/https; ana makine adı yalnızca 127.0.0.1, ::1 veya localhost.
2. Çözümleme: ad çözümlenir; dönen adreslerin TAMAMI loopback olmalıdır.
3. Bağlantı: http_transport, soketi açmadan hemen önce adı yeniden çözümler, aynı kontrolü
   uygular ve yalnızca doğrulanmış IP adresine bağlanır. Böylece iki çözümleme arasında
   adresin değişmesi (DNS rebinding) bağlantı kurulmadan yakalanır.

Loopback dışı hedefe izin veren bir ayar veya otomatik geri dönüş yoktur.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_DEFAULT_PORTS = {"http": 80, "https": 443}

Resolver = Callable[[str, int], Iterable[str]]


class TargetNotAllowed(ValueError):
    """Hedef loopback değil, şeması desteklenmiyor ya da güvenle çözümlenemedi."""


def system_resolver(host: str, port: int) -> list[str]:
    """İşletim sistemi çözümleyicisi: ad için TCP adreslerini döndürür."""
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def is_loopback_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text.split("%", 1)[0])  # IPv6 bölge kimliği (fe80::1%3) ayıklanır
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 gibi adresler IPv4 kuralıyla değerlendirilir
    return ip.is_loopback


def check_url(url: str) -> tuple[str, int]:
    """URL metnini denetler; (ana makine adı, port) döndürür. Ad çözümlemesi yapmaz."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise TargetNotAllowed(f"URL ayrıştırılamadı: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise TargetNotAllowed(f"Desteklenmeyen URL şeması: {scheme or '(yok)'!r}; yalnızca http ve https")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise TargetNotAllowed(
            f"Hedef {host or '(yok)'!r} izinli değil; yalnızca loopback hedefleri: {', '.join(sorted(ALLOWED_HOSTS))}"
        )
    return host, port if port is not None else _DEFAULT_PORTS[scheme]


def resolve_loopback(host: str, port: int, resolver: Resolver = system_resolver) -> list[str]:
    """Adı çözümler; adreslerin tamamı loopback değilse reddeder. Doğrulanmış adresleri sırayla döndürür."""
    try:
        addresses = list(dict.fromkeys(resolver(host, port)))
    except OSError as exc:
        raise TargetNotAllowed(f"{host!r} çözümlenemedi ({type(exc).__name__})") from exc
    if not addresses:
        raise TargetNotAllowed(f"{host!r} hiçbir adrese çözümlenmedi")
    outside = sorted({a for a in addresses if not is_loopback_ip(a)})
    if outside:
        raise TargetNotAllowed(f"{host!r} loopback dışı adrese çözümlendi: {', '.join(outside)}")
    return addresses


def check_target(url: str, resolver: Resolver = system_resolver) -> list[str]:
    """Metin ve çözümleme kontrolü birlikte; doğrulanmış loopback adreslerini döndürür."""
    host, port = check_url(url)
    return resolve_loopback(host, port, resolver)
