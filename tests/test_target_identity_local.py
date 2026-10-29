"""N12 (F-3) entegrasyon testleri: gerçek işletim sistemi dinleyici tablosu (Windows) ile hedef kimliği denetimi.

Varsayılan çalıştırmada hariçtir (`pytest -m integration`). Dinleyiciler bu test sürecinde ya da bu testin başlattığı
bir Python alt sürecinde 127.0.0.1'de geçici portta açılır. Alt sürece HİÇBİR HTTP isteği gönderilmez: yalnızca hedef
doğrulaması (istek öncesi denetim) sınanır. Gerçek HGS2'ye, PostgreSQL'e veya dış ağa bağlanılmaz; tablo okumak ağ
trafiği üretmez.
"""

import json
import os
import socket
import subprocess
import sys

import isolation_guard
import pytest
from local_http_server import LOOPBACK, LocalHTTPServer, install_network_guard

from hgs2_lab import execution
from hgs2_lab.cli import EXIT_OK, main
from hgs2_lab.http_transport import RequestsTransport
from hgs2_lab.port_owner import system_listener_lookup
from hgs2_lab.reader import load_run
from hgs2_lab.target_guard import LISTENER_DECLARED_EXTERNAL, LISTENER_IN_PROCESS, TargetNotAllowed

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(sys.platform != "win32", reason="dinleyici tablosu yalnızca Windows'ta okunur")]

_CHILD = ("import socket, sys\n"
          "port = int(sys.argv[1])\n"
          "s = socket.socket(); s.bind(('127.0.0.1', port)); s.listen()\n"
          "print(s.getsockname()[1], flush=True)\n"
          "sys.stdin.read()\n")


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked_sockets = install_network_guard(monkeypatch)
    yield attempts
    assert attempts == []
    for sock in blocked_sockets:
        sock.close()


@pytest.fixture
def child_listener():
    """Başka bir süreçte (Python) dinleyen soket başlatır; (port, süreç) döndürür. İstek gönderilmez."""
    procs = []

    def start(port=0):
        proc = subprocess.Popen([sys.executable, "-c", _CHILD, str(port)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True)
        procs.append(proc)
        return int(proc.stdout.readline()), proc

    yield start
    for proc in procs:
        proc.stdin.close()
        proc.wait(timeout=10)


def test_own_listener_is_reported_with_own_pid():
    srv = LocalHTTPServer()
    try:
        owners = system_listener_lookup(srv.port)
        assert {(o.pid, o.process_name.lower(), o.address) for o in owners} == {
            (os.getpid(), os.path.basename(sys.executable).lower(), LOOPBACK)}
    finally:
        srv.stop()
    assert system_listener_lookup(srv.port) == []


def test_other_process_listener_requires_explicit_declaration(child_listener):
    port, _ = child_listener()
    [listener] = system_listener_lookup(port)
    # Not: venv'in python.exe'si Windows'ta asıl yorumlayıcıyı alt süreç olarak başlatır; PID Popen.pid olmayabilir.
    assert listener.pid != os.getpid() and listener.process_name.lower() == os.path.basename(sys.executable).lower()
    url = f"http://{LOOPBACK}:{port}/"
    with RequestsTransport(resolver=lambda h, p: [LOOPBACK]) as transport:
        with pytest.raises(TargetNotAllowed, match="target_process"):
            transport.verify_target(url)
    with RequestsTransport(resolver=lambda h, p: [LOOPBACK], target_process="node.exe") as transport:
        with pytest.raises(TargetNotAllowed, match="eşleşmiyor"):
            transport.verify_target(url)
    name = os.path.basename(sys.executable)
    with RequestsTransport(resolver=lambda h, p: [LOOPBACK], target_process=name) as transport:
        assert transport.verify_target(url) == {"port": port, "listener": LISTENER_DECLARED_EXTERNAL}


def test_run_against_undeclared_external_listener_sends_nothing(tmp_path, child_listener, capsys):
    port, _ = child_listener()
    (tmp_path / "scenarios.json").write_text(json.dumps({"scenarios": [{"name": "a", "method": "GET", "path": "/"}]}),
                                             encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"base_url": f"http://{LOOPBACK}:{port}", "output_dir": "results",
                                  "scenarios_file": "scenarios.json"}), encoding="utf-8")
    assert main(["run", "--config", str(config)]) != EXIT_OK
    assert "target_process" in capsys.readouterr().err
    assert not (tmp_path / "results").exists()


def test_session_guard_blocks_released_port_taken_by_another_process(child_listener, isolation_violations):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((LOOPBACK, 0))
    port = sock.getsockname()[1]
    sock.close()  # bu süreç portu bıraktı
    assert port in isolation_guard.released_ports()
    taken, _ = child_listener(port)  # aynı portu başka bir süreç (ör. gerçek HGS2 olabilirdi) dinlemeye başladı
    assert taken == port
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(isolation_guard.OutOfProcessConnectionBlocked):
            probe.connect((LOOPBACK, port))
    finally:
        probe.close()
    assert [a for a, _ in isolation_violations] == [(LOOPBACK, port)]
    isolation_violations.clear()  # bilinçli girişim


def test_session_guard_allows_released_port_with_no_listener(isolation_violations):
    srv = LocalHTTPServer()
    port = srv.port
    srv.start()
    assert srv.stop() == []
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(3)
    try:
        assert probe.connect_ex((LOOPBACK, port)) != 0  # izinli; işletim sistemi reddeder (ya da zaman aşımı)
    finally:
        probe.close()
    assert isolation_violations == []


def test_completed_run_records_in_process_target_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})
    srv = LocalHTTPServer()
    srv.start()
    try:
        (tmp_path / "scenarios.json").write_text(json.dumps({"scenarios": [
            {"name": "hello", "method": "GET", "path": "/hello", "repetitions": 2}]}), encoding="utf-8")
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"base_url": srv.base_url, "output_dir": "results",
                                      "scenarios_file": "scenarios.json"}), encoding="utf-8")
        assert main(["run", "--config", str(config)]) == EXIT_OK
    finally:
        srv.release_stalled()
        assert srv.stop() == []
    [json_file] = (tmp_path / "results").glob("*.json")
    run = load_run(tmp_path / "results", json_file.stem)
    assert run.execution["target_verification"] == {"port": srv.port, "listener": LISTENER_IN_PROCESS}
