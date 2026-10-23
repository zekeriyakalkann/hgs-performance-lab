import json
from pathlib import Path

import pytest

from hgs2_lab.config import ConfigError, LabConfig, load_config


def write(tmp_path, data, name="config.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_minimal_uses_defaults_resolved_against_config_dir(tmp_path):
    cfg = load_config(write(tmp_path, {"base_url": "http://localhost:8080"}))
    assert cfg.base_url == "http://localhost:8080"
    assert cfg.timeout_seconds == 10.0
    assert cfg.output_dir == (tmp_path / "results").resolve()
    assert cfg.scenarios_file == (tmp_path / "scenarios.json").resolve()


def test_relative_paths_follow_config_file_not_cwd(tmp_path, monkeypatch):
    conf_dir = tmp_path / "configs"
    conf_dir.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    path = write(conf_dir, {"base_url": "https://x", "output_dir": "../out", "scenarios_file": "s.json"})
    monkeypatch.chdir(other)
    cfg = load_config(path)
    assert cfg.output_dir == (tmp_path / "out").resolve()
    assert cfg.scenarios_file == (conf_dir / "s.json").resolve()


def test_absolute_paths_kept(tmp_path):
    out = tmp_path / "abs_out"
    cfg = load_config(write(tmp_path, {"base_url": "http://x", "output_dir": str(out)}))
    assert cfg.output_dir == out.resolve()


def test_timeout_override(tmp_path):
    assert load_config(write(tmp_path, {"base_url": "http://x", "timeout_seconds": 3})).timeout_seconds == 3


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"base_url": 123},
        {"base_url": ""},
        {"base_url": "localhost:8080"},
        {"base_url": "ftp://x"},
        {"base_url": "http://"},
        {"base_url": "http://user:pw@host"},
        {"base_url": "http://host/?a=1"},
        {"base_url": "http://host/#frag"},
        {"base_url": "http://x", "timeout_seconds": "5"},
        {"base_url": "http://x", "timeout_seconds": True},
        {"base_url": "http://x", "timeout_seconds": 0},
        {"base_url": "http://x", "timeout_seconds": -1},
        {"base_url": "http://x", "timeout_seconds": float("nan")},
        {"base_url": "http://x", "timeout_seconds": float("inf")},
        {"base_url": "http://x", "output_dir": 5},
        {"base_url": "http://x", "scenarios_file": None},
        {"base_url": "http://x", "timeout": 5},
    ],
)
def test_invalid_config_rejected(tmp_path, data):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, data))


def test_top_level_must_be_object(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match="nesne"):
        load_config(p)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="bulunamadı"):
        load_config(tmp_path / "yok.json")


def test_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON"):
        load_config(p)


def test_path_is_directory(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_undecodable_file(tmp_path):
    p = tmp_path / "bin.json"
    p.write_bytes(b"\xff\xff\xff")
    with pytest.raises(ConfigError):
        load_config(p)


def test_direct_construction_validates():
    with pytest.raises(ConfigError):
        LabConfig(base_url="http://x", timeout_seconds=float("nan"))
    with pytest.raises(ConfigError):
        LabConfig(base_url="http://x", output_dir="results")  # Path değil


def test_to_dict_has_no_extra_fields():
    d = LabConfig(base_url="http://x", output_dir=Path("o"), scenarios_file=Path("s")).to_dict()
    assert set(d) == {"base_url", "timeout_seconds", "output_dir", "scenarios_file"}
