"""Bir TCP portunda dinleyen süreçleri işletim sisteminden okur (ağ trafiği yok; yalnızca yerel tablo okunur).

Hedef kimliği denetimi (target_guard.check_listener) için kullanılır: loopback adresi tek başına hedefin kim olduğunu
söylemez; aynı makinedeki gerçek HGS2 de 127.0.0.1'de dinleyebilir. Bu modül portu dinleyen sürecin PID'ini ve
çalıştırılabilir dosya adını verir.

Yalnızca Windows desteklenir (iphlpapi `GetExtendedTcpTable`, kernel32 `QueryFullProcessImageNameW`). Başka platformda
`ListenerLookupError` fırlatılır; çağıran taraf bunu "doğrulanamadı" olarak ele alır ve hedefi reddeder (güvenli taraf).

`system_listening_sockets` aynı tablonun filtresiz hâlidir (her adres ve port; süreç adı okunmaz): hgs2_launch.py
başlattığı sürecin dinlediği adres/port kümesini bununla doğrular (0.0.0.0, LAN adresi, 8080 vb. görünür olsun diye
loopback süzgeci uygulanmaz).

Sınırlar: tablo okunduğu andaki durumu verir (okuma ile bağlantı arasında dinleyici değişebilir); süreç adı bir kimlik
kanıtı değildir (başka adlı bir vekil süreç gerçek sisteme yönlendirebilir).
"""

from __future__ import annotations

import ipaddress
import ntpath
import socket
import sys
from dataclasses import dataclass

from .target_guard import ListenerOwner

_AF_INET, _AF_INET6 = 2, 23  # Windows değerleri
_TCP_TABLE_OWNER_PID_LISTENER = 3
_NO_ERROR, _ERROR_INSUFFICIENT_BUFFER = 0, 122
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class ListenerLookupError(OSError):
    """Dinleyen süreçler okunamadı (desteklenmeyen platform veya işletim sistemi hatası)."""


@dataclass(frozen=True)
class ListeningSocket:
    """Dinleme durumundaki bir TCP soketi: sahibi süreç, yerel adres (IPv4 ya da IPv6 metni) ve port."""

    pid: int
    address: str
    port: int


def _accepts_loopback(address: str) -> bool:
    """Bu yerel adreste dinleyen soket loopback bağlantısı kabul eder mi (loopback ya da joker adres)."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Row4(ctypes.Structure):  # MIB_TCPROW_OWNER_PID
        _fields_ = [("state", wintypes.DWORD), ("local_addr", wintypes.DWORD), ("local_port", wintypes.DWORD),
                    ("remote_addr", wintypes.DWORD), ("remote_port", wintypes.DWORD), ("pid", wintypes.DWORD)]

    class _Row6(ctypes.Structure):  # MIB_TCP6ROW_OWNER_PID
        _fields_ = [("local_addr", ctypes.c_ubyte * 16), ("local_scope", wintypes.DWORD),
                    ("local_port", wintypes.DWORD), ("remote_addr", ctypes.c_ubyte * 16),
                    ("remote_scope", wintypes.DWORD), ("remote_port", wintypes.DWORD), ("state", wintypes.DWORD),
                    ("pid", wintypes.DWORD)]

    _iphlpapi = ctypes.WinDLL("iphlpapi")
    _GetExtendedTcpTable = _iphlpapi.GetExtendedTcpTable
    _GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG,
                                     ctypes.c_int, wintypes.ULONG]
    _GetExtendedTcpTable.restype = wintypes.DWORD

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _OpenProcess = _kernel32.OpenProcess
    _OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _OpenProcess.restype = wintypes.HANDLE
    _QueryFullProcessImageNameW = _kernel32.QueryFullProcessImageNameW
    _QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                            ctypes.POINTER(wintypes.DWORD)]
    _QueryFullProcessImageNameW.restype = wintypes.BOOL
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _CloseHandle.restype = wintypes.BOOL

    def _rows(family: int, row_type: type) -> list:
        size = wintypes.DWORD(0)
        for _ in range(8):  # tablo iki çağrı arasında büyüyebilir
            buffer = ctypes.create_string_buffer(max(size.value, 4))
            code = _GetExtendedTcpTable(buffer, ctypes.byref(size), False, family, _TCP_TABLE_OWNER_PID_LISTENER, 0)
            if code == _NO_ERROR:
                count = wintypes.DWORD.from_buffer(buffer).value
                return list((row_type * count).from_buffer(buffer, ctypes.sizeof(wintypes.DWORD)))
            if code != _ERROR_INSUFFICIENT_BUFFER:
                raise ListenerLookupError(f"GetExtendedTcpTable hata kodu {code}")
        raise ListenerLookupError("GetExtendedTcpTable: tablo boyutu kararlı değil")

    def _process_name(pid: int) -> str | None:
        handle = _OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None  # ör. sistem süreci veya erişim izni yok
        try:
            length = wintypes.DWORD(1024)
            path = ctypes.create_unicode_buffer(length.value)
            if not _QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
                return None
            return ntpath.basename(path.value) or None
        finally:
            _CloseHandle(handle)

    def system_listening_sockets() -> list[ListeningSocket]:
        """Bu makinedeki tüm dinleme durumundaki TCP soketleri (IPv4 ve IPv6; adres süzgeci yok)."""
        found = [ListeningSocket(row.pid, socket.inet_ntoa(int(row.local_addr).to_bytes(4, "little")),
                                 socket.ntohs(row.local_port & 0xFFFF))
                 for row in _rows(_AF_INET, _Row4)]
        found += [ListeningSocket(row.pid, socket.inet_ntop(socket.AF_INET6, bytes(row.local_addr)),
                                  socket.ntohs(row.local_port & 0xFFFF))
                  for row in _rows(_AF_INET6, _Row6)]
        return found

    def system_listener_lookup(port: int) -> list[ListenerOwner]:
        """`port`'ta loopback bağlantısı kabul eden (loopback veya joker adresli) TCP dinleyicileri."""
        names: dict[int, str | None] = {}
        owners = []
        for sock in system_listening_sockets():
            if sock.port == port and _accepts_loopback(sock.address):
                if sock.pid not in names:
                    names[sock.pid] = _process_name(sock.pid)
                owners.append(ListenerOwner(pid=sock.pid, process_name=names[sock.pid], address=sock.address))
        return owners

else:

    def system_listening_sockets() -> list[ListeningSocket]:
        raise ListenerLookupError(f"Dinleyen süreç denetimi bu platformda desteklenmiyor ({sys.platform})")

    def system_listener_lookup(port: int) -> list[ListenerOwner]:
        raise ListenerLookupError(f"Dinleyen süreç denetimi bu platformda desteklenmiyor ({sys.platform})")
