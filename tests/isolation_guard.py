"""Test süreci yalıtım koruması (N11, N12): testler yalnızca bu sürecin kendi açtığı sunuculara bağlanabilir.

Sorun: loopback denetimi (target_guard.py), aynı makinede çalışan gerçek HGS2'yi (ör. 127.0.0.1:8080, ayrı bir JVM
süreci) yerel test sunucusundan ayıramaz; ikisi de 127.0.0.1'dedir.

Koruma (conftest.py tüm test oturumu için kurar):
* `socket.socket.bind` sarılır; bu süreçte bind edilen her TCP/UDP soketi ve portu kaydedilir (yerel test sunucusu,
  sentetik sunucu, Windows'ta `socket.socketpair` iç soketi). `socket.socket.close` sarılır: soket kapanınca port
  "açık" listesinden "bırakılmış" listesine geçer (N12; önceden port oturum boyunca izinli kalıyordu).
* `socket.socket.connect` / `connect_ex` sarılır; hedef loopback IP DEĞİLSE bağlantı KURULMADAN
  `OutOfProcessConnectionBlocked` fırlatılır ve girişim kaydedilir. Loopback hedefte izin yalnızca şu durumlarda:
  - port, bu süreçte bind edilmiş ve hâlâ AÇIK bir sokete aittir; ya da
  - port bu süreçte bind edilip bırakılmıştır VE o anda hiçbir süreç onu dinlemiyordur (işletim sistemi tablosu,
    hgs2_lab.port_owner; ör. kapalı sunucuya bağlanma testi). Bırakılan portu başka bir süreç (ör. gerçek HGS2)
    dinliyorsa ya da tablo okunamıyorsa bağlantı engellenir.
* conftest'teki otomatik fixture, test sırasında kaydedilen her girişimi testin başarısızlığı olarak raporlar
  (üretim kodu istisnayı yakalasa bile).

Sınırlar (işletim sistemi düzeyinde ağ yalıtımı DEĞİLDİR): yalnızca bu Python sürecindeki `socket.socket` çağrılarını
görür. Alt süreçler (`subprocess`), C uzantılarının kendi soketleri, `--noconftest` ile ya da pytest dışında çalıştırma
ve Windows'ta asyncio Proactor'ün `ConnectEx` yolu bu korumanın dışındadır. Bırakılmış port denetimi tablonun
okunduğu ana aittir (okuma ile bağlantı arasında dinleyici değişebilir).

Bu modül ağ erişimi yapmaz; yalnızca karar verir ve gerçek fonksiyonu çağırır ya da çağırmaz.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import weakref
from collections.abc import Callable

from hgs2_lab.port_owner import system_listener_lookup

_lock = threading.Lock()
_open_sockets: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()  # soket → bind edilen port
_released_ports: set[int] = set()
violations: list[tuple] = []  # (adres, neden); conftest her testten sonra denetler

_real_bind = socket.socket.bind
_real_close = socket.socket.close
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_installed = False


class OutOfProcessConnectionBlocked(AssertionError):
    """Test, bu süreçte açılmamış bir hedefe (gerçek HGS2 olabilir) bağlanmaya çalıştı."""


def bound_ports() -> frozenset[int]:
    """Bu süreçte bind edilmiş ve soketi hâlâ açık olan portlar."""
    with _lock:
        return frozenset(_open_sockets.values())


def released_ports() -> frozenset[int]:
    """Bu süreçte bind edilmiş ama soketi kapanmış (ve yeniden bind edilmemiş) portlar."""
    with _lock:
        return frozenset(_released_ports - set(_open_sockets.values()))


def port_has_no_listener(port: int, lookup: Callable = system_listener_lookup) -> bool:
    """Portu hiçbir süreç dinlemiyorsa True; tablo okunamazsa False (güvenli taraf)."""
    try:
        return not lookup(port)
    except OSError:
        return False


def connection_allowed(
    address: object,
    ports: frozenset[int] | set[int],
    *,
    released: frozenset[int] | set[int] = frozenset(),
    no_listener: Callable[[int], bool] = lambda port: False,
) -> bool:
    """Hedef loopback bir IP adresi mi ve port açık bir sokete ait mi (ya da bırakılmış ve dinleyicisiz mi).

    Ad (ör. "localhost") kabul edilmez: çözümlenmiş adres beklenir.
    """
    if not (isinstance(address, tuple) and len(address) >= 2):
        return False
    host, port = address[0], address[1]
    if not isinstance(host, str) or isinstance(port, bool) or not isinstance(port, int):
        return False
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_loopback:
        return False
    if port in ports:
        return True
    return port in released and no_listener(port)


def make_guarded(
    real: Callable,
    ports: Callable[[], frozenset[int]],
    record: list,
    released: Callable[[], frozenset[int]] = frozenset,
    no_listener: Callable[[int], bool] = lambda port: False,
) -> Callable:
    """`real` (connect/connect_ex) yalnızca izinli hedefte çağrılır; aksi hâlde girişim kaydedilir ve istisna fırlatılır."""

    def guarded(self, address):
        if not connection_allowed(address, ports(), released=released(), no_listener=no_listener):
            record.append((address, "loopback değil veya port bu test sürecinde açık değil (bırakılmış portu başka "
                                    "bir süreç dinliyor olabilir)"))
            raise OutOfProcessConnectionBlocked(
                f"Test süreci dışındaki hedefe bağlantı engellendi (gerçek HGS2 olabilir): {address!r}")
        return real(self, address)

    return guarded


def _tracking_bind(self, address):
    _real_bind(self, address)
    if self.family in (socket.AF_INET, socket.AF_INET6):
        port = self.getsockname()[1]
        with _lock:
            _open_sockets[self] = port


def _tracking_close(self):
    with _lock:
        port = _open_sockets.pop(self, None)
        if port is not None:
            _released_ports.add(port)
    _real_close(self)


guarded_connect = make_guarded(_real_connect, bound_ports, violations, released_ports, port_has_no_listener)
guarded_connect_ex = make_guarded(_real_connect_ex, bound_ports, violations, released_ports, port_has_no_listener)


def install() -> None:
    global _installed
    if _installed:
        return
    socket.socket.bind = _tracking_bind
    socket.socket.close = _tracking_close
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    _installed = True


def uninstall() -> None:
    global _installed
    socket.socket.bind = _real_bind
    socket.socket.close = _real_close
    socket.socket.connect = _real_connect
    socket.socket.connect_ex = _real_connect_ex
    _installed = False
