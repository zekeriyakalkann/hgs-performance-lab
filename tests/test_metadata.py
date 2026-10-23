import hashlib
import importlib.metadata
import json
import re
import subprocess
from pathlib import Path

import pytest

from hgs2_lab import __version__
from hgs2_lab.config import LabConfig
from hgs2_lab.metadata import (
    REDACTED,
    build_run_metadata,
    code_info,
    config_snapshot,
    dependency_versions,
    environment_info,
    file_sha256,
    input_hashes,
    redact,
    scenario_snapshot,
)
from hgs2_lab.scenarios import Scenario

SECRET = "s3cr3t-value-123"  # sahte
SHA1 = "a2f5d9f" + "0" * 33
FIXED_CODE = {"git_commit": SHA1, "git_dirty": False}


def secret_scenario():
    return Scenario(
        name="login",
        method="POST",
        path=f"/login?lang=tr&token={SECRET}",
        headers={"Authorization": f"Bearer {SECRET}", "X-Api-Key": SECRET, "Accept": "application/json"},
        body={"username": "u", "password": SECRET, "nested": {"refresh_token": SECRET}, "items": [{"cookie": SECRET}]},
        expected_status=(200,),
        warmup_repetitions=2,
    )


def write_inputs(tmp_path):
    config_file = tmp_path / "config.json"
    scenarios_file = tmp_path / "scenarios.json"
    config_file.write_bytes(b'{"base_url": "http://localhost:8080", "note": "CONFIG-CONTENT-MARKER"}\r\n')
    scenarios_file.write_bytes('{"scenarios": [], "note": "SCENARIOS-CONTENT-MARKER-ç"}\n'.encode("utf-8"))
    config = LabConfig(base_url="http://localhost:8080", output_dir=tmp_path / "results", scenarios_file=scenarios_file)
    return config, config_file, scenarios_file


def build(tmp_path, **kw):
    config, config_file, _ = write_inputs(tmp_path)
    args = dict(config_path=config_file, monotonic_duration_ms=1234.5, code=FIXED_CODE)
    args.update(kw)
    return build_run_metadata(config, [secret_scenario()], "2026-01-01T00:00:00+00:00",
                              "2026-01-01T00:01:00+00:00", **args)


# --- maskeleme ---
def test_redact_masks_sensitive_keys_recursively_without_mutating_input():
    original = {"password": "p", "a": {"Token": "t"}, "l": [{"secret": "s"}], "ok": 1}
    result = redact(original)
    assert result == {"password": REDACTED, "a": {"Token": REDACTED}, "l": [{"secret": REDACTED}], "ok": 1}
    assert original["password"] == "p"


def test_scenario_snapshot_hides_secrets_but_keeps_other_fields():
    snap = scenario_snapshot(secret_scenario())
    assert SECRET not in json.dumps(snap)
    assert snap["path"] == f"/login?lang=tr&token={REDACTED}"  # hassas sorgu değeri maskeli
    assert snap["headers"]["Accept"] == "application/json"
    assert snap["body"]["username"] == "u"
    assert snap["name"] == "login" and snap["expected_status"] == [200]
    assert snap["warmup_repetitions"] == 2


# --- tam metadata ---
def test_run_metadata_contents_and_no_secrets(tmp_path):
    meta = build(tmp_path, target_label="yerel-test")
    assert set(meta) == {
        "tool_version", "dataset_kind", "target_label", "started_at", "finished_at", "monotonic_duration_ms", "clock",
        "execution", "code", "dependencies", "environment", "inputs", "config", "scenarios",
    }
    assert meta["dataset_kind"] == "measurement"  # varsayılan; sentetik deney açıkça işaretlenir
    assert meta["execution"] is None  # doğrudan çağrıda durum verilmedi; çalıştırma akışı doldurur
    assert meta["clock"] is None  # saat çapasını runner üretir; çalıştırma akışı verir
    assert meta["tool_version"] == __version__
    assert meta["target_label"] == "yerel-test"
    assert meta["monotonic_duration_ms"] == 1234.5
    assert meta["code"] == FIXED_CODE
    assert meta["config"]["base_url"] == "http://localhost:8080"
    assert len(meta["scenarios"]) == 1
    assert SECRET not in json.dumps(meta)
    json.dumps(meta, allow_nan=False)  # sonuç dosyasına yazılabilir


def test_target_label_is_optional(tmp_path):
    assert build(tmp_path)["target_label"] is None


def test_clock_must_be_a_clock_anchor(tmp_path):
    with pytest.raises(ValueError, match="ClockAnchor"):
        build(tmp_path, clock={"monotonic_ns": 1})


@pytest.mark.parametrize("bad", ["", "   ", 5])
def test_invalid_target_label_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        build(tmp_path, target_label=bad)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), True, "5"])
def test_invalid_monotonic_duration_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        build(tmp_path, monotonic_duration_ms=bad)


def test_monotonic_duration_may_be_unknown(tmp_path):
    assert build(tmp_path, monotonic_duration_ms=None)["monotonic_duration_ms"] is None


def test_metadata_contains_no_absolute_paths(tmp_path):
    meta = build(tmp_path)
    text = json.dumps(meta)
    for forbidden in (str(tmp_path), tmp_path.as_posix(), str(Path.home()), Path.home().as_posix()):
        assert forbidden not in text
        assert json.dumps(forbidden)[1:-1] not in text  # JSON kaçışlı (\\) biçim de yok
    assert meta["config"]["output_dir"] == "results"
    assert meta["config"]["scenarios_file"] == "scenarios.json"
    assert meta["inputs"]["config_file"] == "config.json"
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", text)  # Windows sürücü yolu yok ("http:/" hariç)


def test_config_snapshot_keeps_to_dict_unchanged(tmp_path):
    config, _, _ = write_inputs(tmp_path)
    assert Path(config.to_dict()["output_dir"]).is_absolute()  # to_dict davranışı değişmedi
    assert set(config_snapshot(config)) == set(config.to_dict())


# --- girdi özetleri ---
def test_input_hashes_use_original_file_bytes(tmp_path):
    _, config_file, scenarios_file = write_inputs(tmp_path)
    hashes = input_hashes(config_file, scenarios_file)
    assert hashes["config_sha256"] == hashlib.sha256(config_file.read_bytes()).hexdigest()  # \r\n dahil
    assert hashes["scenarios_sha256"] == hashlib.sha256(scenarios_file.read_bytes()).hexdigest()
    assert hashes["hash_errors"] == {}
    assert file_sha256(config_file) == hashes["config_sha256"]


def test_input_hashes_report_missing_or_unreadable_files_safely(tmp_path):
    hashes = input_hashes(tmp_path / "yok.json", tmp_path)  # olmayan dosya ve bir dizin
    assert hashes["config_sha256"] is None and hashes["scenarios_sha256"] is None
    assert hashes["hash_errors"]["config"] == "FileNotFoundError"
    assert hashes["hash_errors"]["scenarios"] in {"IsADirectoryError", "PermissionError"}
    assert str(tmp_path) not in json.dumps(hashes)  # hata mesajı/yol yazılmaz


def test_input_hashes_without_config_path():
    hashes = input_hashes(None, None)
    assert hashes["config_file"] is None and hashes["config_sha256"] is None
    assert hashes["hash_errors"] == {"config": "path_not_provided", "scenarios": "path_not_provided"}


def test_metadata_hashes_match_inputs_and_content_is_not_copied(tmp_path):
    meta = build(tmp_path)
    _, config_file, scenarios_file = write_inputs(tmp_path)
    assert meta["inputs"]["config_sha256"] == hashlib.sha256(config_file.read_bytes()).hexdigest()
    assert meta["inputs"]["scenarios_sha256"] == hashlib.sha256(scenarios_file.read_bytes()).hexdigest()
    text = json.dumps(meta)
    assert "CONFIG-CONTENT-MARKER" not in text and "SCENARIOS-CONTENT-MARKER" not in text  # içerik kopyalanmadı


# --- Git bilgisi (sahte subprocess.run) ---
class FakeRun:
    def __init__(self, *results):
        self._results = list(results)
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def completed(returncode=0, stdout=b""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=b"")


def test_code_info_clean_repository():
    run = FakeRun(completed(stdout=f"{SHA1}\n".encode()), completed(stdout=b""))
    assert code_info(run=run) == {"git_commit": SHA1, "git_dirty": False}
    (args1, kw1), (args2, kw2) = run.calls
    assert args1 == ["git", "rev-parse", "--verify", "HEAD"]
    assert args2 == ["git", "status", "--porcelain"]
    assert kw1["shell"] is False and kw1["timeout"] > 0 and kw1["check"] is False


def test_code_info_dirty_repository_does_not_store_file_names():
    run = FakeRun(completed(stdout=f"{SHA1}\n".encode()), completed(stdout=b" M gizli-dosya-adi.py\n"))
    info = code_info(run=run)
    assert info == {"git_commit": SHA1, "git_dirty": True}
    assert "gizli-dosya-adi" not in json.dumps(info)


def test_code_info_git_not_installed():
    assert code_info(run=FakeRun(FileNotFoundError("git"))) == {"git_commit": None, "git_dirty": None}


def test_code_info_outside_repository():
    run = FakeRun(completed(returncode=128, stdout=b""))
    assert code_info(run=run) == {"git_commit": None, "git_dirty": None}


def test_code_info_timeout():
    run = FakeRun(subprocess.TimeoutExpired(cmd="git", timeout=5))
    assert code_info(run=run) == {"git_commit": None, "git_dirty": None}


def test_code_info_status_failure_keeps_commit():
    run = FakeRun(completed(stdout=f"{SHA1}\n".encode()), completed(returncode=1))
    assert code_info(run=run) == {"git_commit": SHA1, "git_dirty": None}


def test_code_info_rejects_unexpected_head_output():
    run = FakeRun(completed(stdout=b"not-a-sha\n"))
    assert code_info(run=run) == {"git_commit": None, "git_dirty": None}


def test_code_info_real_git_smoke():
    # Yerel git sorgusu (ağ yok); ortamdan bağımsız olarak yalnızca türler doğrulanır.
    info = code_info()
    assert info["git_commit"] is None or re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", info["git_commit"])
    assert info["git_dirty"] in (None, True, False)


# --- sürümler ---
def test_dependency_versions_match_installed_packages():
    versions = dependency_versions()
    assert versions["requests"] == importlib.metadata.version("requests")
    assert versions["urllib3"] == importlib.metadata.version("urllib3")


def test_tool_version_matches_pyproject():
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as f:
        assert tomllib.load(f)["project"]["version"] == __version__


def test_environment_info_keys():
    info = environment_info()
    assert {"python_version", "python_implementation", "platform", "machine", "cpu_count"} <= set(info)
    json.dumps(info)
