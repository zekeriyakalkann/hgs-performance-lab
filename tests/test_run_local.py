"""`hgs2-lab run` uçtan uca entegrasyon testleri: gerçek RequestsTransport, gerçek soket, yerel sunucu.

Varsayılan çalıştırmada hariçtir; `pytest -m integration` ile seçilir.

Ağ sınırı (bkz. test_http_transport_local.py): sunucu yalnızca 127.0.0.1'e bind eder; her testte
`install_network_guard`, 127.0.0.1 dışındaki her bağlantı girişimini bağlantı kurulmadan reddeder ve
kaydeder. Dış adresler (203.0.113.0/24, 2001:db8::/32 belge aralıkları) yalnızca reddedilmesi beklenen
değerler olarak kullanılır. Gizli değerler sahtedir.
"""

import json

import pytest
from local_http_server import ERROR_BODY, HELLO_BODY, LOOPBACK, LocalHTTPServer, install_network_guard

from hgs2_lab import execution
from hgs2_lab.cli import EXIT_ABORTED, EXIT_OK, EXIT_REJECTED, main
from hgs2_lab.config import load_config
from hgs2_lab.execution import STATUS_ABORTED, execute_run
from hgs2_lab.http_transport import RequestsTransport
from hgs2_lab.scenarios import Scenario, load_scenarios
from hgs2_lab.storage import ResultStore
from hgs2_lab.target_guard import TargetNotAllowed

pytestmark = pytest.mark.integration

FAKE = "FAKE-SECRET-123"
READ_TIMEOUT = 1.0


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked_sockets = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked_sockets:
        sock.close()


@pytest.fixture(autouse=True)
def fixed_code_info(monkeypatch):
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})


@pytest.fixture(scope="module")
def _module_server():
    srv = LocalHTTPServer()
    assert srv.server_address[0] == LOOPBACK
    srv.start()
    yield srv
    leftovers = srv.stop()
    assert leftovers == [], f"Kapanmayan thread'ler: {leftovers}"
    assert srv.is_closed
    assert srv.unexpected_errors() == []


@pytest.fixture
def server(_module_server):
    _module_server.reset()
    yield _module_server
    _module_server.release_stalled()


def write_project(tmp_path, base_url, scenarios, **config_extra):
    (tmp_path / "scenarios.json").write_text(json.dumps({"scenarios": scenarios}), encoding="utf-8")
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"base_url": base_url, "timeout_seconds": 5, "output_dir": "results",
                               "scenarios_file": "scenarios.json", **config_extra}), encoding="utf-8")
    return cfg


def result_files(tmp_path):
    return sorted(p.name for p in (tmp_path / "results").iterdir())


def test_cli_run_end_to_end_against_local_server(tmp_path, server, capsys, block_external_network):
    cfg = write_project(tmp_path, server.base_url, [
        {"name": "hello", "method": "GET", "path": f"/hello?page=1&token={FAKE}", "repetitions": 3,
         "warmup_repetitions": 1, "headers": {"Authorization": f"Bearer {FAKE}"}},
        {"name": "echo", "method": "POST", "path": "/echo", "body": {"password": FAKE, "n": 1}},
        {"name": "error", "method": "GET", "path": "/error", "repetitions": 2},
    ])
    assert main(["run", "--config", str(cfg), "--target-label", "yerel-entegrasyon"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "durum: completed" in out and "planlanan 7, tamamlanan 7 (ısınma 1, ölçüm 6)" in out

    (json_name,) = [n for n in result_files(tmp_path) if n.endswith(".json")]
    run_id = json_name[: -len(".json")]
    assert result_files(tmp_path) == [f"{run_id}.csv", f"{run_id}.json"]  # .partial yok
    store = ResultStore(tmp_path / "results")
    stored = store.load_json(run_id)
    assert stored.results == store.load_csv(run_id)

    meta = stored.metadata
    assert meta["schema_version"] == 2 and meta["run_id"] == run_id
    assert meta["target_label"] == "yerel-entegrasyon"
    assert meta["execution"]["status"] == "completed" and meta["execution"]["completed_requests"] == 7
    assert meta["monotonic_duration_ms"] > 0
    assert meta["inputs"]["config_sha256"] and meta["inputs"]["scenarios_sha256"]

    hello = [r for r in stored.results if r.scenario == "hello"]
    assert [r.warmup for r in hello] == [True, False, False, False]
    assert all(r.status_code == 200 and r.response_bytes == len(HELLO_BODY) for r in hello)
    errors = [r for r in stored.results if r.scenario == "error"]
    assert all((r.status_code, r.http_ok, r.error_type) == (500, False, None) for r in errors)  # taşıma hatası değil
    assert all(r.response_bytes == len(ERROR_BODY) for r in errors)
    assert [r.seq for r in stored.results] == list(range(1, 8))

    for name in result_files(tmp_path):  # gizli değer ve mutlak yerel yol sızmaz
        text = (tmp_path / "results" / name).read_text(encoding="utf-8")
        assert FAKE not in text
        assert str(tmp_path) not in text and json.dumps(str(tmp_path))[1:-1] not in text
    assert ("GET", f"/hello?page=1&token={FAKE}") in server.requests_seen()  # istek ham değerle gitti
    assert block_external_network == []


def test_cli_run_stops_on_consecutive_timeouts_and_keeps_partial_results(tmp_path, server, capsys):
    cfg = write_project(tmp_path, server.base_url,
                        [{"name": "stall", "method": "GET", "path": "/stall-headers", "repetitions": 5}],
                        timeout_seconds=READ_TIMEOUT, limits={"max_consecutive_transport_errors": 2})
    assert main(["run", "--config", str(cfg)]) == EXIT_ABORTED
    captured = capsys.readouterr()
    assert "durum: aborted" in captured.out and "tamamlanmadı" in captured.err
    names = result_files(tmp_path)
    assert len(names) == 2 and all(".partial." in n for n in names)
    run_id = names[0].split(".partial.")[0]
    stored = ResultStore(tmp_path / "results").load_json(run_id, partial=True)
    assert stored.metadata["execution"]["stop_reason"] == "consecutive_transport_errors"
    assert [r.error_type for r in stored.results] == ["timeout", "timeout"]
    assert len(server.requests_seen()) == 2  # kalan 3 istek gönderilmedi


@pytest.mark.parametrize("base_url", ["http://203.0.113.5:8080", "http://[2001:db8::1]:8080"])
def test_cli_run_rejects_non_loopback_without_any_connection_attempt(tmp_path, capsys, block_external_network,
                                                                     base_url):
    cfg = write_project(tmp_path, base_url, [{"name": "a", "method": "GET", "path": "/hello"}])
    assert main(["run", "--config", str(cfg)]) == EXIT_REJECTED
    assert "hiçbir istek gönderilmedi" in capsys.readouterr().err
    assert block_external_network == []  # bağlantı girişimi bile olmadı
    assert not (tmp_path / "results").exists()


def test_localhost_name_connects_only_to_validated_loopback_address(tmp_path, server):
    # Ad 'localhost' kalır (Host başlığı); soket yalnızca doğrulanmış 127.0.0.1'e açılır.
    url = f"http://localhost:{server.port}/hello"
    with RequestsTransport(resolver=lambda host, port: ["127.0.0.1"]) as transport:
        response = transport.send(Scenario(name="s", method="GET", path="/hello"), url, 5.0)
    assert response.status_code == 200 and response.body == HELLO_BODY


def test_dns_rebinding_between_checks_is_blocked_before_connecting(tmp_path, server, block_external_network):
    """İlk iki çözümleme (ön kontrol ve send) loopback, bağlantı anındaki çözümleme dış adres döner."""
    answers = iter([["127.0.0.1"], ["127.0.0.1"]])

    def rebinding(host, port):
        return next(answers, ["203.0.113.5"])

    cfg = write_project(tmp_path, f"http://localhost:{server.port}",
                        [{"name": "a", "method": "GET", "path": "/hello", "repetitions": 3}])
    config = load_config(cfg)
    outcome = execute_run(config, load_scenarios(config.scenarios_file), config_path=cfg, resolver=rebinding)
    assert outcome.status == STATUS_ABORTED and outcome.stop_reason == "target_not_allowed"
    assert outcome.results == [] and outcome.json_path.name.endswith(".partial.json")
    assert server.requests_seen() == []  # sunucuya hiçbir istek ulaşmadı
    assert block_external_network == []  # dış adrese bağlantı girişimi bile olmadı


def test_transport_rejects_rebinding_at_connection_layer_directly(server, block_external_network):
    answers = iter([["127.0.0.1"]])  # send içindeki kontrol geçer; bağlantı anında dış adres

    def rebinding(host, port):
        return next(answers, ["203.0.113.5"])

    with RequestsTransport(resolver=rebinding) as transport:
        with pytest.raises(TargetNotAllowed, match="203.0.113.5"):
            transport.send(Scenario(name="s", method="GET", path="/hello"), f"http://localhost:{server.port}/hello", 5.0)
    assert server.requests_seen() == [] and block_external_network == []
