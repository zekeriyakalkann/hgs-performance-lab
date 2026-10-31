"""N11 entegrasyon testleri: gerçek RequestsTransport + süreç içi yerel sunucu (HGS2 BİÇİMLİ sentetik yanıtlar).

Varsayılan çalıştırmada hariçtir; `pytest -m integration` ile seçilir. Bu testler gerçek HGS2 ile canlı entegrasyon
testi DEĞİLDİR: sunucu bu test sürecinde, 127.0.0.1'de geçici bir portta çalışır ve yalnızca HGS2 kaynak kodundan
statik olarak çıkarılan yanıt biçimlerini taklit eder. Ağ sınırları:
* `install_network_guard`: 127.0.0.1 dışındaki her bağlantı kurulmadan reddedilir;
* conftest (isolation_guard): bu sürecin bind etmediği hiçbir porta (ör. gerçek HGS2 8080) bağlanılamaz.
"""

import json
import socket

import isolation_guard
import pytest
from local_http_server import (
    BUSINESS_SECRET,
    EXTERNAL_REDIRECT_TARGET,
    LOOPBACK,
    LocalHTTPServer,
    install_network_guard,
)

from hgs2_lab import execution
from hgs2_lab.cli import EXIT_OK, main
from hgs2_lab.config import LabConfig
from hgs2_lab.execution import PreflightError, execute_run
from hgs2_lab.http_transport import RequestsTransport
from hgs2_lab.reader import load_run
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import TransportConnectionError, TransportTimeout

pytestmark = pytest.mark.integration

# senaryo → (metot, yol, senaryo expected_status, beklenti, beklenen iş sonucu, ayrıştırma kuralı, sınıf, sınıf kuralı)
CASES = {
    "pending-none": ("GET", "/hgs2/sensor/pending-none", [], {"status_codes": [200], "business_outcomes": ["NONE"]},
                     "NONE", "R-TEXT-TOKEN", "PASS", "H-EXPECTED-MATCH"),
    "pending-card": ("GET", "/hgs2/sensor/pending-card", [], {"status_codes": [200], "business_outcomes": ["NONE"]},
                     "SCAN_CARD", "R-TEXT-TOKEN", "APPLICATION_FAILURE", "H-BUSINESS-MISMATCH"),
    "result-waiting": ("GET", "/hgs2/sensor/result-waiting", [],
                       {"status_codes": [200], "business_outcomes": ["WAITING", "READY"]},
                       "WAITING", "R-JSON-STATUS", "PASS", "H-EXPECTED-MATCH"),
    "result-ready-as-auth": ("GET", "/hgs2/sensor/result-ready", [],
                             {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
                             "READY", "R-JSON-STATUS", "APPLICATION_FAILURE", "H-BUSINESS-MISMATCH"),
    "start-status-only": ("POST", "/hgs2/sensor/start", [], {"status_codes": [200]},
                          None, "R-JSON-UNRECOGNIZED", "INCONCLUSIVE", "H-STATUS-OK-UNKNOWN-BODY"),
    "auth-onay": ("POST", "/hgs2/auth/kart-okut-onay", [], {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
                  "ONAYLANDI", "R-TEXT-TOKEN", "PASS", "H-EXPECTED-MATCH"),
    "auth-ret": ("POST", "/hgs2/auth/kart-okut-ret", [], {"status_codes": [200], "business_outcomes": ["ONAYLANDI"]},
                 "REDDEDILDI", "R-TEXT-TOKEN", "APPLICATION_FAILURE", "H-BUSINESS-MISMATCH"),
    "auth-ret-status-only": ("POST", "/hgs2/auth/kart-okut-ret", [], {"status_codes": [200]},
                             "REDDEDILDI", "R-TEXT-TOKEN", "INCONCLUSIVE", "H-STATUS-OK-NEGATIVE-BODY"),
    "auth-unknown": ("POST", "/hgs2/auth/unknown", [], {"status_codes": [200]},
                     None, "R-TEXT-UNRECOGNIZED", "INCONCLUSIVE", "H-STATUS-OK-UNKNOWN-BODY"),
    "auth-bad-request": ("POST", "/hgs2/auth/bad-request", [400], {"status_codes": [400]},
                         None, "R-JSON-UNRECOGNIZED", "PASS", "H-STATUS-MATCH"),
}


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked_sockets = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked_sockets:
        sock.close()


@pytest.fixture(autouse=True)
def fixed_code_info(monkeypatch):
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})


@pytest.fixture
def server():
    srv = LocalHTTPServer()
    assert srv.server_address[0] == LOOPBACK and srv.port in isolation_guard.bound_ports()
    srv.start()
    yield srv
    srv.release_stalled()
    assert srv.stop() == []
    assert srv.unexpected_errors() == []


@pytest.fixture
def connect_log(monkeypatch):
    """Bu testte denenen HER bağlantı hedefini kaydeder (koruma zincirini değiştirmeden)."""
    log = []
    inner = socket.socket.connect

    def recording(self, address):
        log.append(address[:2] if isinstance(address, tuple) else address)
        return inner(self, address)

    monkeypatch.setattr(socket.socket, "connect", recording)
    return log


def test_hgs2_shaped_responses_run_and_classify(tmp_path, server, capsys, block_external_network, connect_log):
    scenarios = [{"name": name, "method": method, "path": path, "repetitions": 1, "expected_status": status}
                 for name, (method, path, status, *_) in CASES.items()]
    (tmp_path / "scenarios.json").write_text(json.dumps({"scenarios": scenarios}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"base_url": server.base_url, "timeout_seconds": 2.0, "output_dir": "results",
                                  "scenarios_file": "scenarios.json"}), encoding="utf-8")
    assert main(["run", "--config", str(config), "--target-label", "n11-hgs2-bicimli-sentetik"]) == EXIT_OK
    [json_file] = (tmp_path / "results").glob("*.json")
    run = load_run(tmp_path / "results", json_file.stem)
    by_name = {r.scenario: r for r in run.results}
    parsing = {e["seq"]: e for e in run.metadata["response_parsing"]["requests"]}
    assert run.metadata["response_parsing"]["parser_version"] == "response-parser-v2"
    for name, (_, _, _, _, outcome, rule, _, _) in CASES.items():
        assert (by_name[name].business_outcome, parsing[by_name[name].seq]["rule_id"]) == (outcome, rule), name

    expectations = tmp_path / "expectations.json"
    expectations.write_text(json.dumps({"expectations_version": 1, "scenarios": {
        name: case[3] for name, case in CASES.items()}}), encoding="utf-8")
    out = tmp_path / "n11.classification.json"
    capsys.readouterr()
    assert main(["results", "classify", "--run-id", json_file.stem, "--results-dir", str(tmp_path / "results"),
                 "--expectations", str(expectations), "--output", str(out)]) == EXIT_OK
    captured = capsys.readouterr()
    records = {r["scenario_id"]: r for r in json.loads(out.read_text(encoding="utf-8"))["classification"]["records"]}
    for name, (*_, cls, rule) in CASES.items():
        analysis = records[name]["analysis"]
        assert (analysis["classification"], analysis["rule_ids"][0]) == (cls, rule), name

    # yalnızca süreç içi sunucuya bağlanıldı; gövdedeki sentetik değer hiçbir çıktıya yazılmadı
    assert set(connect_log) == {(LOOPBACK, server.port)} and block_external_network == []
    for path in (tmp_path / "results").iterdir():
        assert BUSINESS_SECRET not in path.read_text(encoding="utf-8")
    assert BUSINESS_SECRET not in out.read_text(encoding="utf-8") + captured.out + captured.err


def test_stopped_server_fails_as_transport_error_without_trying_another_target(tmp_path, connect_log):
    """Kapalı sunucu: tek girişim, aynı adres ve port; yeniden deneme veya başka hedef yok.

    Hata türü platforma bağlıdır: Windows'ta kapalı loopback portuna bağlanma reddi işletim sisteminin bağlantı
    yeniden denemeleri nedeniyle gecikir ve kısa zaman aşımında `timeout` olarak görülebilir (N11'de gözlendi);
    reddi zaman aşımından önce gelirse `connection_error` olur. İkisi de taşıma hatasıdır, HTTP yanıtı değildir.
    """
    srv = LocalHTTPServer()
    port = srv.port
    srv.start()
    assert srv.stop() == []  # sunucu kapalı: port bu süreçte bind edilmişti, artık dinlemiyor
    with RequestsTransport(resolver=lambda h, p: [LOOPBACK]) as transport:
        with pytest.raises((TransportConnectionError, TransportTimeout)):
            transport.send(Scenario(name="s", method="GET", path="/hello"), f"http://localhost:{port}/hello", 1.0)
    assert connect_log == [(LOOPBACK, port)]  # tek girişim: yeniden deneme, başka port/adres yok

    # N12: çalıştırma, hedef portu dinleyen bir süreç yoksa hedefin kimliğini doğrulayamaz; istek göndermeden reddedilir.
    connect_log.clear()
    (tmp_path / "scenarios.json").write_text('{"scenarios": []}', encoding="utf-8")
    config = LabConfig(base_url=f"http://{LOOPBACK}:{port}", output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json", timeout_seconds=1.0)
    with pytest.raises(PreflightError, match="dinleyen süreç bulunamadı"):
        execute_run(config, [Scenario(name="a", method="GET", path="/hello", repetitions=10)], config_path=None,
                    resolver=lambda h, p: [LOOPBACK])
    assert connect_log == [] and not (tmp_path / "results").exists()


def test_external_redirect_is_reported_not_followed(server, block_external_network, connect_log):
    with RequestsTransport() as transport:
        response = transport.send(Scenario(name="s", method="GET", path="/redirect-external"),
                                  f"{server.base_url}/redirect-external", 2.0)
    assert response.status_code == 302
    assert server.requests_seen() == [("GET", "/redirect-external")]
    assert set(connect_log) == {(LOOPBACK, server.port)} and block_external_network == []
    assert "203.0.113.5" in EXTERNAL_REDIRECT_TARGET


def test_session_guard_blocks_ports_not_opened_by_this_process(isolation_violations):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(isolation_guard.OutOfProcessConnectionBlocked):
            sock.connect((LOOPBACK, 0))  # port 0 hiçbir zaman bind kaydında olmaz; koruma bozuk olsa da bağlanamaz
    finally:
        sock.close()
    assert [a for a, _ in isolation_violations] == [(LOOPBACK, 0)]
    isolation_violations.clear()  # bilinçli girişim: testi başarısız saymamak için
