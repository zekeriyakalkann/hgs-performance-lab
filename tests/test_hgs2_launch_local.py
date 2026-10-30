"""hgs2_launch yaşam döngüsünün gerçek işletim sistemi bileşenleriyle entegrasyon testleri (Windows).

Varsayılan çalıştırmada hariçtir (`pytest -m integration`). HGS2, Java, PostgreSQL ÇALIŞTIRILMAZ: hedef süreç, rastgele
bir 127.0.0.1 portunda dinleyen ve HGS2 günlük satırlarını taklit eden bir Python yardımcı sürecidir. Gerçek olanlar:
Popen (shell=False, DEVNULL, ortam izin listesi), Windows iş nesnesi (KILL_ON_JOB_CLOSE), dinleyici tablosu
(port_owner.system_listening_sockets) ve durdurma. Alt sürece hiçbir HTTP isteği gönderilmez; test süreci yardımcı
sürece bağlanmaz.

Yardımcı süreç, venv yönlendiricisi yerine asıl yorumlayıcıyla başlatılır (`sys._base_executable`): venv'in
python.exe'si asıl yorumlayıcıyı alt süreç olarak başlatır ve dinleyici PID'i Popen.pid olmazdı (java.exe'de böyle bir
ara süreç yoktur; bkz. hgs2_launch.verify_java).
"""

import ctypes
import os
import socket
import sys
import time
from pathlib import Path

import pytest

from hgs2_lab import hgs2_launch
from hgs2_lab.hgs2_launch import ENV_PASSWORD, ENV_USERNAME, Hgs2LaunchError, Hgs2Process, build_child_env
from hgs2_lab.port_owner import system_listening_sockets

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(sys.platform != "win32", reason="iş nesnesi ve dinleyici tablosu yalnızca Windows'ta")]

SECRET = "L0cal-S3cret-Value-q9"  # sahte
USER = "lab_tester_role"
PYTHON = getattr(sys, "_base_executable", None) or sys.executable

_CHILD = r'''
import os, socket, subprocess, sys, time
mode, port = sys.argv[1], int(sys.argv[2])
GUARD = ("2026-10-30T10:00:00.000+03:00  INFO 1 --- [HGS] [main] c.H.HGS.Config.PerfTestSafetyGuard       : "
         "perftest güvenlik denetimi geçti: 127.0.0.1:18080, veritabanı hgs2_perftest_db, ddl-auto none")

def say(text):
    sys.stdout.buffer.write(text.encode("utf-8") + b"\n")
    sys.stdout.flush()

def listen(address, p):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((address, p))
    s.listen()
    return s

say("Starting HgsApplication using Java (yardımcı süreç)")
if mode == "exit":
    say("spring.datasource.password=" + os.environ.get("HGS_PERFTEST_DB_PASSWORD", ""))
    say("ham " + os.environ.get("HGS_PERFTEST_DB_PASSWORD", ""))
    sys.exit(3)
if mode == "env":
    say("ENV " + " ".join(sorted(k.upper() for k in os.environ)))
held = [listen("0.0.0.0" if mode == "wildcard" else "127.0.0.1", port)]
if mode == "extra":
    held.append(listen("127.0.0.1", 0))
if mode == "grandchild":
    code = ("import socket, time\ns = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen()\n"
            "print(s.getsockname()[1], flush=True)\ntime.sleep(600)\n")
    child = subprocess.Popen([sys.executable, "-I", "-c", code], stdout=subprocess.PIPE, text=True)
    say("GRANDCHILD %d %s" % (child.pid, child.stdout.readline().strip()))
if mode != "silent":
    say(GUARD)
    say("Tomcat started on port %d (http) with context path '/'" % port)
time.sleep(600)
'''


def free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))  # yalnızca boş port seçimi; bağlantı yok
    port = sock.getsockname()[1]
    sock.close()
    return port


def child_env(extra=None):
    base = {k: v for k, v in os.environ.items() if k.upper() in hgs2_launch.SYSTEM_ENV_ALLOWLIST}
    return build_child_env({**base, **(extra or {}), ENV_USERNAME: USER, ENV_PASSWORD: SECRET})


@pytest.fixture
def started(tmp_path):
    """Yardımcı süreci başlatır; test bitince (başarısız olsa da) durdurur."""
    processes = []

    def start(mode, port=None, env=None):
        port = port or free_port()
        process = Hgs2Process.start([PYTHON, "-I", "-c", _CHILD, mode, str(port)], cwd=tmp_path,
                                    env=env or child_env(), secrets=[SECRET], expected=("127.0.0.1", port))
        processes.append(process)
        return process, port

    yield start
    for process in processes:
        process.stop()


def listeners(port=None, pid=None):
    return [s for s in system_listening_sockets()
            if (port is None or s.port == port) and (pid is None or s.pid == pid)]


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_job_object_structure_matches_the_windows_abi():
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(hgs2_launch._ExtendedLimit) == 144


def test_verified_start_then_stop_releases_the_port(started):
    process, port = started("ok")
    process.wait_until_ready(timeout=30)
    assert process.observed_listeners == (f"127.0.0.1:{port}",)
    assert {(s.pid, s.address) for s in listeners(port)} == {(process.pid, "127.0.0.1")}
    target = process.target()
    assert target.pid == process.pid and target.is_alive()
    report = process.stop()
    assert report.ok and report.terminated_by_lab and report.exit_code is not None
    assert listeners(port) == [] and listeners(pid=process.pid) == []
    assert not target.is_alive()


def test_child_receives_only_the_allowlisted_environment(started, monkeypatch):
    monkeypatch.setenv("SPRING_PROFILES_ACTIVE", "dev")
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-Dhibernate.hbm2ddl.auto=update")
    monkeypatch.setenv("SERVER_PORT", "8080")
    monkeypatch.setenv(ENV_USERNAME, USER)
    monkeypatch.setenv(ENV_PASSWORD, SECRET)
    env = build_child_env(os.environ)
    process, _ = started("env", env=env)
    process.wait_until_ready(timeout=30)
    [line] = [line for line in process.log_tail() if line.startswith("ENV ")]
    names = set(line.split()[1:])
    # Windows yorumlayıcısı ortam bloğuna kendisi ekleme yapmaz; görülen her ad izin listesinden gelmeli.
    assert names <= set(hgs2_launch.SYSTEM_ENV_ALLOWLIST) | {ENV_USERNAME, ENV_PASSWORD}
    assert {ENV_USERNAME, ENV_PASSWORD, "SYSTEMROOT"} <= names
    assert not names & {"SPRING_PROFILES_ACTIVE", "JAVA_TOOL_OPTIONS", "SERVER_PORT", "PATH", "CLASSPATH"}


def test_early_exit_is_reported_with_masked_output(started):
    process, port = started("exit")
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready(timeout=30)
    error = info.value
    assert error.reason == hgs2_launch.REASON_EXITED and "çıkış kodu 3" in str(error)
    assert any("Starting HgsApplication" in line for line in error.log_tail)
    assert all(SECRET not in line for line in error.log_tail) and SECRET not in str(error)
    assert listeners(port) == []


@pytest.mark.parametrize("mode, shown", [("wildcard", "0.0.0.0:"), ("extra", "127.0.0.1:")])
def test_unexpected_listener_stops_the_process_and_frees_the_port(started, mode, shown):
    process, port = started(mode)
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready(timeout=30)
    assert info.value.reason == hgs2_launch.REASON_LISTENER and shown in str(info.value)
    assert "süreç durduruldu" in str(info.value)
    assert listeners(pid=process.pid) == [] and not process.is_alive()


def test_missing_guard_message_times_out_and_stops(started):
    process, port = started("silent")
    with pytest.raises(Hgs2LaunchError) as info:
        process.wait_until_ready(timeout=2)
    assert info.value.reason == hgs2_launch.REASON_TIMEOUT and "güvenlik koruması" in str(info.value)
    assert listeners(port) == []


def test_busy_port_is_refused_and_the_other_listener_is_left_alone(tmp_path):
    other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    other.bind(("127.0.0.1", 0))
    other.listen()
    port = other.getsockname()[1]
    try:
        with pytest.raises(Hgs2LaunchError) as info:
            Hgs2Process.start([PYTHON, "-I", "-c", _CHILD, "ok", str(port)], cwd=tmp_path, env=child_env(),
                              secrets=[SECRET], expected=("127.0.0.1", port))
        assert info.value.reason == hgs2_launch.REASON_PORT_BUSY and str(os.getpid()) in str(info.value)
        assert [s.pid for s in listeners(port)] == [os.getpid()]  # başka süreç (burada test süreci) dokunulmadı
    finally:
        other.close()


def test_job_object_terminates_child_processes_too(started):
    process, _ = started("grandchild")
    process.wait_until_ready(timeout=30)
    [line] = [line for line in process.log_tail() if line.startswith("GRANDCHILD ")]
    _, grandchild_pid, grandchild_port = line.split()
    grandchild_pid, grandchild_port = int(grandchild_pid), int(grandchild_port)
    assert [s.pid for s in listeners(grandchild_port)] == [grandchild_pid]
    assert process.stop().ok
    assert wait_until(lambda: listeners(grandchild_port) == [])  # iş nesnesi alt süreci de sonlandırdı


def test_missing_executable_is_a_start_failure(tmp_path):
    missing = tmp_path / "jdk" / "bin" / "java.exe"
    with pytest.raises(Hgs2LaunchError) as info:
        Hgs2Process.start([str(missing), "-jar", "x.jar"], cwd=tmp_path, env=child_env(), secrets=[SECRET],
                          expected=("127.0.0.1", free_port()))
    assert info.value.reason == hgs2_launch.REASON_START and SECRET not in str(info.value)

