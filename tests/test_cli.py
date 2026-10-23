import json
import socket

import pytest

from hgs2_lab import execution
from hgs2_lab.cli import (
    EXIT_ABORTED,
    EXIT_ERROR,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_REJECTED,
    EXIT_STORAGE_ERROR,
    main,
)
from hgs2_lab.storage import ResultStore
from hgs2_lab.transport import TransportResponse, TransportTimeout

SCENARIO = {"name": "a", "method": "GET", "path": "/a", "expected_status": [200, 204]}


def setup_files(tmp_path, scenarios=None, config_extra=None):
    scen = tmp_path / "scen.json"
    scen.write_text(json.dumps({"scenarios": [SCENARIO] if scenarios is None else scenarios}), encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(
        json.dumps({"base_url": "http://localhost:8080", "scenarios_file": "scen.json", **(config_extra or {})}),
        encoding="utf-8",
    )
    return cfg


# --- validate / list (mevcut davranış) ---
def test_validate_ok_reports_resolved_paths(tmp_path, capsys):
    assert main(["validate", "--config", str(setup_files(tmp_path))]) == EXIT_OK
    out = capsys.readouterr().out
    assert "1 senaryo" in out
    assert str((tmp_path / "scen.json").resolve()) in out
    assert "hedef:" in out and "loopback (run için izinli" in out


def test_validate_reports_non_loopback_target_without_failing(tmp_path, capsys):
    cfg = setup_files(tmp_path, config_extra={"base_url": "http://203.0.113.5:8080"})
    assert main(["validate", "--config", str(cfg)]) == EXIT_OK
    assert "run bu hedefi reddeder" in capsys.readouterr().out


def test_list_prints_scenarios(tmp_path, capsys):
    assert main(["list", "--config", str(setup_files(tmp_path))]) == EXIT_OK
    out = capsys.readouterr().out
    assert "GET /a" in out and "200,204" in out


def test_scenarios_option_overrides_config_file(tmp_path, capsys):
    cfg = setup_files(tmp_path)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"scenarios": [{"name": "b", "method": "POST", "path": "/b"}]}), encoding="utf-8")
    assert main(["list", "--config", str(cfg), "--scenarios", str(other)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "POST /b" in out and "GET /a" not in out
    assert main(["validate", "--config", str(cfg), "--scenarios", str(other)]) == EXIT_OK
    assert str(other.resolve()) in capsys.readouterr().out


def test_relative_scenario_file_resolved_against_config_not_cwd(tmp_path, monkeypatch, capsys):
    cfg = setup_files(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert main(["validate", "--config", str(cfg)]) == EXIT_OK


def test_missing_config_returns_error(tmp_path, capsys):
    assert main(["validate", "--config", str(tmp_path / "yok.json")]) == EXIT_ERROR
    assert "Hata" in capsys.readouterr().err


def test_invalid_config_value_returns_error_without_traceback(tmp_path, capsys):
    cfg = setup_files(tmp_path, config_extra={"timeout_seconds": "abc"})
    assert main(["validate", "--config", str(cfg)]) == EXIT_ERROR
    assert "timeout_seconds" in capsys.readouterr().err


def test_empty_scenario_list_returns_error(tmp_path, capsys):
    assert main(["list", "--config", str(setup_files(tmp_path, scenarios=[]))]) == EXIT_ERROR
    assert "boş" in capsys.readouterr().err


def test_invalid_scenario_returns_error(tmp_path, capsys):
    cfg = setup_files(tmp_path, scenarios=[{**SCENARIO, "repetitions": 2.7}])
    assert main(["validate", "--config", str(cfg)]) == EXIT_ERROR
    assert "repetitions" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [[], ["bilinmeyen"], ["validate", "--nope"], ["run", "--nope"], ["list", "--target-label", "x"]],
)
def test_usage_errors_exit_with_argparse_code(argv):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_exit_codes_are_distinct():
    codes = [EXIT_OK, EXIT_ERROR, 2, EXIT_REJECTED, EXIT_ABORTED, EXIT_STORAGE_ERROR, EXIT_INTERRUPTED]
    assert len(set(codes)) == len(codes)


# --- run (sahte taşıyıcı; ağ yok) ---
class FakeTransport:
    instances = []

    def __init__(self, resolver=None, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.sent = []
        self.closed = False
        FakeTransport.instances.append(self)

    def send(self, scenario, url, timeout_seconds):
        self.sent.append(url)
        outcome = self.outcomes.pop(0) if self.outcomes else TransportResponse(200, 2)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


@pytest.fixture
def fake_transport(monkeypatch):
    """execute_run'ın varsayılan taşıyıcısını sahtesiyle değiştirir; Git sorgusunu sabitler; soketi yasaklar."""
    FakeTransport.instances = []
    outcomes = []
    monkeypatch.setattr(execution, "RequestsTransport", lambda resolver: FakeTransport(resolver, outcomes))
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})

    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    return outcomes


def run_config(tmp_path, scenarios=None, **extra):
    return setup_files(tmp_path, scenarios=scenarios,
                       config_extra={"base_url": "http://127.0.0.1:8080", "output_dir": "results", **extra})


def only_run_id(tmp_path, partial=False):
    suffix = ".partial.json" if partial else ".json"
    files = [p for p in (tmp_path / "results").glob("*.json") if p.name.endswith(suffix)
             and (partial or not p.name.endswith(".partial.json"))]
    assert len(files) == 1, files
    return files[0].name[: -len(suffix)]


def test_run_completes_and_reports_summary(tmp_path, capsys, fake_transport):
    cfg = run_config(tmp_path, scenarios=[{**SCENARIO, "repetitions": 3, "warmup_repetitions": 1}])
    assert main(["run", "--config", str(cfg), "--target-label", "yerel-test"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "durum: completed" in out and "planlanan 4, tamamlanan 4 (ısınma 1, ölçüm 3)" in out
    run_id = only_run_id(tmp_path)
    stored = ResultStore(tmp_path / "results").load_json(run_id)
    assert stored.metadata["target_label"] == "yerel-test"
    assert stored.metadata["execution"]["status"] == "completed"
    assert stored.metadata["inputs"]["config_file"] == "cfg.json"
    assert len(stored.results) == 4 and FakeTransport.instances[0].closed


def test_run_with_scenarios_option_uses_that_file(tmp_path, capsys, fake_transport):
    cfg = run_config(tmp_path)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"scenarios": [{"name": "b", "method": "GET", "path": "/b", "repetitions": 2}]}),
                     encoding="utf-8")
    assert main(["run", "--config", str(cfg), "--scenarios", str(other)]) == EXIT_OK
    stored = ResultStore(tmp_path / "results").load_json(only_run_id(tmp_path))
    assert [r.scenario for r in stored.results] == ["b", "b"]
    assert stored.metadata["inputs"]["scenarios_file"] == "other.json"


@pytest.mark.parametrize(
    "files",
    [
        {"config_extra": {"timeout_seconds": "abc"}},
        {"config_extra": {"limits": {"max_requests": 0}}},
        {"config_extra": {"limits": {"bilinmeyen": 1}}},
        {"scenarios": [{**SCENARIO, "warmup_repetitions": -1}]},
        {"scenarios": []},
    ],
)
def test_run_with_invalid_config_or_scenarios_sends_nothing(tmp_path, capsys, fake_transport, files):
    cfg = setup_files(tmp_path, scenarios=files.get("scenarios"),
                      config_extra={"base_url": "http://127.0.0.1:8080", **files.get("config_extra", {})})
    assert main(["run", "--config", str(cfg)]) == EXIT_ERROR
    assert "Hata" in capsys.readouterr().err
    assert FakeTransport.instances == []


@pytest.mark.parametrize("base_url", ["http://203.0.113.5:8080", "http://[2001:db8::1]:8080", "https://example.com"])
def test_run_rejects_non_loopback_target_without_requests(tmp_path, capsys, fake_transport, base_url):
    cfg = run_config(tmp_path, base_url=base_url)
    assert main(["run", "--config", str(cfg)]) == EXIT_REJECTED
    assert "reddedildi, hiçbir istek gönderilmedi" in capsys.readouterr().err
    assert FakeTransport.instances == []
    assert not (tmp_path / "results").exists()


def test_run_rejects_budget_overrun_without_requests(tmp_path, capsys, fake_transport):
    cfg = run_config(tmp_path, scenarios=[{**SCENARIO, "repetitions": 8, "warmup_repetitions": 3}],
                     limits={"max_requests": 10})
    assert main(["run", "--config", str(cfg)]) == EXIT_REJECTED
    assert "planlanan 11" in capsys.readouterr().err
    assert FakeTransport.instances == []


def test_run_rejects_invalid_target_label_without_requests(tmp_path, capsys, fake_transport):
    assert main(["run", "--config", str(run_config(tmp_path)), "--target-label", "  "]) == EXIT_REJECTED
    assert FakeTransport.instances == []


def test_run_aborted_by_safety_limit_returns_distinct_code_and_partial_files(tmp_path, capsys, fake_transport):
    fake_transport.extend([TransportTimeout("t")] * 5)
    cfg = run_config(tmp_path, scenarios=[{**SCENARIO, "repetitions": 5}],
                     limits={"max_consecutive_transport_errors": 2})
    assert main(["run", "--config", str(cfg)]) == EXIT_ABORTED
    captured = capsys.readouterr()
    assert "durum: aborted" in captured.out
    assert "tamamlanmadı" in captured.err and "consecutive_transport_errors" in captured.err
    run_id = only_run_id(tmp_path, partial=True)
    assert not (tmp_path / "results" / f"{run_id}.json").exists()
    assert FakeTransport.instances[0].closed and len(FakeTransport.instances[0].sent) == 2


def test_run_interrupted_by_ctrl_c(tmp_path, capsys, fake_transport):
    fake_transport.extend([TransportResponse(200), KeyboardInterrupt()])
    cfg = run_config(tmp_path, scenarios=[{**SCENARIO, "repetitions": 4}])
    assert main(["run", "--config", str(cfg)]) == EXIT_INTERRUPTED
    captured = capsys.readouterr()
    assert "durum: interrupted" in captured.out and "tamamlanmadı" in captured.err
    stored = ResultStore(tmp_path / "results").load_json(only_run_id(tmp_path, partial=True), partial=True)
    assert stored.metadata["execution"]["status"] == "interrupted" and len(stored.results) == 1
    assert FakeTransport.instances[0].closed


def test_run_storage_failure_returns_distinct_code(tmp_path, capsys, fake_transport):
    (tmp_path / "results").write_text("dizin değil, dosya", encoding="utf-8")  # çıktı dizini oluşturulamaz
    assert main(["run", "--config", str(run_config(tmp_path))]) == EXIT_STORAGE_ERROR
    assert "kaydedilemedi" in capsys.readouterr().err
