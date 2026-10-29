"""Yerel web arayüzü (`webui.py`): bağlanma adresi, senaryo listesi, açık kullanıcı eylemi, sonuç gösterimi, kapanış.

Sunucu bu test sürecinde 127.0.0.1'e bağlanır; istemci `http.client` ile yalnızca ona bağlanır (proxy/ortam okunmaz).
Gerçek deney çalıştıran uçtan uca test `integration` işaretlidir (uygulamanın kendi sentetik sunucusu, 127.0.0.1).
"""

import http.client
import re
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from hgs2_lab import execution, webui
from hgs2_lab.analysis import build_analysis
from hgs2_lab.reader import load_run
from hgs2_lab.result_analysis import build_run_document, resolve_dataset_kind

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "configs"
GOLDEN = Path(__file__).resolve().parent / "golden" / "v2-a1331fd"


class FakeRunner:
    """run_synthetic_experiment yerine: çağrıları kaydeder, isteğe bağlı olarak bir olayı bekler."""

    def __init__(self, gate: threading.Event | None = None) -> None:
        self.calls: list[tuple[Path, Path]] = []
        self.gate = gate

    def __call__(self, manifest_path, *, results_dir):
        self.calls.append((Path(manifest_path), Path(results_dir)))
        if self.gate is not None:
            self.gate.wait(10)
        return SimpleNamespace(run=SimpleNamespace(run_id="fake-run", status="completed"), valid=True)


@pytest.fixture
def dirs(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    for name in ("synthetic.example.json", "scenarios.example.json", "campaign.example.json", "config.example.json"):
        shutil.copy(CONFIGS / name, configs / name)
    results = tmp_path / "results"
    results.mkdir()
    return configs, results


@pytest.fixture
def serve():
    started = []

    def start(configs, results, runner):
        ui = webui.LabUI(configs, results, port=0, runner=runner)
        server = webui.make_server(ui)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread, ui))
        return ui

    yield start
    for server, thread, ui in started:
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert ui.manager.close(10)


def request(ui, method, path, *, form=None, host=None, headers=None):
    conn = http.client.HTTPConnection(webui.HOST, ui.port, timeout=30)
    body = urlencode(form) if form is not None else None
    all_headers = {"Host": host or f"{webui.HOST}:{ui.port}", **(headers or {})}
    if body is not None:
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=all_headers)
    response = conn.getresponse()
    text = response.read().decode("utf-8")
    conn.close()
    return response.status, text, response


def copy_golden(results, partial=False):
    stem = "golden-v2-a1331fd-aborted.partial" if partial else "golden-v2-a1331fd-completed"
    for suffix in (".csv", ".json"):
        shutil.copy(GOLDEN / f"{stem}{suffix}", results / f"{stem}{suffix}")
    return stem.replace(".partial", "")


def cells(text):
    return [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td>(.*?)</td>", text)]


# --- 1. yerel başlatma ---
def test_server_binds_only_loopback(dirs, serve):
    ui = serve(*dirs, FakeRunner())
    assert webui.HOST == "127.0.0.1"
    status, text, _ = request(ui, "GET", "/")
    assert status == 200 and "HGS2 Performance Lab" in text


@pytest.mark.parametrize("port", [8080, 5432])
def test_reserved_ports_rejected(dirs, port):
    with pytest.raises(ValueError, match="ayrılmış"):
        webui.make_server(webui.LabUI(*dirs, port=port))


def test_main_has_no_host_option():
    with pytest.raises(SystemExit):
        webui.main(["--host", "0.0.0.0"])


# --- 2. ana sayfa ---
def test_dashboard_without_runs_says_so(dirs, serve):
    configs, results = dirs
    runner = FakeRunner()
    ui = serve(configs, results, runner)
    status, text, _ = request(ui, "GET", "/")
    assert status == 200
    assert "çalışıyor" in text
    assert "Henüz test çalıştırılmadı" in text
    # örnek manifestte 6 senaryo, örnek HTTP dosyasında 1 senaryo, 1 kampanya
    assert cells(text)[:8] == ["Sentetik deney manifesti", "1", "6", "1 dosya", "HTTP senaryo dosyası", "1", "1", "hayır"]
    assert runner.calls == []


def test_dashboard_shows_latest_run(dirs, serve):
    configs, results = dirs
    run_id = copy_golden(results)
    ui = serve(configs, results, FakeRunner())
    _, text, _ = request(ui, "GET", "/")
    assert "Henüz test çalıştırılmadı" not in text
    assert run_id in text and "completed" in text


def test_wrong_host_header_rejected(dirs, serve):
    ui = serve(*dirs, FakeRunner())
    status, _, _ = request(ui, "GET", "/", host=f"evil.example:{ui.port}")
    assert status == 400


# --- 3. senaryolar ---
def test_scenarios_listed_with_runnable_state(dirs, serve):
    ui = serve(*dirs, FakeRunner())
    status, text, _ = request(ui, "GET", "/scenarios")
    assert status == 200
    for name in ("baseline", "latency-fixed", "latency-random", "http-503-after-3", "connection-drop",
                 "client-timeout", "placeholder-get", "syn-fault-mix-001", "camp-mix-001"):
        assert name in text
    assert text.count("Deneyi başlat") == 1  # yalnızca sentetik manifest
    assert text.count("arayüzden çalıştırılamaz") == 2  # HTTP senaryoları + kampanya
    assert "config.example.json" not in text  # yapılandırma dosyası senaryo değildir


def test_invalid_manifest_shown_not_runnable(dirs, serve):
    configs, results = dirs
    (configs / "synthetic.bad.json").write_text('{"manifest_version": 1, "experiment_id": "x"}', encoding="utf-8")
    ui = serve(configs, results, FakeRunner())
    _, text, _ = request(ui, "GET", "/scenarios")
    assert "synthetic.bad.json" in text and "geçersiz" in text
    assert text.count("Deneyi başlat") == 1


# --- 4. açık kullanıcı eylemi ---
def test_get_requests_never_start_a_run(dirs, serve):
    runner = FakeRunner()
    ui = serve(*dirs, runner)
    for path in ("/", "/scenarios", "/runs", "/run", "/scenarios?manifest=synthetic.example.json"):
        request(ui, "GET", path)
    assert runner.calls == []
    assert ui.manager.state() == {"status": "idle"}


def test_post_requires_token_host_and_origin(dirs, serve):
    runner = FakeRunner()
    ui = serve(*dirs, runner)
    form = {"manifest": "synthetic.example.json"}
    assert request(ui, "POST", "/run", form=form)[0] == 403
    assert request(ui, "POST", "/run", form={**form, "token": "yanlis"})[0] == 403
    assert request(ui, "POST", "/run", form={**form, "token": ui.token}, host="evil.example")[0] == 400
    assert request(ui, "POST", "/run", form={**form, "token": ui.token},
                   headers={"Origin": "http://evil.example"})[0] == 403
    assert runner.calls == []


def test_post_only_runs_catalog_synthetic_manifest(dirs, serve):
    configs, results = dirs
    runner = FakeRunner()
    ui = serve(configs, results, runner)
    for name in ("../pyproject.toml", str(CONFIGS / "synthetic.example.json"), "yok.json"):
        assert request(ui, "POST", "/run", form={"manifest": name, "token": ui.token})[0] == 404
    for name in ("scenarios.example.json", "campaign.example.json"):
        assert request(ui, "POST", "/run", form={"manifest": name, "token": ui.token})[0] == 409
    assert runner.calls == []

    status, _, response = request(ui, "POST", "/run", form={"manifest": "synthetic.example.json", "token": ui.token},
                                  headers={"Origin": f"http://{webui.HOST}:{ui.port}"})
    assert status == 303 and response.getheader("Location") == "/scenarios?m=started"
    assert ui.manager.close(10)
    assert runner.calls == [((configs / "synthetic.example.json").resolve(), results)]
    state = ui.manager.state()
    assert state["status"] == "finished" and state["run_id"] == "fake-run"


def test_only_one_run_at_a_time(dirs, serve):
    gate = threading.Event()
    runner = FakeRunner(gate)
    ui = serve(*dirs, runner)
    form = {"manifest": "synthetic.example.json", "token": ui.token}
    assert request(ui, "POST", "/run", form=form)[0] == 303
    status, text, _ = request(ui, "POST", "/run", form=form)
    assert status == 409 and "zaten çalışıyor" in text
    _, page, _ = request(ui, "GET", "/scenarios")
    assert 'http-equiv="refresh"' in page and "disabled" in page
    gate.set()
    assert ui.manager.close(10)
    assert len(runner.calls) == 1


def test_preflight_rejection_reported(dirs, serve):
    def rejecting(manifest_path, *, results_dir):
        raise execution.PreflightError("Hedef reddedildi: token=GIZLI-DEGER-123")

    ui = serve(*dirs, rejecting)
    assert request(ui, "POST", "/run", form={"manifest": "synthetic.example.json", "token": ui.token})[0] == 303
    assert ui.manager.close(10)
    state = ui.manager.state()
    assert state["status"] == "error" and "hiçbir istek gönderilmedi" in state["message"]
    _, text, _ = request(ui, "GET", "/")
    assert "GIZLI-DEGER-123" not in text and "***REDACTED***" in text


# --- 5. sonuç gösterimi ---
def test_run_page_matches_existing_analysis_and_classifier(dirs, serve):
    configs, results = dirs
    run_id = copy_golden(results)
    ui = serve(configs, results, FakeRunner())
    status, text, _ = request(ui, "GET", f"/runs/{run_id}")
    assert status == 200

    run = load_run(results, run_id)
    overall = build_analysis(run)["overall"]
    summary = build_run_document(run, dataset_kind=resolve_dataset_kind(run, None))["classification"]["summary"]
    table = cells(text)
    assert "completed" in text and "2026-10-23T10:00:01.000000+00:00" in text
    median = overall["response_time_ms"]["median"]["value"]
    assert f"{median:.2f}" in table
    rate = overall["rates"]["failure_rate"]
    assert f"%{rate * 100:.1f}" in table
    for name, count in summary["by_classification"].items():
        index = table.index(name)
        assert table[index + 1] == str(count)
    assert "yetersiz örneklem" in text  # p90+ küçük örneklemde hesaplanmış gibi gösterilmez
    assert "FAKE-GOLDEN-TOKEN" not in text and "token=" not in text  # URL'ler gösterilmez


def test_partial_run_and_listing(dirs, serve):
    configs, results = dirs
    complete = copy_golden(results)
    partial = copy_golden(results, partial=True)
    ui = serve(configs, results, FakeRunner())
    _, listing, _ = request(ui, "GET", "/runs")
    assert complete in listing and partial in listing and "(kısmi)" in listing
    _, text, _ = request(ui, "GET", f"/runs/{partial}")
    assert "aborted" in text


def test_unknown_or_invalid_run_id(dirs, serve):
    ui = serve(*dirs, FakeRunner())
    assert request(ui, "GET", "/runs/yok")[0] == 404
    assert request(ui, "GET", "/runs/..%2F..%2Fpyproject")[0] == 404


# --- 6. kapanış ---
def test_close_waits_for_running_experiment_and_refuses_new(dirs):
    gate = threading.Event()
    runner = FakeRunner(gate)
    manager = webui.RunManager(dirs[1], runner)
    entry = next(e for e in webui.scan_catalog(dirs[0]) if e.kind == webui.KIND_SYNTHETIC)
    assert manager.start(entry) == (True, "Deney başlatıldı")
    assert manager.close(0.1) is False and manager.running  # kesilmez, beklenir
    assert manager.start(entry)[0] is False
    gate.set()
    assert manager.close(10) is True and not manager.running
    assert len(runner.calls) == 1


def test_main_ctrl_c_waits_for_running_experiment(dirs, monkeypatch, capsys):
    configs, results = dirs
    gate = threading.Event()
    runner = FakeRunner(gate)
    monkeypatch.setattr(webui, "run_synthetic_experiment", runner)
    real_make_server = webui.make_server
    holder = {}

    class InterruptedServer:
        """Gerçek sunucu bağlanır; serve_forever bir deney başlatıp Ctrl+C'yi taklit eder."""

        def __init__(self, ui):
            self.ui, self.real = ui, real_make_server(ui)
            holder["ui"] = ui

        def serve_forever(self):
            entry = next(e for e in webui.scan_catalog(self.ui.configs_dir) if e.kind == webui.KIND_SYNTHETIC)
            assert self.ui.manager.start(entry)[0]
            threading.Timer(0.3, gate.set).start()
            raise KeyboardInterrupt

        def server_close(self):
            self.real.server_close()

    monkeypatch.setattr(webui, "make_server", InterruptedServer)
    assert webui.main(["--port", "0", "--configs-dir", str(configs), "--results-dir", str(results)]) == 0
    assert gate.is_set() and not holder["ui"].manager.running  # main deney bitmeden dönmedi
    assert holder["ui"].manager.state()["status"] == "finished"
    out, err = capsys.readouterr()
    assert "http://127.0.0.1:" in out and "Arayüz kapatıldı" in out
    assert "bitmesi bekleniyor" in err


def test_worker_thread_is_not_daemon(dirs):
    gate = threading.Event()
    manager = webui.RunManager(dirs[1], FakeRunner(gate))
    entry = next(e for e in webui.scan_catalog(dirs[0]) if e.kind == webui.KIND_SYNTHETIC)
    manager.start(entry)
    worker = next(t for t in threading.enumerate() if t.name == "hgs2-ui-run")
    assert worker.daemon is False  # yorumlayıcı çıkışta yarıda bırakmaz
    gate.set()
    assert manager.close(10)


# --- 7. hedef güvenliği: gerçek deney mevcut akıştan geçer (integration) ---
@pytest.mark.integration
def test_end_to_end_synthetic_run_via_ui(dirs, serve, monkeypatch):
    configs, results = dirs
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})
    ui = serve(configs, results, webui.run_synthetic_experiment)
    assert request(ui, "POST", "/run", form={"manifest": "synthetic.example.json", "token": ui.token})[0] == 303
    deadline = time.monotonic() + 60
    while ui.manager.running and time.monotonic() < deadline:
        time.sleep(0.1)
    state = ui.manager.state()
    assert state["status"] == "finished", state
    run = load_run(results, state["run_id"])
    # Mevcut hedef doğrulaması uygulandı: hedef bu sürecin kendi sentetik sunucusu.
    assert run.metadata["execution"]["target_verification"]["listener"] == "in_process"
    assert run.metadata["config"]["base_url"].startswith("http://127.0.0.1:")
    _, text, _ = request(ui, "GET", f"/runs/{state['run_id']}")
    assert "Sentetik etiketler" in text and "completed" in text
    labels_row = cells(text)
    assert ["55", "55", "0", "0", "evet"] == labels_row[labels_row.index("55"):labels_row.index("55") + 5]
    _, dash, _ = request(ui, "GET", "/")
    assert state["run_id"] in dash and "Henüz test çalıştırılmadı" not in dash
