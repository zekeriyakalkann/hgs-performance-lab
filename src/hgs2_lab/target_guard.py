"""Hedef güvenliği: isteklerin yalnızca loopback adreslerine gitmesini sağlar.

Kontrol üç katmanda yapılır (bkz. README "Güvenlik sınırları"):

1. Metin: şema yalnızca http/https; ana makine adı yalnızca 127.0.0.1, ::1 veya localhost.
2. Çözümleme: ad çözümlenir; dönen adreslerin TAMAMI loopback olmalıdır.
3. Bağlantı: http_transport, soketi açmadan hemen önce adı yeniden çözümler, aynı kontrolü
   uygular ve yalnızca doğrulanmış IP adresine bağlanır. Böylece iki çözümleme arasında
   adresin değişmesi (DNS rebinding) bağlantı kurulmadan yakalanır.

Loopback dışı hedefe izin veren bir ayar veya otomatik geri dönüş yoktur.

Ayrılmış portlar (`RESERVED_PORTS`): loopback denetimi, aynı makinede çalışan gerçek HGS2'yi yalıtılmış bir test
sunucusundan AYIRAMAZ (ikisi de 127.0.0.1'dedir). Gerçek HGS2 yapılandırmasındaki portlara (HGS2
`application.properties`: `server.port`, `spring.datasource.url`) gerçek ağ taşıyıcısı istek göndermez. Bu bir alt
korumadır, yalıtım kanıtı değildir: gerçek HGS2 başka bir portta başlatılırsa tanınmaz. Ayrılmış portu açan bir
ayar veya seçenek yoktur.

Dinleyici kimliği (`check_listener`, N12): istek göndermeden önce hedef portu dinleyen süreç(ler) işletim sisteminden
okunur (port_owner.py; ağ trafiği yok). İzin yalnızca şu durumlarda verilir:
* dinleyicinin tamamı BU süreçtir (Lab'in kendi sentetik/test sunucusu); ya da
* dinleyici başka bir süreçtir, adı yapılandırmada `target_process` ile AÇIKÇA bildirilmiştir ve ad eşleşir.
JVM ve PostgreSQL süreçleri (`REFUSED_PROCESS_NAMES`) her koşulda reddedilir: gerçek HGS2 (Spring Boot) bir JVM'de
çalışır; HGS2 test profili ve kimlik işareti doğrulanana kadar hiçbir HGS2 örneği hedef olamaz. Süreç adı okunamazsa,
dinleyici yoksa ya da tablo okunamazsa hedef doğrulanmamış sayılır.
Sınırlar: süreç adı kimlik kanıtı değildir (JVM olmayan bir vekil süreç gerçek sisteme iletebilir); denetim okunduğu
ana aittir (dinleyici sonradan değişebilir); yalnızca Windows'ta uygulanır.

Başlatılmış hedef (`LaunchedTarget`, `hgs2 run`): JVM kuralının TEK istisnası. hgs2_launch.py HGS2'yi perftest
profiliyle kendisi başlatır ve başlangıcı doğrular (güvenlik koruması günlüğü, PID'in dinlediği adres/port kümesi tam
olarak {127.0.0.1:18080}); yalnızca bundan sonra bir `LaunchedTarget` üretir. `launched` verildiğinde portu dinleyen
süreçlerin TAMAMI o PID olmalı ve süreç hâlâ çalışıyor olmalıdır; adı ne olursa olsun başka her dinleyici reddedilir
(`target_process` ile birlikte kullanılamaz). `launched` verilmeden JVM/PostgreSQL kuralı aynen geçerlidir. Bu istisnayı
açan bir yapılandırma anahtarı yoktur.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from urllib.parse import urlsplit

from .target_process import REFUSED_PROCESS_NAMES, is_refused_process, validate_target_process  # noqa: F401

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
RESERVED_PORTS = MappingProxyType({
    8080: "gerçek HGS2'nin server.port değeri",
    5432: "gerçek HGS2'nin PostgreSQL bağlantı portu",
})

LISTENER_IN_PROCESS = "in_process"
LISTENER_DECLARED_EXTERNAL = "declared_external"
LISTENER_LAUNCHED = "launched"

Resolver = Callable[[str, int], Iterable[str]]


class TargetNotAllowed(ValueError):
    """Hedef loopback değil, şeması desteklenmiyor ya da güvenle çözümlenemedi."""


@dataclass(frozen=True)
class ListenerOwner:
    """Bir portta dinleyen soket: sahibi süreç ve yerel adresi (port_owner.py doldurur)."""

    pid: int
    process_name: str | None  # çalıştırılabilir dosyanın adı (yol yok); okunamadıysa None
    address: str


ListenerLookup = Callable[[int], Sequence[ListenerOwner]]


@dataclass(frozen=True)
class LaunchedTarget:
    """Lab'in kendi başlattığı ve başlangıcını doğruladığı süreç (yalnızca hgs2_launch.Hgs2Process.target() üretir).

    `is_alive` sürecin Lab'in elindeki tutamağıyla hâlâ çalıştığını söyler (PID yeniden kullanılmaz: tutamak açıkken
    işletim sistemi PID'i başka sürece vermez).
    """

    pid: int
    is_alive: Callable[[], bool] = field(compare=False, repr=False)


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


def check_not_reserved_port(port: int) -> None:
    """Port gerçek HGS2 ortamına ayrılmışsa reddeder (bkz. modül açıklaması)."""
    reason = RESERVED_PORTS.get(port)
    if reason is not None:
        raise TargetNotAllowed(f"Port {port} ayrılmış ({reason}); gerçek sisteme ulaşmamak için test hedefi olamaz")


def check_listener(
    port: int,
    owners: Sequence[ListenerOwner],
    *,
    own_pid: int,
    target_process: str | None = None,
    launched: LaunchedTarget | None = None,
) -> str:
    """Portu dinleyen süreçlerin hedef olabileceğini denetler (bkz. modül açıklaması).

    Döner: `LISTENER_IN_PROCESS`, `LISTENER_DECLARED_EXTERNAL` ya da (`launched` ile) `LISTENER_LAUNCHED`.
    Uymazsa `TargetNotAllowed`.
    """
    if not owners:
        raise TargetNotAllowed(f"Port {port}'ta dinleyen süreç bulunamadı; hedefin kimliği doğrulanamadı")
    if launched is not None:
        return _check_launched(port, owners, launched, target_process)
    external = False
    for owner in owners:
        if owner.pid == own_pid:
            continue
        name = owner.process_name
        if name is None:
            raise TargetNotAllowed(f"Port {port}'u dinleyen sürecin (PID {owner.pid}) adı okunamadı; hedef "
                                   "doğrulanamadı")
        if is_refused_process(name):
            raise TargetNotAllowed(f"Port {port}'u bir JVM/PostgreSQL süreci dinliyor ({name}, PID {owner.pid}); "
                                   "gerçek HGS2 veya veritabanı olabilir, hedef olamaz")
        if target_process is None:
            raise TargetNotAllowed(f"Port {port}'u bu Lab süreci değil başka bir süreç dinliyor ({name}, PID "
                                   f"{owner.pid}); dış hedef yapılandırmada `target_process` ile açıkça bildirilmeli")
        if name.lower() != target_process.lower():
            raise TargetNotAllowed(f"Port {port}'u dinleyen süreç ({name}, PID {owner.pid}) bildirilen "
                                   f"target_process ({target_process}) ile eşleşmiyor")
        external = True
    return LISTENER_DECLARED_EXTERNAL if external else LISTENER_IN_PROCESS


def _check_launched(port: int, owners: Sequence[ListenerOwner], launched: LaunchedTarget,
                    target_process: str | None) -> str:
    if target_process is not None:
        raise TargetNotAllowed("Başlatılmış hedef ile target_process birlikte kullanılamaz")
    if not launched.is_alive():
        raise TargetNotAllowed(f"Lab'in başlattığı süreç (PID {launched.pid}) artık çalışmıyor; hedef doğrulanamadı")
    for owner in owners:
        if owner.pid != launched.pid:
            raise TargetNotAllowed(f"Port {port}'u Lab'in başlattığı süreç (PID {launched.pid}) dışında bir süreç "
                                   f"dinliyor ({owner.process_name or 'adı okunamadı'}, PID {owner.pid}); "
                                   "başlatılmamış süreçler hedef olamaz")
    return LISTENER_LAUNCHED


def check_target(url: str, resolver: Resolver = system_resolver) -> list[str]:
    """Metin ve çözümleme kontrolü birlikte; doğrulanmış loopback adreslerini döndürür."""
    host, port = check_url(url)
    return resolve_loopback(host, port, resolver)
