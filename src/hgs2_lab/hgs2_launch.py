"""HGS2'yi izole perftest profiliyle güvenli başlatma, başlangıç doğrulaması ve durdurma (`hgs2-lab hgs2 run`).

Yalnızca Windows (dinleyici tablosu ve iş nesnesi Windows API'leridir). HGS2'yi DERLEMEZ: JAR kullanıcı tarafından
önceden hazırlanır. Başlangıç doğrulaması HTTP isteği göndermez; veritabanına bağlanmaz.

Akış (`prepare_launch` -> `launch` -> çalıştırma -> `Hgs2Process.stop`):

1. Girdi doğrulaması (süreç başlatılmadan):
   * Uygulama dizini: mutlak yol, bağlantısız (sembolik bağlantı/junction/8.3 kısa ad yok), HGS2 işaretleri var
     (`pom.xml` içinde `<artifactId>HGS</artifactId>`, `HgsApplication.java`, `application-perftest.properties`).
   * Java: mutlak, bağlantısız yol; dosya adı `java.exe`; bir JDK/JRE kurulumunun `bin` dizininde (kurulum kökünde
     `release` dosyası). Oracle `javapath` gibi yönlendirici kopyalar kabul edilmez: dinleyici PID'i başlatılan PID
     olmayabilirdi.
   * JAR: mutlak, bağlantısız yol; doğrudan `<uygulama dizini>\\target\\` içinde; ZIP içeriği salt okunur incelenir
     (çalıştırılmaz): `PerfTestSafetyGuard.class`, `HgsApplication.class` ve `application-perftest.properties` tam bir
     kez bulunmalı; profil dosyası `REQUIRED_PROFILE_SETTINGS` değerlerini taşımalı, `spring.config.*` /
     `spring.profiles.*` anahtarı ve çok belgeli (`#---`) yapı içermemeli. SHA-256 özeti metadata'ya yazılır.
   * Ortam: `HGS_PERFTEST_DB_USERNAME` ve `HGS_PERFTEST_DB_PASSWORD` tanımlı ve boş olmamalı; kullanıcı adı `postgres`
     olamaz. Alt sürece YALNIZCA bu iki değişken ve `SYSTEM_ENV_ALLOWLIST` aktarılır (SPRING_*, SERVER_*,
     JAVA_TOOL_OPTIONS, _JAVA_OPTIONS, JDK_JAVA_OPTIONS, CLASSPATH... izin listesinde olmadığı için aktarılmaz).
2. Komut sabittir (`build_command`; profil, adres, port, ddl-auto ve JDBC hedefi parametre değildir) ve başlatmadan
   önce `check_command` ile yeniden denetlenir. Kullanıcı adı ve parola komut satırına HİÇ girmez: perftest profil
   dosyasındaki `${HGS_PERFTEST_DB_USERNAME}` / `${HGS_PERFTEST_DB_PASSWORD}` yer tutucuları ortamdan çözülür (JAR
   doğrulaması bu satırların varlığını denetler). Komut satırında yer tutucu kullanılmaz: Spring'in komut satırı
   kaynağındaki çözümlemesi bu depoda Java çalıştırılmadan otomatik testle doğrulanamaz.
3. Başlatma: `shell=False`, mutlak yollar, çalışma dizini uygulama dizini, `stdin=DEVNULL`, stdout+stderr tek boruda.
   Başlatmadan önce 18080 portunda (hangi adreste olursa olsun) dinleyici olmamalı; varsa başka süreç durdurulmaz,
   başlatma reddedilir. Süreç, `KILL_ON_JOB_CLOSE` ayarlı bir Windows iş nesnesine (Job Object) bağlanır: Lab çökse
   bile tutamak kapanınca JVM ve olası alt süreçleri sonlanır. Bağlanamazsa süreç durdurulur, başlatma reddedilir.
4. Başlangıç doğrulaması (en çok `STARTUP_TIMEOUT_SECONDS`): başarı için HEPSİ gerekir:
   * süreç sonlanmamış;
   * günlükte PerfTestSafetyGuard başarı satırı (`GUARD_OK_RE`);
   * günlükte port açılış satırı (`started on port 18080`; yardımcı kanıt);
   * işletim sistemi tablosunda başlatılan PID'in dinlediği adres/port kümesi TAM OLARAK {127.0.0.1:18080} ve portu
     başka bir PID dinlemiyor.
   Koruma başarısızlık satırı, erken sonlanma, beklenmeyen adres/port (0.0.0.0, ::, LAN adresi, 8080, ek port) ya da
   zaman aşımında süreç durdurulur ve `Hgs2LaunchError` fırlatılır (`reason` alanı nedeni verir).
5. Durdurma (`stop`): YALNIZCA modülün oluşturduğu `Popen` nesnesi (`terminate` = TerminateProcess, kendi tutamağıyla)
   ve kendi iş nesnesi (`TerminateJobObject`) kullanılır; tablodan PID seçilmez, ad ile (`taskkill /IM`) süreç
   sonlandırılmaz. Ardından sürecin bittiği ve portun boşaldığı doğrulanır (`StopReport`).

Windows'ta durdurma yöntemi: `Popen.terminate()` ve `taskkill /F` ikisi de TerminateProcess'tir: JVM kapanma kancaları
(Spring'in düzenli kapanışı) çalışmaz, açık işlemler PostgreSQL tarafında geri alınır. `taskkill` (zorlamasız) konsol
penceresi olmayan JVM'e WM_CLOSE gönderir ve çoğunlukla etkisizdir; `/IM` ile ad hedeflemek başka bir JVM'i (ör. gerçek
HGS2) öldürebilir, `/PID` ise PID yeniden kullanımına açıktır. `Popen` tutamağı açıkken PID başka sürece verilmez; bu
yüzden tek güvenli hedef bu tutamaktır. Ani sonlandırma test veritabanında ve `ddl-auto=none` ile kabul edilir.

Gizli değerler: parola yalnızca alt süreç ortamında bulunur; hata mesajlarında, günlük kuyruğunda ve metadata'da yer
almaz (günlük satırları parolanın birebir değeri ve sanitize.py kurallarıyla maskelenir; metadata'da yalnızca ortam
değişkeni ADLARI bulunur).

Sınırlar: JAR doğrulaması ile başlatma arasında dosya değiştirilebilir (özet başlatmadan hemen önce alınır); süreç
iş nesnesine başladıktan hemen sonra bağlanır (aradaki çok kısa sürede başlatılan alt süreç iş nesnesi dışında
kalabilir; java.exe bu aşamada alt süreç başlatmaz); günlük satırları kanıt değil yardımcı işarettir (asıl kanıt
dinleyici tablosudur); tablo okunduğu ana aittir.
"""

from __future__ import annotations

import collections
import ipaddress
import os
import re
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .metadata import file_sha256
from .port_owner import ListenerLookupError, ListeningSocket, system_listening_sockets
from .sanitize import REDACTED, sanitize_text
from .target_guard import LaunchedTarget

# --- sabit hedef (kullanıcı tarafından değiştirilemez) ---
PROFILE = "perftest"
ADDRESS = "127.0.0.1"
PORT = 18080
DATABASE = "hgs2_perftest_db"
JDBC_URL = f"jdbc:postgresql://127.0.0.1:5432/{DATABASE}"
BASE_URL = f"http://{ADDRESS}:{PORT}"
EXPECTED_ENDPOINT = (ADDRESS, PORT)

ENV_USERNAME = "HGS_PERFTEST_DB_USERNAME"
ENV_PASSWORD = "HGS_PERFTEST_DB_PASSWORD"
FORBIDDEN_USERNAMES = frozenset({"postgres"})
# Alt sürece aktarılan Windows değişkenleri (değerleri Lab'in ortamından); bunlar ve iki test değişkeni dışında hiçbir
# değişken aktarılmaz.
SYSTEM_ENV_ALLOWLIST = ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP")

FIXED_JVM_OPTIONS = ("-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8")
FIXED_APP_ARGUMENTS = (
    f"--spring.profiles.active={PROFILE}",
    f"--server.address={ADDRESS}",
    f"--server.port={PORT}",
    "--spring.jpa.hibernate.ddl-auto=none",
    f"--spring.datasource.url={JDBC_URL}",
)

STARTUP_TIMEOUT_SECONDS = 90.0
POLL_INTERVAL_SECONDS = 0.25
STOP_TIMEOUT_SECONDS = 15.0
PORT_RELEASE_TIMEOUT_SECONDS = 5.0

# --- HGS2 uygulama dizini ve JAR içeriği ---
APP_MARKERS = (
    "pom.xml",
    "src/main/java/com/HibritGirisSistemi/HGS/HgsApplication.java",
    "src/main/resources/application-perftest.properties",
)
POM_ARTIFACT_MARKER = "<artifactId>HGS</artifactId>"
JAR_GUARD_CLASS = "BOOT-INF/classes/com/HibritGirisSistemi/HGS/Config/PerfTestSafetyGuard.class"
JAR_MAIN_CLASS = "BOOT-INF/classes/com/HibritGirisSistemi/HGS/HgsApplication.class"
JAR_PROFILE_FILE = "BOOT-INF/classes/application-perftest.properties"
REQUIRED_PROFILE_SETTINGS = {
    "server.address": ADDRESS,
    "server.port": str(PORT),
    "spring.datasource.url": JDBC_URL,
    "spring.datasource.username": "${" + ENV_USERNAME + "}",
    "spring.datasource.password": "${" + ENV_PASSWORD + "}",
    "spring.jpa.hibernate.ddl-auto": "none",
    "spring.sql.init.mode": "never",
}
_FORBIDDEN_PROFILE_KEY_PREFIXES = ("spring.config.", "spring.profiles.")
_MAX_POM_BYTES = 1_000_000
_MAX_PROFILE_BYTES = 64 * 1024
_MAX_CLASS_BYTES = 1_000_000
_CLASS_MAGIC = b"\xca\xfe\xba\xbe"

# --- günlük işaretleri (Türkçe karakterler konsol kodlamasına karşı esnek eşleşir) ---
GUARD_OK_RE = re.compile(
    r"PerfTestSafetyGuard\b.*perftest g\S{1,4}venlik denetimi ge\S{1,4}ti: 127\.0\.0\.1:18080, "
    r"veritaban\S{1,4} hgs2_perftest_db, ddl-auto none\b"
)
GUARD_FAILED_RE = re.compile(r"perftest g\S{1,4}venlik denetimi ba\S{1,4}ar\S{1,4}s\S{1,4}z")
LOG_TAIL_LINES = 40
_MAX_LINE_BYTES = 8192
_MAX_TAIL_CHARS = 400

# --- hata nedenleri (Hgs2LaunchError.reason) ---
REASON_PLATFORM = "unsupported_platform"
REASON_APP_DIR = "app_dir_invalid"
REASON_JAVA = "java_invalid"
REASON_JAR = "jar_invalid"
REASON_ENV = "environment_invalid"
REASON_COMMAND = "command_invalid"
REASON_PORT_BUSY = "port_busy"
REASON_LOOKUP = "listener_lookup_failed"
REASON_JOB = "job_object_failed"
REASON_START = "start_failed"
REASON_EXITED = "process_exited"
REASON_GUARD = "guard_failed"
REASON_LISTENER = "unexpected_listener"
REASON_TIMEOUT = "startup_timeout"
REASON_NOT_READY = "not_ready"

if sys.platform == "win32":
    _CREATION_FLAGS = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
else:
    _CREATION_FLAGS = 0

Endpoint = tuple[str, int]
SocketTable = Callable[[], Sequence[ListeningSocket]]


class Hgs2LaunchError(Exception):
    """Başlatma reddedildi ya da başlangıç doğrulanamadı (süreç başlatıldıysa durdurulmuştur).

    Mesaj ve `log_tail` gizli değer içermez (bkz. modül açıklaması).
    """

    def __init__(self, reason: str, message: str, log_tail: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.reason = reason
        self.log_tail = tuple(log_tail)


def _fail(reason: str, message: str) -> Hgs2LaunchError:
    return Hgs2LaunchError(reason, message)


# --- yol doğrulaması ---
def _real_path(path: Path | str, what: str, reason: str) -> Path:
    """Mutlak ve bağlantısız yol: çözümlenmiş gerçek konum verilen yolla aynı olmalı."""
    path = Path(path)
    if not path.is_absolute():
        raise _fail(reason, f"{what} mutlak bir yol olmalı: {path}")
    absolute = Path(os.path.abspath(path))
    try:
        real = Path(os.path.realpath(absolute, strict=True))
    except OSError:
        raise _fail(reason, f"{what} bulunamadı: {absolute}") from None
    if os.path.normcase(str(real)) != os.path.normcase(str(absolute)):
        raise _fail(reason, f"{what} sembolik bağlantı, junction ya da kısa (8.3) ad içeriyor ve başka bir konuma "
                            f"çözümleniyor ({real}); gerçek tam yolu verin")
    return real


def verify_app_dir(app_dir: Path | str) -> Path:
    """HGS2 uygulama dizinini doğrular; gerçek yolunu döndürür."""
    app = _real_path(app_dir, "HGS2 uygulama dizini", REASON_APP_DIR)
    if not app.is_dir():
        raise _fail(REASON_APP_DIR, f"HGS2 uygulama dizini bir dizin değil: {app}")
    for marker in APP_MARKERS:
        if not (app / marker).is_file():
            raise _fail(REASON_APP_DIR, f"HGS2 uygulama dizini beklenen dosyayı içermiyor: {marker}")
    pom = app / "pom.xml"
    if pom.stat().st_size > _MAX_POM_BYTES or POM_ARTIFACT_MARKER not in pom.read_text("utf-8", errors="replace"):
        raise _fail(REASON_APP_DIR, f"pom.xml HGS2 projesine ait görünmüyor ({POM_ARTIFACT_MARKER} yok)")
    return app


def verify_java(java: Path | str) -> Path:
    """Java yürütülebilir dosyasını doğrular (çalıştırmaz); gerçek yolunu döndürür."""
    path = _real_path(java, "Java yürütülebilir dosyası", REASON_JAVA)
    if not path.is_file():
        raise _fail(REASON_JAVA, f"Java yürütülebilir dosyası bir dosya değil: {path}")
    if path.name.lower() != "java.exe":
        raise _fail(REASON_JAVA, f"Java yürütülebilir dosyasının adı java.exe olmalı (alınan: {path.name})")
    if path.parent.name.lower() != "bin" or not (path.parent.parent / "release").is_file():
        raise _fail(REASON_JAVA, "java.exe bir JDK/JRE kurulumunun bin dizininde olmalı (kurulum kökünde 'release' "
                                 "dosyası beklenir); javapath gibi yönlendirici kopyalar kabul edilmez")
    return path


# --- JAR doğrulaması (ZIP salt okunur incelenir, çalıştırılmaz) ---
@dataclass(frozen=True)
class JarInfo:
    path: Path
    sha256: str
    size_bytes: int


def _logical_lines(text: str) -> list[str]:
    """Java properties mantıksal satırları: yorum/boş satırlar atlanır, tek sayıda '\\' ile biten satır birleştirilir."""
    lines: list[str] = []
    pending: str | None = None
    for raw in text.splitlines():
        stripped = raw.lstrip(" \t\f")
        if pending is None:
            if not stripped or stripped[0] in "#!":
                continue
            line = stripped
        else:
            line = pending + stripped
        trailing = len(line) - len(line.rstrip("\\"))
        if trailing % 2 == 1:
            pending = line[:-1]
            continue
        pending = None
        lines.append(line)
    if pending is not None:
        lines.append(pending)
    return lines


_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


def _unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "u" and re.fullmatch(r"[0-9A-Fa-f]{4}", text[i + 2:i + 6]):
                out.append(chr(int(text[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def parse_properties(text: str) -> dict[str, str]:
    """Java `.properties` metnini çözümler (aynı anahtar tekrar ederse sonuncusu geçerlidir, Java'daki gibi)."""
    result: dict[str, str] = {}
    for line in _logical_lines(text):
        i = 0
        while i < len(line):
            if line[i] == "\\":
                i += 2
                continue
            if line[i] in "=: \t\f":
                break
            i += 1
        key, rest = line[:i], line[i:].lstrip(" \t\f")
        if rest[:1] in ("=", ":"):
            rest = rest[1:].lstrip(" \t\f")
        result[_unescape(key)] = _unescape(rest)
    return result


def _check_profile_text(text: str) -> None:
    if any(line.strip() in ("#---", "!---") for line in text.splitlines()):
        raise _fail(REASON_JAR, "JAR'daki application-perftest.properties çok belgeli (#---) olamaz")
    settings = parse_properties(text)
    for key in settings:
        if key.startswith(_FORBIDDEN_PROFILE_KEY_PREFIXES):
            raise _fail(REASON_JAR, f"JAR'daki application-perftest.properties {key} anahtarını içeremez")
    for key, expected in REQUIRED_PROFILE_SETTINGS.items():
        # Bulunan değer yazdırılmaz: yanlışlıkla dosyaya yazılmış bir parola olabilir.
        if settings.get(key) != expected:
            raise _fail(REASON_JAR, f"JAR'daki application-perftest.properties beklenen ayarı içermiyor: "
                                    f"{key}={expected}")


def _check_archive(archive: zipfile.ZipFile) -> None:
    counts = collections.Counter(archive.namelist())
    for entry in (JAR_GUARD_CLASS, JAR_MAIN_CLASS, JAR_PROFILE_FILE):
        if counts[entry] == 0:
            raise _fail(REASON_JAR, f"JAR beklenen bileşeni içermiyor: {entry}")
        if counts[entry] > 1:
            raise _fail(REASON_JAR, f"JAR aynı bileşeni birden fazla kez içeriyor: {entry}")
    guard = archive.getinfo(JAR_GUARD_CLASS)
    if guard.file_size > _MAX_CLASS_BYTES or archive.read(guard)[:4] != _CLASS_MAGIC:
        raise _fail(REASON_JAR, "JAR'daki PerfTestSafetyGuard.class geçerli bir Java sınıf dosyası değil")
    profile = archive.getinfo(JAR_PROFILE_FILE)
    if profile.file_size > _MAX_PROFILE_BYTES:
        raise _fail(REASON_JAR, "JAR'daki application-perftest.properties beklenenden büyük")
    _check_profile_text(archive.read(profile).decode("latin-1"))


def verify_jar(jar: Path | str, app_dir: Path) -> JarInfo:
    """JAR'ı doğrular (`app_dir`: verify_app_dir'in döndürdüğü gerçek yol); SHA-256 özetini hesaplar."""
    path = _real_path(jar, "HGS2 JAR dosyası", REASON_JAR)
    if not path.is_file() or path.suffix.lower() != ".jar":
        raise _fail(REASON_JAR, f"HGS2 JAR dosyası .jar uzantılı bir dosya olmalı: {path}")
    expected_dir = app_dir / "target"
    if os.path.normcase(str(path.parent)) != os.path.normcase(str(expected_dir)):
        raise _fail(REASON_JAR, f"HGS2 JAR dosyası doğrudan {expected_dir} dizininde olmalı (bulunan: {path})")
    try:
        with zipfile.ZipFile(path) as archive:
            _check_archive(archive)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as exc:
        raise _fail(REASON_JAR, f"HGS2 JAR dosyası okunamadı ya da geçerli bir arşiv değil ({type(exc).__name__})") \
            from None
    return JarInfo(path=path, sha256=file_sha256(path), size_bytes=path.stat().st_size)


# --- komut ve ortam ---
def build_command(java: Path, jar: Path) -> list[str]:
    """Sabit başlatma komutu. Profil, adres, port, ddl-auto ve JDBC hedefi parametre değildir; kimlik bilgisi yoktur."""
    return [str(java), *FIXED_JVM_OPTIONS, "-jar", str(jar), *FIXED_APP_ARGUMENTS]


def check_command(argv: Sequence[str], java: Path, jar: Path) -> None:
    """Başlatmadan hemen önce komutun sabit biçimde olduğunu denetler; uymazsa `Hgs2LaunchError`."""
    args = list(argv)
    profiles = [a for a in args if a.startswith(("--spring.profiles.", "-Dspring.profiles."))]
    if profiles != [f"--spring.profiles.active={PROFILE}"]:
        raise _fail(REASON_COMMAND, f"Başlatma komutunda profil yalnızca bir kez ve tam olarak '{PROFILE}' olmalı")
    if not (Path(java).is_absolute() and Path(jar).is_absolute()):
        raise _fail(REASON_COMMAND, "Başlatma komutunda Java ve JAR yolları mutlak olmalı")
    if args != build_command(java, jar):
        raise _fail(REASON_COMMAND, "Başlatma komutu sabit biçimle eşleşmiyor (ek ya da değiştirilmiş argüman var)")


def _lookup(environ: Mapping[str, str], name: str) -> str | None:
    for key, value in environ.items():
        if key.upper() == name:
            return value
    return None


def build_child_env(environ: Mapping[str, str]) -> dict[str, str]:
    """Alt süreç ortamı: yalnızca `SYSTEM_ENV_ALLOWLIST` ve iki test değişkeni. Mesajlar değer içermez."""
    username, password = _lookup(environ, ENV_USERNAME), _lookup(environ, ENV_PASSWORD)
    missing = [name for name, value in ((ENV_USERNAME, username), (ENV_PASSWORD, password))
               if value is None or not value.strip()]
    if missing:
        raise _fail(REASON_ENV, f"Ortam değişkeni tanımlı ve boş olmamalı: {', '.join(missing)}")
    assert username is not None and password is not None
    if username.strip().lower() in FORBIDDEN_USERNAMES:
        raise _fail(REASON_ENV, f"{ENV_USERNAME} süper kullanıcı 'postgres' olamaz; ayrı test rolü gerekli")
    env = {name: value for name in SYSTEM_ENV_ALLOWLIST if (value := _lookup(environ, name)) is not None}
    env[ENV_USERNAME] = username
    env[ENV_PASSWORD] = password
    return env


@dataclass(frozen=True)
class LaunchPlan:
    """Doğrulanmış başlatma girdileri. `env` parola içerir: repr'de ve metadata'da yer almaz."""

    app_dir: Path
    java: Path
    jar: JarInfo
    argv: tuple[str, ...]
    env: Mapping[str, str] = field(repr=False)

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self.env[ENV_PASSWORD],)


def prepare_launch(*, java: Path | str, jar: Path | str, app_dir: Path | str,
                   environ: Mapping[str, str] | None = None, platform: str = sys.platform) -> LaunchPlan:
    """Süreç başlatmadan tüm girdileri doğrular. Uymazsa `Hgs2LaunchError` (hiçbir süreç başlatılmaz)."""
    if platform != "win32":
        raise _fail(REASON_PLATFORM, f"HGS2 başlatma yalnızca Windows'ta desteklenir ({platform})")
    app = verify_app_dir(app_dir)
    java_path = verify_java(java)
    jar_info = verify_jar(jar, app)
    env = build_child_env(os.environ if environ is None else environ)
    argv = build_command(java_path, jar_info.path)
    check_command(argv, java_path, jar_info.path)
    return LaunchPlan(app_dir=app, java=java_path, jar=jar_info, argv=tuple(argv), env=env)


# --- Windows iş nesnesi (Job Object) ---
class Job(Protocol):
    def assign(self, pid: int) -> None: ...

    def terminate(self) -> None: ...

    def close(self) -> None: ...


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100

    class _BasicLimit(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IoCounters(ctypes.Structure):  # IO_COUNTERS
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                                                         "OtherOperationCount", "ReadTransferCount",
                                                         "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimit(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateJobObjectW = _kernel32.CreateJobObjectW
    _CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _CreateJobObjectW.restype = wintypes.HANDLE
    _SetInformationJobObject = _kernel32.SetInformationJobObject
    _SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _SetInformationJobObject.restype = wintypes.BOOL
    _AssignProcessToJobObject = _kernel32.AssignProcessToJobObject
    _AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _AssignProcessToJobObject.restype = wintypes.BOOL
    _TerminateJobObject = _kernel32.TerminateJobObject
    _TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _TerminateJobObject.restype = wintypes.BOOL
    _OpenProcess = _kernel32.OpenProcess
    _OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _OpenProcess.restype = wintypes.HANDLE
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _CloseHandle.restype = wintypes.BOOL

    class WindowsJob:
        """`KILL_ON_JOB_CLOSE` ayarlı iş nesnesi: tutamak kapanınca (Lab çökse bile) içindeki tüm süreçler sonlanır."""

        def __init__(self) -> None:
            handle = _CreateJobObjectW(None, None)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            info = _ExtendedLimit()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not _SetInformationJobObject(handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                                            ctypes.sizeof(info)):
                error = ctypes.get_last_error()
                _CloseHandle(handle)
                raise ctypes.WinError(error)
            self._handle: int | None = handle

        def assign(self, pid: int) -> None:
            # PID, çağıranın Popen tutamağı açık olduğu sürece başka bir sürece verilemez.
            process = _OpenProcess(_PROCESS_TERMINATE | _PROCESS_SET_QUOTA, False, pid)
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not _AssignProcessToJobObject(self._handle, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                _CloseHandle(process)

        def terminate(self) -> None:
            if self._handle:
                _TerminateJobObject(self._handle, 1)

        def close(self) -> None:
            if self._handle:
                _CloseHandle(self._handle)
                self._handle = None

else:

    class WindowsJob:  # type: ignore[no-redef]
        def __init__(self) -> None:
            raise OSError(f"İş nesnesi bu platformda desteklenmiyor ({sys.platform})")

        def assign(self, pid: int) -> None: ...

        def terminate(self) -> None: ...

        def close(self) -> None: ...


# --- günlük izleme ---
def _mask(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return sanitize_text(text, secrets)


class _LogMonitor:
    """Alt sürecin çıktısını sonuna kadar okur (boru dolup süreç kilitlenmesin), işaretleri arar ve maskelenmiş son
    satırları tutar. Ham satırlar saklanmaz."""

    def __init__(self, stream: Any, secrets: Sequence[str], port: int) -> None:
        self._stream = stream
        self._secrets = tuple(s for s in secrets if s)
        self._port_re = re.compile(rf"started on port(?:\(s\))?:?\s+{port}\b", re.IGNORECASE)
        self._tail: collections.deque[str] = collections.deque(maxlen=LOG_TAIL_LINES)
        self._lock = threading.Lock()
        self.guard_ok = threading.Event()
        self.guard_failed = threading.Event()
        self.port_evidence = threading.Event()
        self._thread = threading.Thread(target=self._run, name="hgs2-log", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            while True:
                raw = self._stream.readline(_MAX_LINE_BYTES)
                if not raw:
                    return
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if GUARD_OK_RE.search(line):
                    self.guard_ok.set()
                if GUARD_FAILED_RE.search(line):
                    self.guard_failed.set()
                if self._port_re.search(line):
                    self.port_evidence.set()
                cleaned = _mask(line, self._secrets)[:_MAX_TAIL_CHARS]
                with self._lock:
                    self._tail.append(cleaned)
        except (OSError, ValueError):
            return  # akış kapandı

    def join(self, timeout: float) -> None:
        if self._thread.is_alive():
            self._thread.join(timeout)

    def tail(self) -> list[str]:
        with self._lock:
            return list(self._tail)


# --- süreç yaşam döngüsü ---
def _normalize_address(address: str) -> str:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return str(ip)


def _endpoint_text(endpoint: Endpoint) -> str:
    address, port = endpoint
    return f"[{address}]:{port}" if ":" in address else f"{address}:{port}"


@dataclass(frozen=True)
class StopReport:
    pid: int
    exit_code: int | None  # None: süreç beklenen sürede sonlanmadı
    terminated_by_lab: bool  # False: süreç durdurma anında zaten sonlanmıştı
    port_released: bool
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code is not None and self.port_released


class Hgs2Process:
    """Bu modülün başlattığı tek süreç. Yalnızca `start` ile oluşturulur; durdurma yalnızca kendi tutamağıyla yapılır."""

    def __init__(self, proc: subprocess.Popen, job: Job, monitor: _LogMonitor, *, expected: Endpoint,
                 table: SocketTable, clock: Callable[[], float], sleep: Callable[[float], None]) -> None:
        self._proc = proc
        self._job = job
        self._monitor = monitor
        self._expected = (_normalize_address(expected[0]), expected[1])
        self._table = table
        self._clock = clock
        self._sleep = sleep
        self._started = clock()
        self._ready = False
        self._stop_report: StopReport | None = None
        self.ready_after_seconds: float | None = None
        self.observed_listeners: tuple[str, ...] = ()

    @classmethod
    def start(cls, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], secrets: Sequence[str] = (),
              expected: Endpoint = EXPECTED_ENDPOINT, popen: Callable[..., subprocess.Popen] = subprocess.Popen,
              job_factory: Callable[[], Job] = WindowsJob, table: SocketTable = system_listening_sockets,
              clock: Callable[[], float] = time.monotonic,
              sleep: Callable[[float], None] = time.sleep) -> "Hgs2Process":
        port = expected[1]
        try:
            busy = sorted({s.pid for s in table() if s.port == port})
        except (ListenerLookupError, OSError) as exc:
            raise _fail(REASON_LOOKUP, f"Dinleyici tablosu okunamadı ({type(exc).__name__}); port {port}'un boş "
                                       "olduğu doğrulanamadı, başlatma reddedildi") from None
        if busy:
            raise _fail(REASON_PORT_BUSY, f"Port {port} zaten dinleniyor (PID {', '.join(map(str, busy))}); başka "
                                          "süreç durdurulmaz, başlatma reddedildi")
        try:
            job = job_factory()
        except OSError as exc:
            raise _fail(REASON_JOB, f"İş nesnesi oluşturulamadı ({type(exc).__name__}); başlatma reddedildi") \
                from None
        try:
            proc = popen(list(argv), cwd=str(cwd), env=dict(env), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, shell=False, close_fds=True, creationflags=_CREATION_FLAGS)
        except (OSError, ValueError) as exc:
            job.close()
            raise _fail(REASON_START, f"HGS2 süreci başlatılamadı ({type(exc).__name__}: "
                                      f"{_mask(str(exc), secrets)})") from None
        monitor = _LogMonitor(proc.stdout, secrets, port)
        monitor.start()
        process = cls(proc, job, monitor, expected=expected, table=table, clock=clock, sleep=sleep)
        try:
            job.assign(proc.pid)
        except OSError as exc:
            reason = REASON_EXITED if proc.poll() is not None else REASON_JOB
            process._abort(reason, f"HGS2 süreci iş nesnesine bağlanamadı ({type(exc).__name__})")
        return process

    @property
    def pid(self) -> int:
        return self._proc.pid

    def is_alive(self) -> bool:
        return self._stop_report is None and self._proc.poll() is None

    def target(self) -> LaunchedTarget:
        """Doğrulanmış hedef; yalnızca başlangıç doğrulaması geçtiyse ve süreç durdurulmadıysa."""
        if not self._ready or self._stop_report is not None:
            raise _fail(REASON_NOT_READY, "HGS2 süreci doğrulanmadı ya da durduruldu; hedef olarak kullanılamaz")
        return LaunchedTarget(pid=self.pid, is_alive=self.is_alive)

    def log_tail(self) -> list[str]:
        return self._monitor.tail()

    def _abort(self, reason: str, message: str) -> None:
        report = self.stop()
        if reason == REASON_EXITED and self._monitor.guard_failed.is_set():
            reason, message = REASON_GUARD, "HGS2 perftest güvenlik koruması (PerfTestSafetyGuard) başlatmayı reddetti"
        state = "süreç durduruldu" if report.ok else f"DİKKAT: durdurma doğrulanamadı ({report.detail})"
        raise Hgs2LaunchError(reason, f"{message}; {state}", self._monitor.tail())

    def _check(self) -> bool:
        """Bir gözlem turu: başarı koşulları sağlandıysa True; başarısızlıkta süreci durdurur ve fırlatır."""
        if self._monitor.guard_failed.is_set():
            self._abort(REASON_GUARD, "HGS2 perftest güvenlik koruması (PerfTestSafetyGuard) başlatmayı reddetti")
        code = self._proc.poll()
        if code is not None:
            self._abort(REASON_EXITED, f"HGS2 süreci başlangıçta beklenmedik biçimde sonlandı (çıkış kodu {code})")
        try:
            sockets = list(self._table())
        except (ListenerLookupError, OSError) as exc:
            self._abort(REASON_LOOKUP, f"Dinleyici tablosu okunamadı ({type(exc).__name__}); dinleme adresi "
                                       "doğrulanamadı")
        port = self._expected[1]
        foreign = sorted({s.pid for s in sockets if s.port == port and s.pid != self.pid})
        if foreign:
            self._abort(REASON_LISTENER, f"Port {port}'u başlatılan süreç (PID {self.pid}) dışında bir süreç "
                                         f"dinliyor (PID {', '.join(map(str, foreign))})")
        mine = {(_normalize_address(s.address), s.port) for s in sockets if s.pid == self.pid}
        unexpected = sorted(mine - {self._expected})
        if unexpected:
            self._abort(REASON_LISTENER, f"HGS2 süreci beklenmeyen adres/portta dinliyor: "
                                         f"{', '.join(map(_endpoint_text, unexpected))}; beklenen yalnızca "
                                         f"{_endpoint_text(self._expected)}")
        self.observed_listeners = tuple(sorted(map(_endpoint_text, mine)))
        return mine == {self._expected} and self._monitor.guard_ok.is_set() and self._monitor.port_evidence.is_set()

    def _missing_evidence(self) -> str:
        missing = []
        if not self._monitor.guard_ok.is_set():
            missing.append("güvenlik koruması başarı mesajı görülmedi")
        if not self._monitor.port_evidence.is_set():
            missing.append(f"port {self._expected[1]} açılış mesajı görülmedi")
        if self.observed_listeners != (_endpoint_text(self._expected),):
            missing.append(f"süreç {_endpoint_text(self._expected)} adresinde dinlemiyor")
        return "; ".join(missing)

    def wait_until_ready(self, timeout: float = STARTUP_TIMEOUT_SECONDS,
                         poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
        """Başlangıcı en çok `timeout` sn gözler (HTTP isteği yok). Başarısızlıkta süreç durdurulur ve fırlatılır."""
        deadline = self._clock() + timeout
        try:
            while not self._check():
                if self._clock() >= deadline:
                    self._abort(REASON_TIMEOUT, f"HGS2 başlangıcı {timeout:g} sn içinde doğrulanamadı: "
                                                f"{self._missing_evidence()}")
                self._sleep(poll_interval)
        except Hgs2LaunchError:
            raise
        except BaseException:  # Ctrl+C dahil: süreç arkada bırakılmaz
            self.stop()
            raise
        self._ready = True
        self.ready_after_seconds = self._clock() - self._started

    def _wait_port_released(self) -> tuple[bool, str | None]:
        deadline = self._clock() + PORT_RELEASE_TIMEOUT_SECONDS
        port = self._expected[1]
        while True:
            try:
                sockets = list(self._table())
            except (ListenerLookupError, OSError) as exc:
                return False, f"dinleyici tablosu okunamadı ({type(exc).__name__})"
            mine = [s for s in sockets if s.pid == self.pid]
            others = sorted({s.pid for s in sockets if s.port == port and s.pid != self.pid})
            if not mine and not others:
                return True, None
            if self._clock() >= deadline:
                if mine:
                    return False, f"PID {self.pid} hâlâ dinliyor"
                return False, f"port {port} başka bir süreç tarafından dinleniyor (PID {', '.join(map(str, others))})"
            self._sleep(POLL_INTERVAL_SECONDS)

    def stop(self, timeout: float = STOP_TIMEOUT_SECONDS) -> StopReport:
        """Süreci ve iş nesnesini durdurur; sonlandığını ve portun boşaldığını doğrular. Tekrar çağrılabilir."""
        if self._stop_report is not None:
            return self._stop_report
        terminated = False
        if self._proc.poll() is None:
            try:
                self._proc.terminate()  # TerminateProcess, yalnızca bu Popen tutamağıyla
                terminated = True
            except OSError:
                pass  # süreç bu arada sonlandı
        try:
            self._job.terminate()  # iş nesnesindeki (yalnızca bu sürecin) alt süreçleri
        except OSError:
            pass
        try:
            exit_code: int | None = self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            exit_code = None
        self._job.close()
        self._monitor.join(5.0)
        if self._proc.stdout is not None:
            try:
                self._proc.stdout.close()
            except OSError:
                pass
        if exit_code is None:
            released, detail = False, f"süreç {timeout:g} sn içinde sonlanmadı"
        else:
            released, detail = self._wait_port_released()
        self._stop_report = StopReport(self.pid, exit_code, terminated, released, detail)
        return self._stop_report


def launch(plan: LaunchPlan, *, startup_timeout: float = STARTUP_TIMEOUT_SECONDS, **process_options: Any) \
        -> Hgs2Process:
    """Doğrulanmış plana göre HGS2'yi başlatır ve başlangıcı doğrular. Hedef (127.0.0.1:18080) değiştirilemez.

    `process_options` yalnızca testlerin sahte bileşenleri içindir (popen, job_factory, table, clock, sleep).
    """
    if "expected" in process_options:
        raise TypeError("hedef adres/port değiştirilemez")
    check_command(plan.argv, plan.java, plan.jar.path)
    process = Hgs2Process.start(plan.argv, cwd=plan.app_dir, env=plan.env, secrets=plan.secrets, **process_options)
    process.wait_until_ready(startup_timeout)
    return process


def launch_metadata(plan: LaunchPlan, process: Hgs2Process) -> dict[str, Any]:
    """`execution.hgs2_launch`: profil, hedef, JAR özeti ve başlangıç kanıtı. Gizli değer içermez."""
    return {
        "profile": PROFILE,
        "address": ADDRESS,
        "port": PORT,
        "database": DATABASE,
        "java": str(plan.java),
        "jar": {"path": str(plan.jar.path), "sha256": plan.jar.sha256, "size_bytes": plan.jar.size_bytes},
        "pid": process.pid,
        "startup_seconds": round(process.ready_after_seconds or 0.0, 3),
        "evidence": {"guard_message": True, "port_message": True, "listeners": list(process.observed_listeners)},
        "containment": "windows_job_object_kill_on_close",
        "child_environment": sorted(plan.env),  # yalnızca adlar
    }
