import json

import pytest

from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_RUN_DISABLED, main

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


def test_validate_ok_reports_resolved_paths(tmp_path, capsys):
    assert main(["validate", "--config", str(setup_files(tmp_path))]) == EXIT_OK
    out = capsys.readouterr().out
    assert "1 senaryo" in out
    assert str((tmp_path / "scen.json").resolve()) in out


def test_list_prints_scenarios(tmp_path, capsys):
    assert main(["list", "--config", str(setup_files(tmp_path))]) == EXIT_OK
    out = capsys.readouterr().out
    assert "GET /a" in out and "200,204" in out


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


def test_run_is_disabled_with_distinct_exit_code(capsys):
    assert main(["run"]) == EXIT_RUN_DISABLED
    assert EXIT_RUN_DISABLED not in (EXIT_OK, EXIT_ERROR, 2)  # 2: argparse kullanım hatası
    assert "etkin değil" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["bilinmeyen"], ["run", "--config", "x.json"], ["validate", "--nope"]])
def test_usage_errors_exit_with_argparse_code(argv):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
