"""HGS2 güvenli başlatma (hgs2_launch.py) ve `hgs2 run` komutu birim testleri.

Gerçek Java, HGS2, PostgreSQL, donanım veya ağ kullanılmaz: Popen, iş nesnesi, dinleyici tablosu, saat ve ortam
sahtedir; JAR'lar geçici dizinde üretilen ZIP dosyalarıdır, java.exe boş bir dosyadır (hiç çalıştırılmaz).
"""

import dataclasses
import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
import time
import warnings
import zipfile
from pathlib import Path

import pytest

from hgs2_lab import cli, hgs2_launch
from hgs2_lab.execution import RunOutcome
from hgs2_lab.hgs2_launch import (
    ENV_PASSWORD,
    ENV_USERNAME,
    JAR_GUARD_CLASS,
    JAR_MAIN_CLASS,
    JAR_PROFILE_FILE,
    Hgs2LaunchError,
    Hgs2Process,
    build_child_env,
    build_command,
    check_command,
    parse_properties,
    prepare_launch,
)
from hgs2_lab.port_owner import ListenerLookupError, ListeningSocket
from hgs2_lab.target_guard import LaunchedTarget

SECRET = "S3cr3t-Pa55w0rd-xyz"  # sahte; hiçbir çıktıda görünmemeli
USER = "lab_tester_role"  # veritabanı adının alt dizesi olmasın
PID = 4242
FOREIGN = 5151
CLASS_BYTES = b"\xca\xfe\xba\xbe\x00\x00\x00\x41" + b"\x00" * 16
PROFILE_TEXT = (
    "# perftest\n"
    "server.address=127.0.0.1\n"
    "server.port=18080\n"
    "spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/hgs2_perftest_db\n"
    "spring.datasource.username=${HGS_PERFTEST_DB_USERNAME}\n"
    "spring.datasource.password=${HGS_PERFTEST_DB_PASSWORD}\n"
    "spring.jpa.hibernate.ddl-auto=none\n"
    "spring.jpa.show-sql=false\n"
    "spring.sql.init.mode=never\n"
)
GUARD_LINE = ("2026-10-30T10:00:00.000+03:00  INFO 4242 --- [HGS] [           main] "
              "c.H.HGS.Config.PerfTestSafetyGuard       : perftest güvenlik denetimi geçti: 127.0.0.1:18080, "
              "veritabanı hgs2_perftest_db, ddl-auto none")
PORT_LINE = ("2026-10-30T10:00:03.000+03:00  INFO 4242 --- [HGS] [           main] "
             "o.s.boot.tomcat.TomcatWebServer          : Tomcat started on port 18080 (http) with context path '/'")
GUARD_FAIL_LINE = ("java.lang.IllegalStateException: perftest güvenlik denetimi başarısız, uygulama başlatılmadı: "
                   "etkin profil yalnızca 'perftest' olmalı")
OK = ("127.0.0.1", 18080)


# --- geçici HGS2 ağacı ---
def write_jar(path, *, guard=CLASS_BYTES, main=CLASS_BYTES, profile=PROFILE_TEXT, extra=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # bilerek yinelenen girdi
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
            if guard is not None:
                archive.writestr(JAR_GUARD_CLASS, guard)
            if main is not None:
                archive.writestr(JAR_MAIN_CLASS, main)
            if profile is not None:
                archive.writestr(JAR_PROFILE_FILE, profile)
            for name, data in extra:
                archive.writestr(name, data)
    return path


@dataclasses.dataclass
class Tree:
    root: Path
    app: Path
    jar: Path
    java: Path
    environ: dict


@pytest.fixture
def tree(tmp_path):
    app = tmp_path / "HGS"
    (app / "src/main/java/com/HibritGirisSistemi/HGS").mkdir(parents=True)
    (app / "src/main/resources").mkdir(parents=True)
    (app / "pom.xml").write_text("<project><artifactId>HGS</artifactId></project>", encoding="utf-8")
    (app / "src/main/java/com/HibritGirisSistemi/HGS/HgsApplication.java").write_text("class X {}", encoding="utf-8")
    (app / "src/main/resources/application-perftest.properties").write_text(PROFILE_TEXT, encoding="utf-8")
    jar = write_jar(app / "target" / "HGS-0.0.1-SNAPSHOT.jar")
    jdk = tmp_path / "jdk-21"
    (jdk / "bin").mkdir(parents=True)
    (jdk / "release").write_text('JAVA_VERSION="21"\n', encoding="utf-8")
    java = jdk / "bin" / "java.exe"
    java.write_bytes(b"MZ")  # hiç çalıştırılmaz
    environ = {"SYSTEMROOT": r"C:\Windows", "TEMP": r"C:\Temp", ENV_USERNAME: USER, ENV_PASSWORD: SECRET}
    return Tree(tmp_path, app, jar, java, environ)


def prepare(tree, **overrides):
    args = {"java": tree.java, "jar": tree.jar, "app_dir": tree.app, "environ": tree.environ, "platform": "win32"}
    args.update(overrides)
    return prepare_launch(**args)


def assert_rejected(reason, call, *args, **kwargs):
    with pytest.raises(Hgs2LaunchError) as info:
        call(*args, **kwargs)
    assert info.value.reason == reason, str(info.value)
    assert SECRET not in str(info.value)
    return info.value


# --- komut ---
def test_command_is_fixed_and_carries_no_credentials(tree):
    plan = prepare(tree)
    assert list(plan.argv) == [
        str(tree.java), "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8",
        "-jar", str(tree.jar),
        "--spring.profiles.active=perftest", "--server.address=127.0.0.1", "--server.port=18080",
        "--spring.jpa.hibernate.ddl-auto=none",
        "--spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/hgs2_perftest_db",
    ]
    joined = " ".join(plan.argv)
    assert SECRET not in joined and USER not in joined
    assert "username" not in joined and "password" not in joined  # kimlik bilgisi yalnızca ortamdan, profil dosyasıyla
    assert [a for a in plan.argv if "profiles" in a] == ["--spring.profiles.active=perftest"]


def test_profile_port_and_jvm_options_are_not_parameters():
    assert list(inspect.signature(build_command).parameters) == ["java", "jar"]
    assert set(inspect.signature(prepare_launch).parameters) == {"java", "jar", "app_dir", "environ", "platform"}
    assert "profile" not in inspect.signature(hgs2_launch.launch).parameters


@pytest.mark.parametrize("mutate", [
    lambda a: [x for x in a if not x.startswith("--spring.profiles.active")],  # profil eksik
    lambda a: [x.replace("=perftest", "=perftst") for x in a],  # yanlış yazılmış profil
    lambda a: [x.replace("=perftest", "=perftest,dev") for x in a],
    lambda a: [x.replace("=perftest", "=PERFTEST") for x in a],
    lambda a: a + ["--spring.profiles.active=dev"],
    lambda a: a + ["--spring.profiles.include=dev"],
    lambda a: a[:1] + ["-Dspring.profiles.active=dev"] + a[1:],
    lambda a: a[:1] + ["-javaagent:C:\\x\\agent.jar"] + a[1:],  # keyfî JVM argümanı
    lambda a: [x.replace("--server.port=18080", "--server.port=8080") for x in a],
    lambda a: [x.replace("--server.address=127.0.0.1", "--server.address=0.0.0.0") for x in a],
    lambda a: [x.replace("ddl-auto=none", "ddl-auto=update") for x in a],
    lambda a: [x.replace("hgs2_perftest_db", "hibrit_giris_db") for x in a],
    lambda a: a + ["--spring.datasource.username=postgres"],
])
def test_check_command_rejects_missing_wrong_or_extra_arguments(tree, mutate):
    argv = build_command(tree.java, tree.jar)
    assert_rejected(hgs2_launch.REASON_COMMAND, check_command, mutate(list(argv)), tree.java, tree.jar)


def test_check_command_requires_absolute_paths():
    java, jar = Path("java.exe"), Path("target/x.jar")
    assert_rejected(hgs2_launch.REASON_COMMAND, check_command, build_command(java, jar), java, jar)


# --- ortam ---
@pytest.mark.parametrize("environ, missing", [
    ({}, [ENV_USERNAME, ENV_PASSWORD]),
    ({ENV_USERNAME: USER}, [ENV_PASSWORD]),
    ({ENV_PASSWORD: SECRET}, [ENV_USERNAME]),
    ({ENV_USERNAME: "", ENV_PASSWORD: SECRET}, [ENV_USERNAME]),
    ({ENV_USERNAME: USER, ENV_PASSWORD: "   "}, [ENV_PASSWORD]),
])
def test_missing_or_blank_test_credentials_are_rejected(environ, missing):
    error = assert_rejected(hgs2_launch.REASON_ENV, build_child_env, environ)
    for name in missing:
        assert name in str(error)


@pytest.mark.parametrize("username", ["postgres", "Postgres", " POSTGRES "])
def test_postgres_superuser_is_rejected(username):
    error = assert_rejected(hgs2_launch.REASON_ENV, build_child_env, {ENV_USERNAME: username, ENV_PASSWORD: SECRET})
    assert "postgres" in str(error)


def test_child_environment_is_an_explicit_allowlist():
    environ = {
        "SystemRoot": r"C:\Windows", "WINDIR": r"C:\Windows", "SYSTEMDRIVE": "C:", "TEMP": r"C:\T", "TMP": r"C:\T",
        "hgs_perftest_db_username": USER, ENV_PASSWORD: SECRET,  # büyük/küçük harf duyarsız okunur
        "SPRING_PROFILES_ACTIVE": "dev", "SPRING_DATASOURCE_URL": "jdbc:postgresql://localhost/hibrit_giris_db",
        "SPRING_DATASOURCE_USERNAME": "postgres", "SPRING_APPLICATION_JSON": "{}", "SERVER_PORT": "8080",
        "SERVER_ADDRESS": "0.0.0.0", "JAVA_TOOL_OPTIONS": "-Dhibernate.hbm2ddl.auto=update",
        "_JAVA_OPTIONS": "-javaagent:x.jar", "JDK_JAVA_OPTIONS": "-Dx=y", "CLASSPATH": r"C:\evil",
        "PATH": r"C:\Windows", "HGS_DB_PASSWORD": "gercek-sistem", "JAVA_HOME": r"C:\jdk",
    }
    env = build_child_env(environ)
    assert env == {"SYSTEMROOT": r"C:\Windows", "WINDIR": r"C:\Windows", "SYSTEMDRIVE": "C:", "TEMP": r"C:\T",
                   "TMP": r"C:\T", ENV_USERNAME: USER, ENV_PASSWORD: SECRET}


def test_plan_repr_and_metadata_names_only_hide_the_password(tree):
    plan = prepare(tree)
    assert SECRET not in repr(plan)
    assert plan.env[ENV_PASSWORD] == SECRET and plan.secrets == (SECRET,)


def test_os_environ_is_used_when_not_given(tree, monkeypatch):
    monkeypatch.setenv(ENV_USERNAME, USER)
    monkeypatch.setenv(ENV_PASSWORD, SECRET)
    monkeypatch.setenv("SPRING_PROFILES_ACTIVE", "dev")
    plan = prepare(tree, environ=None)
    assert "SPRING_PROFILES_ACTIVE" not in plan.env and plan.env[ENV_USERNAME] == USER


# --- Java ---
def test_java_must_exist(tree):
    assert_rejected(hgs2_launch.REASON_JAVA, prepare, tree, java=tree.root / "jdk-21" / "bin" / "yok.exe")


@pytest.mark.parametrize("name", ["javaw.exe", "java.cmd", "java.bat", "python.exe"])
def test_java_must_be_java_exe(tree, name):
    other = tree.java.with_name(name)
    other.write_bytes(b"MZ")
    assert_rejected(hgs2_launch.REASON_JAVA, prepare, tree, java=other)


def test_java_must_be_absolute(tree, monkeypatch):
    monkeypatch.chdir(tree.root)
    assert_rejected(hgs2_launch.REASON_JAVA, prepare, tree, java=Path("jdk-21/bin/java.exe"))


def test_java_redirector_outside_a_jdk_is_rejected(tree):
    javapath = tree.root / "javapath"
    javapath.mkdir()
    (javapath / "java.exe").write_bytes(b"MZ")
    assert_rejected(hgs2_launch.REASON_JAVA, prepare, tree, java=javapath / "java.exe")
    (tree.root / "jdk-21" / "release").unlink()
    assert_rejected(hgs2_launch.REASON_JAVA, prepare, tree)


# --- uygulama dizini ve JAR yolu ---
@pytest.mark.parametrize("marker", hgs2_launch.APP_MARKERS)
def test_app_dir_must_be_the_hgs2_project(tree, marker):
    (tree.app / marker).unlink()
    assert_rejected(hgs2_launch.REASON_APP_DIR, prepare, tree)


def test_app_dir_pom_must_be_hgs(tree):
    (tree.app / "pom.xml").write_text("<project><artifactId>baska</artifactId></project>", encoding="utf-8")
    assert_rejected(hgs2_launch.REASON_APP_DIR, prepare, tree)


def test_jar_must_exist(tree):
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=tree.app / "target" / "yok.jar")


def test_jar_must_be_directly_in_app_target(tree):
    nested = write_jar(tree.app / "target" / "sub" / "HGS.jar")
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=nested)
    in_root = write_jar(tree.app / "HGS.jar")
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=in_root)
    outside = write_jar(tree.root / "baska" / "target" / "HGS.jar")
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=outside)


def test_jar_path_cannot_escape_with_dot_dot(tree):
    write_jar(tree.root / "baska" / "target" / "HGS.jar")
    escaping = Path(str(tree.app / "target" / ".." / ".." / "baska" / "target" / "HGS.jar"))
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=escaping)


def test_jar_must_be_absolute_and_a_jar(tree, monkeypatch):
    monkeypatch.chdir(tree.app)
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=Path("target") / tree.jar.name)
    other = tree.app / "target" / "HGS.zip"
    other.write_bytes(tree.jar.read_bytes())
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=other)


@pytest.mark.skipif(sys.platform != "win32", reason="junction yalnızca Windows'ta")
def test_junction_redirection_is_rejected(tree):
    import _winapi

    elsewhere = tree.root / "elsewhere"
    write_jar(elsewhere / "HGS.jar")
    target_dir = tree.app / "target"
    for item in target_dir.iterdir():
        item.unlink()
    target_dir.rmdir()
    _winapi.CreateJunction(str(elsewhere), str(target_dir))  # target -> başka bir konum
    try:
        error = assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=target_dir / "HGS.jar")
        assert "junction" in str(error)
    finally:
        os.rmdir(target_dir)

    link_app = tree.root / "HGS-link"
    _winapi.CreateJunction(str(tree.app), str(link_app))  # uygulama dizinine başka adla erişim
    try:
        write_jar(tree.app / "target" / "HGS.jar")
        assert_rejected(hgs2_launch.REASON_APP_DIR, prepare, tree, app_dir=link_app,
                        jar=link_app / "target" / "HGS.jar")
    finally:
        os.rmdir(link_app)


def test_file_symlink_is_rejected(tree):
    link = tree.app / "target" / "link.jar"
    try:
        os.symlink(write_jar(tree.root / "elsewhere" / "HGS.jar"), link)
    except (OSError, NotImplementedError):
        pytest.skip("sembolik bağlantı oluşturma izni yok (Windows geliştirici modu kapalı)")
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree, jar=link)


# --- JAR içeriği ---
@pytest.mark.parametrize("kwargs", [
    {"guard": None},  # güvenlik sınıfı yok
    {"profile": None},  # profil dosyası yok
    {"main": None},
    {"guard": b"not a class file"},
    {"extra": [(JAR_GUARD_CLASS, CLASS_BYTES)]},  # yinelenen girdi
    {"extra": [(JAR_PROFILE_FILE, PROFILE_TEXT.replace("18080", "8080"))]},
])
def test_jar_without_expected_safety_components_is_rejected(tree, kwargs):
    write_jar(tree.jar, **kwargs)
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree)


def test_jar_that_is_not_an_archive_is_rejected(tree):
    tree.jar.write_bytes(b"PK\x03\x04 bozuk")
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree)


@pytest.mark.parametrize("profile", [
    PROFILE_TEXT.replace("server.port=18080", "server.port=8080"),
    PROFILE_TEXT.replace("server.address=127.0.0.1", "server.address=0.0.0.0"),
    PROFILE_TEXT.replace("ddl-auto=none", "ddl-auto=update"),
    PROFILE_TEXT.replace("hgs2_perftest_db", "hibrit_giris_db"),
    PROFILE_TEXT.replace("${HGS_PERFTEST_DB_USERNAME}", "postgres"),
    PROFILE_TEXT.replace("spring.sql.init.mode=never", ""),
    PROFILE_TEXT + "server.port=8080\n",  # son değer geçerlidir (Java ile aynı)
    PROFILE_TEXT + "spring.config.import=optional:file:./override.properties\n",
    PROFILE_TEXT + "spring.profiles.include=dev\n",
    PROFILE_TEXT + "#---\nspring.config.activate.on-profile=x\nserver.port=8080\n",
    # devam satırı: ikinci satır ayrı bir anahtar DEĞİL, 'foo' değerinin parçasıdır; gerçek server.port tanımsız kalır
    PROFILE_TEXT.replace("server.port=18080\n", "foo=bar\\\n  server.port=18080\n"),
])
def test_profile_file_must_match_the_safe_settings(tree, profile):
    write_jar(tree.jar, profile=profile)
    assert_rejected(hgs2_launch.REASON_JAR, prepare, tree)


def test_profile_check_never_prints_a_literal_password(tree):
    write_jar(tree.jar, profile=PROFILE_TEXT.replace("${HGS_PERFTEST_DB_PASSWORD}", SECRET))
    error = assert_rejected(hgs2_launch.REASON_JAR, prepare, tree)
    assert "spring.datasource.password" in str(error)


def test_properties_parser_follows_java_rules():
    text = ("# yorum\n! yorum\n  a = 1\nb:2\nc 3\nd=x\\\n   y\ne=\\u0041\\tB\nf\n"
            "g=son\\\\\nh=one\ng=tekrar\n")
    assert parse_properties(text) == {"a": "1", "b": "2", "c": "3", "d": "xy", "e": "A\tB", "f": "",
                                      "g": "tekrar", "h": "one"}


def test_valid_plan_records_jar_digest_and_resolved_paths(tree):
    plan = prepare(tree)
    assert plan.jar.sha256 == hashlib.sha256(tree.jar.read_bytes()).hexdigest()
    assert plan.jar.size_bytes == tree.jar.stat().st_size
    assert plan.app_dir == Path(os.path.realpath(tree.app)) and plan.java == Path(os.path.realpath(tree.java))


def test_non_windows_platform_is_rejected(tree):
    assert_rejected(hgs2_launch.REASON_PLATFORM, prepare, tree, platform="linux")


# --- süreç yaşam döngüsü (sahte Popen, iş nesnesi, tablo, saat) ---
class FakePopen:
    def __init__(self, lines=(), *, pid=PID, exit_code=None, hang=False, encoding="utf-8"):
        self.pid = pid
        self.stdout = io.BytesIO(b"".join(line.encode(encoding) + b"\r\n" for line in lines))
        self.returncode = exit_code
        self.hang = hang
        self.terminate_calls = 0
        self.args = None
        self.kwargs = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1
        if not self.hang:
            self.returncode = 1

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("java", timeout)
        return self.returncode


class FakeJob:
    def __init__(self, fail_assign=False):
        self.assigned, self.terminated, self.closed, self.fail_assign = [], 0, 0, fail_assign

    def assign(self, pid):
        if self.fail_assign:
            raise PermissionError("assign")
        self.assigned.append(pid)

    def terminate(self):
        self.terminated += 1

    def close(self):
        self.closed += 1


class FakeTable:
    """Süreç çalışırken `alive` soketlerini, her zaman `always` soketlerini döndürür; `after_exit` sonlandıktan sonra."""

    def __init__(self, alive=(), always=(), after_exit=(), fail=False):
        self.proc = None
        self.alive, self.always, self.after_exit, self.fail = list(alive), list(always), list(after_exit), fail
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise ListenerLookupError("tablo okunamadı")
        sockets = list(self.always)
        if self.proc is not None:
            sockets += self.alive if self.proc.returncode is None else self.after_exit
        return sockets


def sock(address="127.0.0.1", port=18080, pid=PID):
    return ListeningSocket(pid=pid, address=address, port=port)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        time.sleep(0.001)  # günlük okuyucu iş parçacığına sıra ver


def start(proc, table, *, job=None, popen=None, **kwargs):
    clock = Clock()
    job = job or FakeJob()

    def fake_popen(args, **kw):
        proc.args, proc.kwargs = args, kw
        table.proc = proc
        return proc

    process = Hgs2Process.start(["java.exe", "-jar", "x.jar"], cwd=Path("C:/app"), env={ENV_PASSWORD: SECRET},
                                secrets=[SECRET], popen=popen or fake_popen, job_factory=lambda: job, table=table,
                                clock=clock, sleep=clock.sleep, **kwargs)
    return process, job, clock


@pytest.fixture(autouse=True)
def no_foreign_kill(monkeypatch):
    """Hiçbir test başka bir süreci ad/PID ile sonlandırmaya çalışmamalı."""
    def refuse(*args, **kwargs):
        raise AssertionError(f"yasak süreç sonlandırma/komut çağrısı: {args!r}")

    monkeypatch.setattr(os, "kill", refuse)
    monkeypatch.setattr(os, "system", refuse)
    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "call", refuse)
    monkeypatch.setattr(subprocess, "check_call", refuse)


def test_ready_when_guard_port_message_and_listener_set_all_match():
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    table = FakeTable(alive=[sock()])
    process, job, clock = start(proc, table)
    process.wait_until_ready()
    target = process.target()
    assert isinstance(target, LaunchedTarget) and target.pid == PID and target.is_alive()
    assert process.observed_listeners == ("127.0.0.1:18080",) and process.ready_after_seconds is not None
    assert job.assigned == [PID]
    kw = proc.kwargs
    assert kw["shell"] is False and kw["stdin"] is subprocess.DEVNULL and kw["stdout"] is subprocess.PIPE
    assert kw["stderr"] is subprocess.STDOUT and kw["cwd"] == str(Path("C:/app")) and kw["env"] == {ENV_PASSWORD: SECRET}
    if sys.platform == "win32":
        assert kw["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    report = process.stop()
    assert report.ok and report.terminated_by_lab and proc.terminate_calls == 1
    assert not target.is_alive()


@pytest.mark.parametrize("encoding", ["cp1254", "cp857"])
def test_guard_message_is_recognised_under_turkish_console_codepages(encoding):
    proc = FakePopen([GUARD_LINE, PORT_LINE], encoding=encoding)
    process, _, _ = start(proc, FakeTable(alive=[sock()]))
    process.wait_until_ready()
    process.stop()


def test_ipv4_mapped_listener_counts_as_expected_address():
    process, _, _ = start(FakePopen([GUARD_LINE, PORT_LINE]), FakeTable(alive=[sock("::ffff:127.0.0.1")]))
    process.wait_until_ready()
    assert process.observed_listeners == ("127.0.0.1:18080",)
    process.stop()


@pytest.mark.parametrize("busy", [
    [sock("127.0.0.1", 18080, FOREIGN)],
    [sock("0.0.0.0", 18080, FOREIGN)],  # ör. başka bir Java süreci
    [sock("192.168.1.5", 18080, FOREIGN)],
])
def test_busy_port_refuses_start_without_touching_the_other_process(busy):
    proc = FakePopen()
    table = FakeTable(always=busy)
    popen_calls = []
    with pytest.raises(Hgs2LaunchError) as info:
        start(proc, table, popen=lambda *a, **k: popen_calls.append(a))
    assert info.value.reason == hgs2_launch.REASON_PORT_BUSY and str(FOREIGN) in str(info.value)
    assert popen_calls == [] and proc.terminate_calls == 0


def test_unreadable_table_refuses_start():
    popen_calls = []
    with pytest.raises(Hgs2LaunchError) as info:
        start(FakePopen(), FakeTable(fail=True), popen=lambda *a, **k: popen_calls.append(a))
    assert info.value.reason == hgs2_launch.REASON_LOOKUP and popen_calls == []


def test_popen_oserror_is_reported_without_secrets():
    job = FakeJob()

    def broken(args, **kwargs):
        raise FileNotFoundError(2, f"bulunamadı {SECRET}", "C:\\jdk\\bin\\java.exe")

    with pytest.raises(Hgs2LaunchError) as info:
        start(FakePopen(), FakeTable(), job=job, popen=broken)
    assert info.value.reason == hgs2_launch.REASON_START and SECRET not in str(info.value)
    assert "FileNotFoundError" in str(info.value) and job.closed == 1


def test_job_object_failures_stop_or_prevent_the_process():
    popen_calls = []

    def no_job():
        raise OSError("job")

    with pytest.raises(Hgs2LaunchError) as info:
        Hgs2Process.start(["x"], cwd=Path("C:/"), env={}, popen=lambda *a, **k: popen_calls.append(a),
                          job_factory=no_job, table=FakeTable())
    assert info.value.reason == hgs2_launch.REASON_JOB and popen_calls == []

    proc = FakePopen()
    with pytest.raises(Hgs2LaunchError) as info:
        start(proc, FakeTable(), job=FakeJob(fail_assign=True))
    assert info.value.reason == hgs2_launch.REASON_JOB and proc.terminate_calls == 1


def test_unexpected_early_exit_is_reported_with_masked_log_tail():
    proc = FakePopen(["Starting HgsApplication", f"spring.datasource.password={SECRET}", f"ham değer {SECRET}"],
                     exit_code=1)
    table = FakeTable()
    process, job, _ = start(proc, table)
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    error = info.value
    assert error.reason == hgs2_launch.REASON_EXITED and "çıkış kodu 1" in str(error)
    assert error.log_tail and all(SECRET not in line for line in error.log_tail)
    assert any("Starting HgsApplication" in line for line in error.log_tail)
    assert proc.terminate_calls == 0 and job.terminated == 1 and job.closed == 1  # zaten sonlanmıştı


def test_guard_rejection_is_reported_as_guard_failure():
    proc = FakePopen(["Starting", GUARD_FAIL_LINE], exit_code=1)
    process, _, _ = start(proc, FakeTable())
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    assert info.value.reason == hgs2_launch.REASON_GUARD


def test_guard_rejection_stops_a_process_that_is_still_running():
    proc = FakePopen([GUARD_FAIL_LINE])
    process, _, _ = start(proc, FakeTable())
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    assert info.value.reason == hgs2_launch.REASON_GUARD and proc.terminate_calls == 1


@pytest.mark.parametrize("lines, missing", [
    ([PORT_LINE], "güvenlik koruması başarı mesajı görülmedi"),
    ([GUARD_LINE], "port 18080 açılış mesajı görülmedi"),
    ([GUARD_LINE.replace("PerfTestSafetyGuard", "BaskaSinif"), PORT_LINE], "güvenlik koruması"),
])
def test_missing_evidence_times_out_and_stops(lines, missing):
    proc = FakePopen(lines)
    process, _, clock = start(proc, FakeTable(alive=[sock()]))
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    assert info.value.reason == hgs2_launch.REASON_TIMEOUT and missing in str(info.value)
    assert 90 <= clock.now < 91 and proc.terminate_calls == 1


def test_listener_never_appearing_times_out():
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    process, _, _ = start(proc, FakeTable())
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    assert info.value.reason == hgs2_launch.REASON_TIMEOUT and "dinlemiyor" in str(info.value)


@pytest.mark.parametrize("listeners, shown", [
    ([sock("0.0.0.0")], "0.0.0.0:18080"),
    ([sock("::")], "[::]:18080"),
    ([sock("192.168.1.5")], "192.168.1.5:18080"),
    ([sock("127.0.0.1", 8080)], "127.0.0.1:8080"),
    ([sock(), sock("127.0.0.1", 8080)], "127.0.0.1:8080"),
    ([sock(), sock("127.0.0.1", 5005)], "127.0.0.1:5005"),  # ör. hata ayıklama portu
    ([sock(), sock("::1")], "[::1]:18080"),
])
def test_unexpected_address_or_port_fails_and_stops_only_our_process(listeners, shown):
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    process, job, _ = start(proc, FakeTable(alive=listeners))
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    assert info.value.reason == hgs2_launch.REASON_LISTENER and shown in str(info.value)
    assert proc.terminate_calls == 1 and job.terminated == 1 and job.closed == 1


def test_foreign_listener_on_the_port_after_start_fails():
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    table = FakeTable(alive=[sock(), sock("127.0.0.1", 18080, FOREIGN)])
    process, _, _ = start(proc, table)
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    assert info.value.reason == hgs2_launch.REASON_LISTENER and str(FOREIGN) in str(info.value)


def test_unreadable_table_during_startup_fails_closed():
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    table = FakeTable(alive=[sock()])
    process, _, _ = start(proc, table)
    table.fail = True
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready()
    assert info.value.reason == hgs2_launch.REASON_LOOKUP
    assert proc.terminate_calls == 1  # durdurulduğu doğrulanamasa da süreç sonlandırıldı


def test_keyboard_interrupt_during_startup_stops_the_process():
    proc = FakePopen([PORT_LINE])
    process, _, clock = start(proc, FakeTable(alive=[sock()]))

    def interrupted(seconds):
        raise KeyboardInterrupt

    clock.sleep = interrupted
    process._sleep = interrupted
    with pytest.raises(KeyboardInterrupt):
        process.wait_until_ready()
    assert proc.terminate_calls == 1 and not process.is_alive()


def test_stop_uses_only_the_own_process_handle_and_is_idempotent():
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    process, job, _ = start(proc, FakeTable(alive=[sock()]))
    process.wait_until_ready()
    first = process.stop()
    second = process.stop()
    assert first is second and first.ok and first.pid == PID and first.exit_code == 1
    assert proc.terminate_calls == 1 and job.terminated == 1 and job.closed == 1
    with pytest.raises(Hgs2LaunchError) as info:
        process.target()
    assert info.value.reason == hgs2_launch.REASON_NOT_READY


def test_target_is_unavailable_before_startup_is_verified():
    process, _, _ = start(FakePopen([GUARD_LINE]), FakeTable(alive=[sock()]))
    with pytest.raises(Hgs2LaunchError):
        process.target()
    process.stop()


@pytest.mark.parametrize("after_exit, detail", [
    ([sock()], f"PID {PID} hâlâ dinliyor"),
    ([sock("127.0.0.1", 18080, FOREIGN)], f"PID {FOREIGN}"),
])
def test_stop_verifies_that_the_port_was_released(after_exit, detail):
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    process, _, _ = start(proc, FakeTable(alive=[sock()], after_exit=after_exit))
    process.wait_until_ready()
    report = process.stop()
    assert report.exit_code == 1 and not report.port_released and not report.ok and detail in report.detail


def test_stop_reports_a_process_that_does_not_exit():
    proc = FakePopen([GUARD_LINE, PORT_LINE], hang=True)
    process, job, _ = start(proc, FakeTable(alive=[sock()]))
    process.wait_until_ready()
    report = process.stop(timeout=0.01)
    assert report.exit_code is None and not report.ok and "sonlanmadı" in report.detail
    assert job.terminated == 1 and job.closed == 1  # iş nesnesi kapanınca işletim sistemi sonlandırır


# --- launch / metadata ---
def test_launch_runs_the_checked_plan_and_cannot_change_the_endpoint(tree):
    plan = prepare(tree)
    proc = FakePopen([GUARD_LINE, PORT_LINE])
    table = FakeTable(alive=[sock()])
    clock = Clock()

    def fake_popen(args, **kw):
        proc.args, proc.kwargs = args, kw
        table.proc = proc
        return proc

    options = dict(popen=fake_popen, job_factory=FakeJob, table=table, clock=clock, sleep=clock.sleep)
    with pytest.raises(TypeError):
        hgs2_launch.launch(plan, expected=("127.0.0.1", 8080), **options)
    tampered = dataclasses.replace(plan, argv=plan.argv + ("--spring.profiles.active=dev",))
    assert_rejected(hgs2_launch.REASON_COMMAND, hgs2_launch.launch, tampered, **options)
    assert proc.args is None  # reddedilen planlar için süreç başlatılmadı

    process = hgs2_launch.launch(plan, **options)
    assert proc.args == list(plan.argv) and proc.kwargs["cwd"] == str(plan.app_dir)
    metadata = hgs2_launch.launch_metadata(plan, process)
    assert metadata["profile"] == "perftest" and metadata["port"] == 18080
    assert metadata["database"] == "hgs2_perftest_db" and metadata["pid"] == PID
    assert metadata["jar"]["sha256"] == plan.jar.sha256
    assert metadata["evidence"]["listeners"] == ["127.0.0.1:18080"]
    assert metadata["child_environment"] == sorted(plan.env)
    assert SECRET not in json.dumps(metadata)
    process.stop()


# --- CLI: hgs2 run ---
def write_config(tree, base_url="http://127.0.0.1:18080", **extra):
    (tree.root / "scenarios.json").write_text(json.dumps({"scenarios": [
        {"name": "kart", "method": "POST", "path": "/api/auth/kart-okut", "repetitions": 2}]}), encoding="utf-8")
    config = tree.root / "config.json"
    config.write_text(json.dumps({"base_url": base_url, "output_dir": "results", "scenarios_file": "scenarios.json",
                                  **extra}), encoding="utf-8")
    return config


def cli_args(tree, config, *extra):
    return ["hgs2", "run", "--config", str(config), "--java", str(tree.java), "--jar", str(tree.jar),
            "--app-dir", str(tree.app), *extra]


@pytest.fixture
def credentials(monkeypatch, tree):
    monkeypatch.setenv(ENV_USERNAME, USER)
    monkeypatch.setenv(ENV_PASSWORD, SECRET)


@pytest.fixture
def no_launch(monkeypatch):
    monkeypatch.setattr(hgs2_launch, "launch", lambda *a, **k: pytest.fail("HGS2 başlatılmamalıydı"))


@pytest.mark.parametrize("option", [["--profile", "dev"], ["--port", "8080"], ["--jvm-arg", "-Dx=y"],
                                    ["--spring.profiles.active=dev"], ["--jdbc-url", "x"]])
def test_cli_does_not_accept_profile_port_or_jvm_overrides(tree, option, no_launch, capsys):
    with pytest.raises(SystemExit) as info:
        cli.main(cli_args(tree, write_config(tree), *option))
    assert info.value.code == cli.EXIT_USAGE


@pytest.mark.parametrize("base_url", ["http://localhost:18080", "http://127.0.0.1:8080", "http://127.0.0.1:18081",
                                      "https://127.0.0.1:18080", "http://127.0.0.1:18080/api"])
def test_cli_requires_the_fixed_target(tree, base_url, credentials, no_launch, capsys):
    assert cli.main(cli_args(tree, write_config(tree, base_url))) == cli.EXIT_REJECTED
    assert "http://127.0.0.1:18080" in capsys.readouterr().err


def test_cli_refuses_target_process_with_launch(tree, credentials, no_launch, capsys):
    config = write_config(tree, target_process="python.exe")
    assert cli.main(cli_args(tree, config)) == cli.EXIT_REJECTED
    assert "target_process" in capsys.readouterr().err


def test_cli_refuses_missing_credentials_before_launch(tree, monkeypatch, no_launch, capsys):
    monkeypatch.delenv(ENV_USERNAME, raising=False)
    monkeypatch.setenv(ENV_PASSWORD, SECRET)
    assert cli.main(cli_args(tree, write_config(tree))) == cli.EXIT_REJECTED
    captured = capsys.readouterr()
    assert ENV_USERNAME in captured.err and SECRET not in captured.out + captured.err
    assert not (tree.root / "results").exists()


def test_cli_refuses_an_invalid_jar_before_launch(tree, credentials, no_launch, capsys):
    write_jar(tree.jar, guard=None)
    assert cli.main(cli_args(tree, write_config(tree))) == cli.EXIT_REJECTED
    assert "PerfTestSafetyGuard" in capsys.readouterr().err


class FakeProcess:
    pid = PID
    observed_listeners = ("127.0.0.1:18080",)
    ready_after_seconds = 3.2

    def __init__(self, report_ok=True):
        self.stops = 0
        self.report_ok = report_ok

    def target(self):
        return LaunchedTarget(pid=PID, is_alive=lambda: self.stops == 0)

    def stop(self):
        self.stops += 1
        return hgs2_launch.StopReport(PID, 1, True, self.report_ok, None if self.report_ok else "PID hâlâ dinliyor")


def test_cli_runs_against_the_launched_target_and_always_stops_it(tree, credentials, monkeypatch, capsys):
    process = FakeProcess()
    monkeypatch.setattr(hgs2_launch, "launch", lambda plan: process)
    calls = []

    def fake_execute_run(config, scenarios, **kwargs):
        calls.append(kwargs)
        return RunOutcome(kwargs["run_id"], "completed", None, None, 2)

    monkeypatch.setattr(cli, "execute_run", fake_execute_run)
    assert cli.main(cli_args(tree, write_config(tree))) == cli.EXIT_OK
    [kwargs] = calls
    assert kwargs["launched"].pid == PID and kwargs["launch_metadata"]["pid"] == PID
    assert kwargs["launch_metadata"]["jar"]["sha256"] == hashlib.sha256(tree.jar.read_bytes()).hexdigest()
    assert process.stops == 1
    captured = capsys.readouterr()
    assert "boşaldı" in captured.out and SECRET not in captured.out + captured.err


def test_cli_stops_the_process_even_when_the_run_raises(tree, credentials, monkeypatch):
    process = FakeProcess()
    monkeypatch.setattr(hgs2_launch, "launch", lambda plan: process)

    def boom(*args, **kwargs):
        raise RuntimeError("beklenmeyen")

    monkeypatch.setattr(cli, "execute_run", boom)
    with pytest.raises(RuntimeError):
        cli.main(cli_args(tree, write_config(tree)))
    assert process.stops == 1


def test_cli_reports_unverified_stop_with_its_own_exit_code(tree, credentials, monkeypatch, capsys):
    monkeypatch.setattr(hgs2_launch, "launch", lambda plan: FakeProcess(report_ok=False))
    monkeypatch.setattr(cli, "execute_run",
                        lambda config, scenarios, **kw: RunOutcome(kw["run_id"], "completed", None, None, 2))
    assert cli.main(cli_args(tree, write_config(tree))) == cli.EXIT_TARGET_STOP_FAILED
    assert "elle denetleyin" in capsys.readouterr().err


def test_cli_launch_failure_prints_masked_tail_and_sends_nothing(tree, credentials, monkeypatch, capsys):
    def failing(plan):
        raise Hgs2LaunchError(hgs2_launch.REASON_EXITED, "HGS2 süreci başlangıçta sonlandı", ["satır 1", "satır 2"])

    monkeypatch.setattr(hgs2_launch, "launch", failing)
    monkeypatch.setattr(cli, "execute_run", lambda *a, **k: pytest.fail("istek gönderilmemeliydi"))
    assert cli.main(cli_args(tree, write_config(tree))) == cli.EXIT_TARGET_START_FAILED
    err = capsys.readouterr().err
    assert "process_exited" in err and "satır 2" in err
    assert not (tree.root / "results").exists()
