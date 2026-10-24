"""Sistem telemetrisi (F4): çalıştırma sırasında zaman damgalı CPU, bellek, disk ve TCP sayaçları.

Yalnızca ölçüm ve kayıt altyapısıdır. Telemetri anomali dedektörünün veya özellik tablosunun girdisi DEĞİLDİR;
sonuç dosyalarına (şema v2) dokunmaz, ayrı bir dosyaya yazılır:
`<sonuç dizini>/telemetry/<run_id>[.partial].telemetry.json`.

Kapsam (her metrik grubu `scope` taşır):
* system  : işletim sisteminin makine geneli sayaçları; deneyle ilgisiz tüm süreçlerin etkinliğini de içerir.
* process : yalnızca bu Python süreci: istemci, `synthetic run`'da aynı süreçteki sentetik sunucu ve örnekleyici
            iş parçacığının kendisi birlikte. Sunucu servis süresi veya sunucu kaynak kullanımı olarak yorumlanamaz.

Örnekleme: `start()` anında ve `stop()` anında birer örnek; arada ayrı bir arka plan iş parçacığı, başlangıç
anına göre sabit aralıklı son tarihlerde (kayma birikmez) örnek alır. Geç kalınan aralıklar atlanır ve sayılır
(`missed_slots`). Her örnek monotonik (`time.perf_counter_ns`, runner'ın saat çapasıyla aynı saat) ve duvar saati
(`time.time_ns`) zaman damgası, toplama maliyeti (`collect_ns`) ve planlanan ana göre gecikmesini (`lag_ns`) taşır.

Hata politikası: alınamayan metrik için değer UYDURULMAZ. Okuma hatasında grubun değeri null olur ve hata
`errors`'a yazılır; platformda desteklenmeyen grup `available: false` ve nedeniyle işaretlenir ve yeniden denenmez.
Telemetri hatası çalıştırmayı durdurmaz.

Ağ kodu içe aktarılmaz (requests, urllib3, socket kullanılmaz); Windows sayaçları ctypes ile salt okunur.
"""

from __future__ import annotations

import hashlib
import os
import platform
import statistics
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .clock import ClockAnchor, callable_name, ns_to_utc_iso

TELEMETRY_FORMAT = "hgs2-lab-telemetry"
TELEMETRY_SCHEMA_VERSION = 1  # alan eklemek sürüm değiştirmez; alan silmek veya anlam değiştirmek değiştirir
TELEMETRY_DIR_NAME = "telemetry"
DEFAULT_INTERVAL_MS = 250
MIN_INTERVAL_MS = 100  # daha sık örnekleme: CPU sayaçlarının saat adımı (~15,6 ms) ve GIL payı nedeniyle anlamsız
MAX_INTERVAL_MS = 60_000
MAX_SAMPLES = 20_000  # 3600 sn'lik en uzun çalıştırma en kısa aralıkta 36 000 örnek olurdu; fazlası sayılır
STOP_JOIN_TIMEOUT_SECONDS = 2.0

SCOPE_SYSTEM = "system"
SCOPE_PROCESS = "process"
COUNTER = "counter"  # birikimli sayaç (açılıştan / süreç başlangıcından beri); yalnızca farkları anlamlıdır
GAUGE = "gauge"  # anlık değer

TRIGGER_START = "start"
TRIGGER_PERIODIC = "periodic"
TRIGGER_STOP = "stop"

_NS_PER_MS = 1_000_000
_NS_PER_SECOND = 1_000_000_000
_FILETIME_PER_SECOND = 10_000_000  # Windows FILETIME ve disk süreleri 100 ns birimindedir
_MAX_ERROR_TEXT = 200


class TelemetryError(ValueError):
    """Geçersiz telemetri parametresi."""


class ProbeUnavailable(Exception):
    """Metrik grubu bu platformda veya ortamda okunamıyor; bir kez saptanır, yeniden denenmez."""


@dataclass(frozen=True)
class Probe:
    """Bir metrik grubu: aynı kaynaktan tek çağrıda okunan alanlar.

    `fields`: alan adı -> (birim, COUNTER | GAUGE). `read()` yalnızca bu alanları döndürür; okunamazsa istisna
    fırlatır (değer uydurmaz). `ProbeUnavailable` grubu çalıştırma boyunca devre dışı bırakır.
    """

    name: str
    scope: str
    source: str
    fields: Mapping[str, tuple[str, str]]
    read: Callable[[], dict[str, int | float]]
    note: str = ""
    close: Callable[[], None] | None = None  # açık kaynaklar (ör. disk tanıtıcıları); stop() sonunda çağrılır

    def describe(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "source": self.source,
            "fields": {k: {"unit": unit, "kind": kind} for k, (unit, kind) in self.fields.items()},
            "note": self.note,
        }


def validate_interval_ms(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TelemetryError(f"telemetri aralığı tam sayı (ms) olmalı (alınan: {value!r})")
    if not MIN_INTERVAL_MS <= value <= MAX_INTERVAL_MS:
        raise TelemetryError(f"telemetri aralığı {MIN_INTERVAL_MS}–{MAX_INTERVAL_MS} ms arasında olmalı (alınan: {value})")
    return value


def output_paths(output_dir: str | Path, run_id: str) -> tuple[Path, Path]:
    """(tam, kısmi) telemetri dosyası yolları; sonuç dosyalarıyla aynı `.partial` kuralı."""
    directory = Path(output_dir) / TELEMETRY_DIR_NAME
    return directory / f"{run_id}.telemetry.json", directory / f"{run_id}.partial.telemetry.json"


def _error_text(exc: BaseException) -> str:
    message = str(exc)
    return (f"{type(exc).__name__}: {message}" if message else type(exc).__name__)[:_MAX_ERROR_TEXT]


# --- metrik grupları -------------------------------------------------------------------------------------------

CPU_SYSTEM_FIELDS = {"idle_s": ("s", COUNTER), "kernel_s": ("s", COUNTER), "user_s": ("s", COUNTER)}
CPU_PROCESS_FIELDS = {"user_s": ("s", COUNTER), "system_s": ("s", COUNTER)}
MEMORY_SYSTEM_FIELDS = {
    "memory_load_percent": ("%", GAUGE), "total_phys_bytes": ("B", GAUGE), "avail_phys_bytes": ("B", GAUGE),
    "commit_limit_bytes": ("B", GAUGE), "commit_avail_bytes": ("B", GAUGE),
}
MEMORY_PROCESS_FIELDS = {
    "working_set_bytes": ("B", GAUGE), "peak_working_set_bytes": ("B", GAUGE), "private_bytes": ("B", GAUGE),
    "page_faults": ("count", COUNTER),
}
DISK_SYSTEM_FIELDS = {
    "drives": ("count", GAUGE), "read_bytes": ("B", COUNTER), "write_bytes": ("B", COUNTER),
    "read_count": ("count", COUNTER), "write_count": ("count", COUNTER), "read_time_s": ("s", COUNTER),
    "write_time_s": ("s", COUNTER), "idle_time_s": ("s", COUNTER), "queue_depth": ("count", GAUGE),
}
IO_PROCESS_FIELDS = {
    "read_ops": ("count", COUNTER), "write_ops": ("count", COUNTER), "other_ops": ("count", COUNTER),
    "read_bytes": ("B", COUNTER), "write_bytes": ("B", COUNTER), "other_bytes": ("B", COUNTER),
}
NET_TCP_SYSTEM_FIELDS = {
    "active_opens": ("count", COUNTER), "passive_opens": ("count", COUNTER), "attempt_fails": ("count", COUNTER),
    "estab_resets": ("count", COUNTER), "curr_estab": ("count", GAUGE), "in_segs": ("count", COUNTER),
    "out_segs": ("count", COUNTER), "retrans_segs": ("count", COUNTER), "in_errs": ("count", COUNTER),
    "out_rsts": ("count", COUNTER), "num_conns": ("count", GAUGE),
}

PROBE_NAMES = ("cpu_system", "cpu_process", "memory_system", "memory_process", "disk_system", "io_process",
               "net_tcp_system")

_NOTES = {
    "cpu_system": "Tüm mantıksal işlemcilerin toplamı. kernel_s boşta süreyi (idle_s) İÇERİR. Sayaçlar saat adımıyla "
                  "(~15,6 ms) güncellenir; kısa aralıklarda kullanım oranı kabadır.",
    "cpu_process": "Bu sürecin tüm iş parçacıkları (istemci, aynı süreçteki sentetik sunucu, örnekleyici). Windows'ta "
                   "saat adımı çözünürlüğündedir; cycles alanı (varsa) gerçek işlemci çevrimidir, süreye çevrilmez.",
    "memory_system": "Makine geneli fiziksel bellek ve commit sınırı (sayfa dosyası dahil).",
    "memory_process": "Bu sürecin çalışma kümesi ve özel (commit) belleği.",
    "disk_system": "Fiziksel disklerin (\\\\.\\PhysicalDriveN, başlangıçta keşfedilen) toplamı; makine geneli. Süreler "
                   "disk başına toplanır. Bir disk okunamazsa grup null olur (kısmi toplam üretilmez).",
    "io_process": "Bu sürecin TÜM G/Ç işlemleri: dosya, aygıt ve soket (loopback HTTP trafiği dahil). Disk G/Ç'si "
                  "değildir.",
    "net_tcp_system": "Makine geneli TCP istatistikleri, IPv4 + IPv6 toplamı. Loopback bağlantılarını İÇERİR (deneyin "
                      "kendi bağlantıları + diğer tüm süreçler). Segment sayısıdır, bayt değildir. 32 bit sayaçlar "
                      "(in_segs/out_segs dışındakiler) taşabilir.",
}


def _cpu_process_probe(*, cycles: Callable[[], int] | None = None) -> Probe:
    fields = dict(CPU_PROCESS_FIELDS)
    if cycles is not None:
        fields["cycles"] = ("cycles", COUNTER)

    def read() -> dict[str, int | float]:
        t = os.times()
        values: dict[str, int | float] = {"user_s": t.user, "system_s": t.system}
        if cycles is not None:
            values["cycles"] = cycles()
        return values

    source = "os.times" + (" + QueryProcessCycleTime" if cycles is not None else "")
    return Probe("cpu_process", SCOPE_PROCESS, source, fields, read, _NOTES["cpu_process"])


def _unavailable(name: str, scope: str, fields: Mapping[str, tuple[str, str]], reason: str) -> Probe:
    def read() -> dict[str, int | float]:
        raise ProbeUnavailable(reason)

    return Probe(name, scope, "unavailable", fields, read, _NOTES[name])


def _windows_probes() -> list[Probe]:  # Windows testlerinde gerçek sayaçlarla sınanır
    import ctypes
    from ctypes import wintypes as w

    # Bu çağrılar mikrosaniyelik, bloklamayan sorgulardır. 64 bit'te (tek çağrı kuralı) PyDLL ile GIL BIRAKILMADAN
    # çağrılır: aksi halde her dönüş GIL'i yeniden bekler ve CPU-yoğun bir iş parçacığı varken bir örnek ~8 el
    # değiştirmeyle onlarca ms'ye yayılır (bu makinede medyan ~46 ms; PyDLL ile < 1 ms). 32 bit'te stdcall gerektiği
    # için WinDLL kullanılır.
    library = ctypes.PyDLL if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.WinDLL
    kernel32 = library("kernel32", use_last_error=True)
    iphlpapi = library("iphlpapi", use_last_error=True)

    def fail() -> OSError:
        return ctypes.WinError(ctypes.get_last_error())

    kernel32.GetCurrentProcess.restype = w.HANDLE
    process = kernel32.GetCurrentProcess()  # sözde tanıtıcı; kapatılmaz

    class FILETIME(ctypes.Structure):
        _fields_ = [("low", w.DWORD), ("high", w.DWORD)]

    kernel32.GetSystemTimes.argtypes = [ctypes.POINTER(FILETIME)] * 3

    def cpu_system() -> dict[str, int | float]:
        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            raise fail()
        return {name: ((ft.high << 32) | ft.low) / _FILETIME_PER_SECOND
                for name, ft in (("idle_s", idle), ("kernel_s", kernel), ("user_s", user))}

    kernel32.QueryProcessCycleTime.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_uint64)]

    def cycles() -> int:
        value = ctypes.c_uint64()
        if not kernel32.QueryProcessCycleTime(process, ctypes.byref(value)):
            raise fail()
        return value.value

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", w.DWORD), ("dwMemoryLoad", w.DWORD)] + [
            (n, ctypes.c_uint64) for n in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                                           "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]

    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]

    def memory_system() -> dict[str, int | float]:
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(m)
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            raise fail()
        return {"memory_load_percent": m.dwMemoryLoad, "total_phys_bytes": m.ullTotalPhys,
                "avail_phys_bytes": m.ullAvailPhys, "commit_limit_bytes": m.ullTotalPageFile,
                "commit_avail_bytes": m.ullAvailPageFile}

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                           "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                           "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                           "PrivateUsage")]

    kernel32.K32GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), w.DWORD]

    def memory_process() -> dict[str, int | float]:
        c = PROCESS_MEMORY_COUNTERS_EX()
        c.cb = ctypes.sizeof(c)
        if not kernel32.K32GetProcessMemoryInfo(process, ctypes.byref(c), c.cb):
            raise fail()
        return {"working_set_bytes": c.WorkingSetSize, "peak_working_set_bytes": c.PeakWorkingSetSize,
                "private_bytes": c.PrivateUsage, "page_faults": c.PageFaultCount}

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                   "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    kernel32.GetProcessIoCounters.argtypes = [w.HANDLE, ctypes.POINTER(IO_COUNTERS)]

    def io_process() -> dict[str, int | float]:
        c = IO_COUNTERS()
        if not kernel32.GetProcessIoCounters(process, ctypes.byref(c)):
            raise fail()
        return {"read_ops": c.ReadOperationCount, "write_ops": c.WriteOperationCount,
                "other_ops": c.OtherOperationCount, "read_bytes": c.ReadTransferCount,
                "write_bytes": c.WriteTransferCount, "other_bytes": c.OtherTransferCount}

    class DISK_PERFORMANCE(ctypes.Structure):
        _fields_ = [("BytesRead", ctypes.c_int64), ("BytesWritten", ctypes.c_int64), ("ReadTime", ctypes.c_int64),
                    ("WriteTime", ctypes.c_int64), ("IdleTime", ctypes.c_int64), ("ReadCount", w.DWORD),
                    ("WriteCount", w.DWORD), ("QueueDepth", w.DWORD), ("SplitCount", w.DWORD),
                    ("QueryTime", ctypes.c_int64), ("StorageDeviceNumber", w.DWORD),
                    ("StorageManagerName", w.WCHAR * 8)]

    kernel32.CreateFileW.restype = w.HANDLE
    kernel32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel32.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, w.DWORD,
                                         ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [w.HANDLE]
    invalid_handle = w.HANDLE(-1).value
    ioctl_disk_performance = 0x00070020
    share_read_write, open_existing = 0x1 | 0x2, 3

    def read_drive(handle: int) -> DISK_PERFORMANCE:
        perf, returned = DISK_PERFORMANCE(), w.DWORD()
        if not kernel32.DeviceIoControl(handle, ioctl_disk_performance, None, 0, ctypes.byref(perf),
                                        ctypes.sizeof(perf), ctypes.byref(returned), None):
            raise fail()
        return perf

    # Tanıtıcılar keşifte bir kez açılır ve close() ile kapatılır: örnek başına tek yabancı çağrı (her çağrı dönüşü
    # GIL'i yeniden bekler; çağrı sayısı toplama maliyetini doğrudan etkiler).
    drives: list[int] = []
    discovery_errors: list[str] = []
    for number in range(16):
        # Erişim hakkı 0: yalnızca aygıt sorgusu; okuma/yazma izni istenmez, yönetici gerekmez.
        handle = kernel32.CreateFileW(f"\\\\.\\PhysicalDrive{number}", 0, share_read_write, None, open_existing, 0,
                                      None)
        if handle is None or handle == invalid_handle:
            error = fail()
            if error.winerror not in (2, 3):  # dosya/yol yok = o numarada disk yok
                discovery_errors.append(f"PhysicalDrive{number}: {_error_text(error)}")
            continue
        try:
            read_drive(handle)
        except OSError as exc:  # ör. disk performans sayaçları kapalı
            discovery_errors.append(f"PhysicalDrive{number}: {_error_text(exc)}")
            kernel32.CloseHandle(handle)
        else:
            drives.append(handle)

    def close_drives() -> None:
        while drives:
            kernel32.CloseHandle(drives.pop())

    def disk_system() -> dict[str, int | float]:
        if not drives:
            raise ProbeUnavailable("disk tanıtıcıları kapatıldı")
        total = dict.fromkeys(DISK_SYSTEM_FIELDS, 0)
        for handle in drives:
            p = read_drive(handle)  # bir disk okunamazsa tüm grup hata verir: kısmi toplam sahte fark üretir
            total["read_bytes"] += p.BytesRead
            total["write_bytes"] += p.BytesWritten
            total["read_count"] += p.ReadCount
            total["write_count"] += p.WriteCount
            total["read_time_s"] += p.ReadTime / _FILETIME_PER_SECOND
            total["write_time_s"] += p.WriteTime / _FILETIME_PER_SECOND
            total["idle_time_s"] += p.IdleTime / _FILETIME_PER_SECOND
            total["queue_depth"] += p.QueueDepth
        total["drives"] = len(drives)
        return total

    class MIB_TCPSTATS2(ctypes.Structure):
        _fields_ = [("RtoAlgorithm", ctypes.c_int)] + [
            (n, w.DWORD) for n in ("dwRtoMin", "dwRtoMax", "dwMaxConn", "dwActiveOpens", "dwPassiveOpens",
                                   "dwAttemptFails", "dwEstabResets", "dwCurrEstab")] + [
            ("dw64InSegs", ctypes.c_uint64), ("dw64OutSegs", ctypes.c_uint64)] + [
            (n, w.DWORD) for n in ("dwRetransSegs", "dwInErrs", "dwOutRsts", "dwNumConns")]

    tcp_stats = getattr(iphlpapi, "GetTcpStatisticsEx2", None)
    if tcp_stats is not None:
        tcp_stats.argtypes = [ctypes.POINTER(MIB_TCPSTATS2), w.ULONG]
        tcp_stats.restype = w.ULONG
    tcp_map = {"active_opens": "dwActiveOpens", "passive_opens": "dwPassiveOpens", "attempt_fails": "dwAttemptFails",
               "estab_resets": "dwEstabResets", "curr_estab": "dwCurrEstab", "in_segs": "dw64InSegs",
               "out_segs": "dw64OutSegs", "retrans_segs": "dwRetransSegs", "in_errs": "dwInErrs",
               "out_rsts": "dwOutRsts", "num_conns": "dwNumConns"}

    def net_tcp_system() -> dict[str, int | float]:
        total = dict.fromkeys(NET_TCP_SYSTEM_FIELDS, 0)
        for family in (2, 23):  # AF_INET, AF_INET6
            stats = MIB_TCPSTATS2()
            rc = tcp_stats(ctypes.byref(stats), family)
            if rc != 0:  # iphlpapi hata kodunu döndürür (GetLastError değil)
                raise ctypes.WinError(rc)
            for key, field in tcp_map.items():
                total[key] += getattr(stats, field)
        return total

    probes = [
        Probe("cpu_system", SCOPE_SYSTEM, "GetSystemTimes", CPU_SYSTEM_FIELDS, cpu_system, _NOTES["cpu_system"]),
        _cpu_process_probe(cycles=cycles),
        Probe("memory_system", SCOPE_SYSTEM, "GlobalMemoryStatusEx", MEMORY_SYSTEM_FIELDS, memory_system,
              _NOTES["memory_system"]),
        Probe("memory_process", SCOPE_PROCESS, "K32GetProcessMemoryInfo", MEMORY_PROCESS_FIELDS, memory_process,
              _NOTES["memory_process"]),
    ]
    if drives:
        probes.append(Probe("disk_system", SCOPE_SYSTEM, "DeviceIoControl(IOCTL_DISK_PERFORMANCE)",
                            DISK_SYSTEM_FIELDS, disk_system, _NOTES["disk_system"], close=close_drives))
    else:
        reason = "disk performans sayacı okunabilen fiziksel disk bulunamadı"
        probes.append(_unavailable("disk_system", SCOPE_SYSTEM, DISK_SYSTEM_FIELDS,
                                   reason + (f" ({'; '.join(discovery_errors)})" if discovery_errors else "")))
    probes.append(Probe("io_process", SCOPE_PROCESS, "GetProcessIoCounters", IO_PROCESS_FIELDS, io_process,
                        _NOTES["io_process"]))
    if tcp_stats is not None:
        probes.append(Probe("net_tcp_system", SCOPE_SYSTEM, "GetTcpStatisticsEx2 (AF_INET + AF_INET6)",
                            NET_TCP_SYSTEM_FIELDS, net_tcp_system, _NOTES["net_tcp_system"]))
    else:
        probes.append(_unavailable("net_tcp_system", SCOPE_SYSTEM, NET_TCP_SYSTEM_FIELDS,
                                   "GetTcpStatisticsEx2 bu Windows sürümünde yok"))
    return probes


def default_probes(platform_name: str = sys.platform) -> list[Probe]:
    """Bu platformda kullanılabilir metrik grupları; desteklenmeyenler `unavailable` olarak döner (değer üretmez)."""
    if platform_name == "win32":
        try:
            return _windows_probes()
        except (OSError, AttributeError) as exc:  # kitaplık/işlev yüklenemedi: yalnızca taşınabilir grup kalır
            reason = f"Windows sayaçları yüklenemedi: {_error_text(exc)}"
            probes = [_cpu_process_probe()]
    else:
        reason = f"desteklenmeyen platform: {platform_name} (sistem sayaçları yalnızca Windows için uygulandı)"
        probes = [_cpu_process_probe()]
    specs = {"cpu_system": (SCOPE_SYSTEM, CPU_SYSTEM_FIELDS), "memory_system": (SCOPE_SYSTEM, MEMORY_SYSTEM_FIELDS),
             "memory_process": (SCOPE_PROCESS, MEMORY_PROCESS_FIELDS), "disk_system": (SCOPE_SYSTEM, DISK_SYSTEM_FIELDS),
             "io_process": (SCOPE_PROCESS, IO_PROCESS_FIELDS),
             "net_tcp_system": (SCOPE_SYSTEM, NET_TCP_SYSTEM_FIELDS)}
    probes += [_unavailable(name, scope, fields, reason) for name, (scope, fields) in specs.items()]
    return sorted(probes, key=lambda p: PROBE_NAMES.index(p.name))


# --- türetilmiş değerler ---------------------------------------------------------------------------------------

DERIVED_FIELDS = {
    "interval_ms": "Önceki örnekten bu örneğe monotonik süre (monotonic_ns farkı).",
    "system_cpu_busy_ratio": "cpu_system farklarından: (Δkernel_s + Δuser_s − Δidle_s) / (Δkernel_s + Δuser_s); "
                             "makine geneli, 0–1. Payda 0 ise null.",
    "process_cpu_ratio": "cpu_process farklarından: (Δuser_s + Δsystem_s) / (interval × mantıksal CPU sayısı); "
                         "makine kapasitesine oranla bu süreç, 0–1. Saat adımı çözünürlüğünde (kaba).",
}


def derive(previous: Mapping[str, Any] | None, current: Mapping[str, Any], cpu_count: int | None) -> dict[str, Any]:
    """Ardışık iki örnekten türetilen oranlar; gerekli değerlerden biri yoksa null (uydurulmaz)."""
    result: dict[str, Any] = dict.fromkeys(DERIVED_FIELDS)
    if previous is None:
        return result
    interval_ns = current["monotonic_ns"] - previous["monotonic_ns"]
    result["interval_ms"] = interval_ns / _NS_PER_MS
    prev_cpu, cur_cpu = previous["values"].get("cpu_system"), current["values"].get("cpu_system")
    if prev_cpu and cur_cpu:
        d = {k: cur_cpu[k] - prev_cpu[k] for k in ("idle_s", "kernel_s", "user_s")}
        total = d["kernel_s"] + d["user_s"]
        if total > 0:
            result["system_cpu_busy_ratio"] = (total - d["idle_s"]) / total
    prev_proc, cur_proc = previous["values"].get("cpu_process"), current["values"].get("cpu_process")
    if prev_proc and cur_proc and cpu_count and interval_ns > 0:
        used = (cur_proc["user_s"] - prev_proc["user_s"]) + (cur_proc["system_s"] - prev_proc["system_s"])
        result["process_cpu_ratio"] = used / (interval_ns / _NS_PER_SECOND * cpu_count)
    return result


# --- örnekleyici -----------------------------------------------------------------------------------------------

CAVEATS = [
    "Telemetri bu aşamada (F4) yalnızca toplanır; anomali dedektörünün veya özellik tablosunun girdisi değildir.",
    "Örnekleyici, istemciyle (ve synthetic run'da sentetik sunucuyla) AYNI süreçte bir arka plan iş parçacığıdır; "
    "GIL'i paylaşır. Bir örnek [monotonic_ns, monotonic_ns + collect_ns] aralığında çakışan isteği bu kadar "
    "geciktirebilir; process kapsamlı metrikler istemci + sunucu + örnekleyicinin toplamıdır ve sunucu servis "
    "süresi ya da sunucu kaynak kullanımı olarak yorumlanmamalıdır.",
    "system kapsamlı metrikler makine genelidir; deneyle ilgisiz süreçlerin etkinliğini de içerir.",
    "Sayaç (counter) alanlarının mutlak değeri anlamsızdır; yalnızca aynı dosyadaki örnekler arası farklar anlamlıdır.",
    "Bir örneğin grupları collect_ns içinde sırayla okunur; aynı ana ait değildir. 64 bit Windows'ta sayaçlar GIL "
    "bırakılmadan okunur (collect_ns tipik olarak < 1 ms; bu sürede diğer iş parçacıkları bekler). Uyanma GIL'i "
    "beklediği için başka bir iş parçacığı CPU-yoğunken lag_ns onlarca ms'ye çıkabilir; her örnekte kaydedilir.",
    "Sentetik deneyde process ve net_tcp_system değerleri enjekte edilen hatayı yansıtabilir (ör. connection_drop "
    "yeni TCP bağlantısı açtırır); bağımsız bir sinyal değildir.",
    "Ağ arabirimi bayt sayaçları toplanmaz: Windows'ta loopback trafiği arabirim sayaçlarına yansımaz ve okuma "
    "örnek başına milisaniyeler sürer (README 'F4').",
]


class TelemetryRecorder:
    """Tek kullanımlık örnekleyici: `start()` -> (arka plan örnekleri) -> `stop()` -> `document(...)`.

    `start()` ve `stop()` KeyboardInterrupt dışında istisna fırlatmaz; örnekleyici hatası belgeye yazılır.
    """

    def __init__(
        self,
        probes: Sequence[Probe] | None = None,
        *,
        interval_ms: int = DEFAULT_INTERVAL_MS,
        clock: Callable[[], int] = time.perf_counter_ns,
        wall_clock: Callable[[], int] = time.time_ns,
        thread_clock: Callable[[], int] = time.thread_time_ns,
        max_samples: int = MAX_SAMPLES,
        cpu_count: int | None = None,
    ) -> None:
        self.interval_ms = validate_interval_ms(interval_ms)
        if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples < 2:
            raise TelemetryError(f"max_samples en az 2 olan bir tam sayı olmalı (alınan: {max_samples!r})")
        self._interval_ns = interval_ms * _NS_PER_MS
        self._probes = list(probes) if probes is not None else None
        self._clock = clock
        self._wall_clock = wall_clock
        self._thread_clock = thread_clock
        self._max_samples = max_samples
        self._cpu_count = cpu_count if cpu_count is not None else os.cpu_count()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[dict[str, Any]] = []
        self._unavailable: dict[str, str] = {}
        self._error_counts: dict[str, int] = {}
        self._origin_ns: int | None = None
        self._missed_slots = 0
        self._dropped_samples = 0
        self._sampler_error: str | None = None
        self._thread_cpu_ns: int | None = None
        self._thread_left_running = False
        self._state = "new"

    @property
    def probes(self) -> list[Probe]:
        if self._probes is None:
            self._probes = default_probes()
        return self._probes

    def _take(self, trigger: str, scheduled_ns: int | None = None) -> None:
        t0 = self._clock()
        wall_ns = self._wall_clock()
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for probe in self.probes:
            if probe.name in self._unavailable:
                values[probe.name] = None
                continue
            try:
                raw = probe.read()
                values[probe.name] = {k: raw[k] for k in probe.fields}  # yalnızca tanımlı alanlar, sabit sıra
            except ProbeUnavailable as exc:
                self._unavailable[probe.name] = str(exc)[:_MAX_ERROR_TEXT]
                values[probe.name] = None
            except Exception as exc:  # noqa: BLE001 - bir metrik hatası örneklemeyi ve çalıştırmayı durdurmaz
                values[probe.name] = None
                errors[probe.name] = _error_text(exc)
        t1 = self._clock()
        sample = {
            "trigger": trigger,
            "monotonic_ns": t0,
            "wall_time_ns": wall_ns,
            "collect_ns": t1 - t0,
            "lag_ns": t0 - scheduled_ns if scheduled_ns is not None else None,
            "values": values,
            "errors": errors,
        }
        with self._lock:
            if trigger == TRIGGER_PERIODIC and len(self._samples) >= self._max_samples - 1:  # stop için yer kalır
                self._dropped_samples += 1
                return
            self._samples.append(sample)
            for name in errors:
                self._error_counts[name] = self._error_counts.get(name, 0) + 1

    def _wait_until(self, deadline_ns: int) -> bool:
        """Son tarihe kadar bekler; durdurma istenirse True. `Event.wait` zaman aşımını yuvarlayıp erken
        dönebildiği için (Windows) son tarihe ulaşılana kadar yeniden beklenir: örnek planlanan andan önce alınmaz."""
        while True:
            delay_ns = deadline_ns - self._clock()
            if delay_ns <= 0:
                return self._stop_event.is_set()
            if self._stop_event.wait(delay_ns / _NS_PER_SECOND):
                return True

    def _loop(self) -> None:
        cpu_start = self._thread_clock()
        try:
            k = 1
            while True:
                scheduled = self._origin_ns + k * self._interval_ns
                if self._wait_until(scheduled):
                    break
                behind = (self._clock() - scheduled) // self._interval_ns
                if behind > 0:  # geç kalınan aralıklar telafi edilmez, sayılır
                    self._missed_slots += behind
                    scheduled += behind * self._interval_ns
                    k += behind
                self._take(TRIGGER_PERIODIC, scheduled)
                k += 1
        except Exception as exc:  # noqa: BLE001 - örnekleyici çökse de çalıştırma sürer; belgede görünür
            self._sampler_error = _error_text(exc)
        finally:
            self._thread_cpu_ns = self._thread_clock() - cpu_start

    def start(self) -> None:
        if self._state != "new":
            raise RuntimeError("TelemetryRecorder tek kullanımlıktır")
        self._state = "running"
        try:
            self.probes  # grupların kurulumu (ör. disk keşfi) zamanlanan pencerenin dışında kalır
            self._origin_ns = self._clock()
            self._take(TRIGGER_START)
            self._thread = threading.Thread(target=self._loop, name="hgs2-lab-telemetry", daemon=True)
            self._thread.start()
        except Exception as exc:  # noqa: BLE001 - telemetri başlatılamazsa çalıştırma telemetrisiz sürer
            self._sampler_error = _error_text(exc)
            self._thread = None

    def stop(self) -> None:
        if self._state != "running":
            return
        self._state = "stopped"
        self._stop_event.set()
        try:
            if self._thread is not None:
                self._thread.join(STOP_JOIN_TIMEOUT_SECONDS)
                self._thread_left_running = self._thread.is_alive()
            self._take(TRIGGER_STOP)
            if not self._thread_left_running:  # iş parçacığı hâlâ okuyorsa kaynaklar süreç sonunda serbest kalır
                for probe in self.probes:
                    if probe.close is not None:
                        probe.close()
        except Exception as exc:  # noqa: BLE001
            self._sampler_error = self._sampler_error or _error_text(exc)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
        collect = [s["collect_ns"] / _NS_PER_MS for s in samples]
        lags = [s["lag_ns"] / _NS_PER_MS for s in samples if s["lag_ns"] is not None]
        triggers = [s["trigger"] for s in samples]
        return {
            "samples": len(samples),
            "by_trigger": {t: triggers.count(t) for t in (TRIGGER_START, TRIGGER_PERIODIC, TRIGGER_STOP)},
            "missed_slots": self._missed_slots,
            "dropped_samples": self._dropped_samples,
            "collect_ms": {"min": min(collect), "median": statistics.median(collect), "max": max(collect),
                           "total": sum(collect)} if collect else None,
            "lag_ms": {"median": statistics.median(lags), "max": max(lags)} if lags else None,
            "probe_errors": dict(sorted(self._error_counts.items())),
            "unavailable": dict(sorted(self._unavailable.items())),
            "sampler_thread_cpu_ms": self._thread_cpu_ns / _NS_PER_MS if self._thread_cpu_ns is not None else None,
            "sampler_error": self._sampler_error,
            "sampler_stopped_cleanly": self._state == "stopped" and not self._thread_left_running
                                       and self._sampler_error is None,
        }

    def document(
        self,
        run_id: str,
        *,
        anchor: ClockAnchor | None,
        dataset_kind: str,
        generated_at: str,
        result_files: Sequence[Path] = (),
    ) -> dict[str, Any]:
        """Telemetri belgesi. `offset_ms` yalnızca çapa aynı monotonik saatten alınmışsa doldurulur."""
        clock_name = callable_name(self._clock)
        anchor_ns = anchor.monotonic_ns if anchor is not None and anchor.monotonic_source == clock_name else None
        with self._lock:
            raw = list(self._samples)
        samples = []
        previous = None
        for index, s in enumerate(raw):
            item = {"index": index, "trigger": s["trigger"], "monotonic_ns": s["monotonic_ns"],
                    "offset_ms": (s["monotonic_ns"] - anchor_ns) / _NS_PER_MS if anchor_ns is not None else None,
                    "wall_time_ns": s["wall_time_ns"], "wall_time_utc": ns_to_utc_iso(s["wall_time_ns"]),
                    "collect_ns": s["collect_ns"], "lag_ns": s["lag_ns"], "values": s["values"],
                    "errors": s["errors"], "derived": derive(previous, s, self._cpu_count)}
            samples.append(item)
            previous = s
        metrics = {}
        for probe in self.probes:
            entry = probe.describe()
            reason = self._unavailable.get(probe.name)
            entry["available"] = reason is None
            entry["reason"] = reason
            metrics[probe.name] = entry
        return {
            "format": TELEMETRY_FORMAT,
            "telemetry_schema_version": TELEMETRY_SCHEMA_VERSION,
            "generated_at": generated_at,
            "run_id": run_id,
            "dataset_kind": dataset_kind,
            "tool": {"name": "hgs2-lab", "version": __version__},
            "note": "Sistem telemetrisi; sonuç dosyalarından ayrı bir kaynaktır. Bu aşamada model/dedektör girdisi "
                    "değildir ve sunucu servis süresi olarak yorumlanmamalıdır.",
            "environment": {"platform": platform.platform(), "sys_platform": sys.platform,
                            "python_version": platform.python_version(), "cpu_count": self._cpu_count},
            "process_model": {"sampler": "background_thread_same_process",
                              "note": "Örnekleyici istemciyle aynı süreçte; synthetic run'da sentetik sunucu da aynı "
                                      "süreçtedir."},
            "clock": {"monotonic_source": clock_name, "wall_source": callable_name(self._wall_clock),
                      "offset_reference": "sonuç metadata'sındaki clock.monotonic_ns (runner_origin)",
                      "offset_available": anchor_ns is not None,
                      "note": "offset_ms < 0: çalıştırmanın ilk isteğinden önce alınan örnek."},
            "sampling": {"interval_ms": self.interval_ms, "max_samples": self._max_samples,
                         "schedule": "start() ve stop() anında birer örnek; arada origin + k × interval son "
                                     "tarihlerinde (kayma birikmez, geç kalınan aralıklar atlanır)",
                         "wait": "threading.Event.wait (Windows'ta ~15,6 ms adımla uyanabilir; lag_ns kaydedilir)",
                         "timestamp": "monotonic_ns ve wall_time_ns grupların okunmasından hemen önce alınır; "
                                      "collect_ns tüm grupların okunma süresidir"},
            "metrics": metrics,
            "derived_fields": DERIVED_FIELDS,
            "caveats": CAVEATS,
            "result_files": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                             for p in result_files],
            "summary": self.summary(),
            "samples": samples,
        }
