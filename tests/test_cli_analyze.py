"""`hgs2-lab analyze` testleri. Analiz yolu ağ kullanmaz: her testte soket bağlantısı, ad çözümlemesi ve
requests oturumu engellenir; herhangi bir girişim testi başarısız kılar."""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, EXIT_USAGE, main
from hgs2_lab.config import LabConfig
from hgs2_lab.execution import execute_run
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import TransportResponse, TransportTimeout

GOLDEN = Path(__file__).parent / "golden"
SRC = Path(__file__).resolve().parent.parent / "src"
COMPLETED = "golden-v2-a1331fd-completed"
ABORTED = "golden-v2-a1331fd-aborted"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append(args)
        raise AssertionError(f"Analiz yolunda ağ erişimi girişimi: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)
    yield attempts
    assert attempts == []


def copy_golden(tmp_path, directory="v2-a1331fd"):
    results = tmp_path / "results"
    shutil.copytree(GOLDEN / directory, results)
    return results


def digests(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}


def test_analyze_writes_default_output_and_keeps_inputs_unchanged(tmp_path, capsys):
    results = copy_golden(tmp_path)
    before = digests(results)
    assert main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED]) == EXIT_OK
    out = capsys.readouterr().out
    assert f"Analiz: {COMPLETED}  durum: completed" in out
    assert "ölçümde başarılı 5, HTTP hatası 1, taşıma hatası 1" in out
    assert "p90 yetersiz örneklem (en az 100)" in out

    output = results / "analysis" / f"{COMPLETED}.analysis.json"
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["format"] == "hgs2-lab-analysis"
    assert document["analysis"]["input"]["files"][0]["sha256"] == before[f"{COMPLETED}.json"]
    assert document["analysis"]["overall"]["response_time_ms"]["median"]["value"] == 6.25
    assert digests(results) == before  # ham sonuçlar değişmedi


def test_analyze_refuses_to_overwrite(tmp_path, capsys):
    results = copy_golden(tmp_path)
    assert main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED]) == EXIT_OK
    output = results / "analysis" / f"{COMPLETED}.analysis.json"
    original = output.read_bytes()
    capsys.readouterr()
    assert main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED]) == EXIT_STORAGE_ERROR
    assert "üzerine yazılmaz" in capsys.readouterr().err
    assert output.read_bytes() == original


def test_analyze_refuses_existing_custom_output(tmp_path, capsys):
    results = copy_golden(tmp_path)
    target = tmp_path / "rapor.json"
    target.write_text("mevcut", encoding="utf-8")
    code = main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED, "--output", str(target)])
    assert code == EXIT_STORAGE_ERROR and target.read_text(encoding="utf-8") == "mevcut"


def test_analyze_output_into_input_file_is_refused(tmp_path):
    results = copy_golden(tmp_path)
    before = digests(results)
    code = main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED,
                 "--output", str(results / f"{COMPLETED}.json")])
    assert code == EXIT_STORAGE_ERROR and digests(results) == before


def test_analyze_partial_run_uses_partial_name_and_flags_it(tmp_path, capsys):
    results = copy_golden(tmp_path)
    assert main(["analyze", "--results-dir", str(results), "--run-id", ABORTED]) == EXIT_OK
    assert "durum: aborted  (kısmi)" in capsys.readouterr().out
    document = json.loads((results / "analysis" / f"{ABORTED}.partial.analysis.json").read_text(encoding="utf-8"))
    assert "run_incomplete" in {w["code"] for w in document["analysis"]["warnings"]}


def test_analyze_is_deterministic_across_invocations(tmp_path):
    results = copy_golden(tmp_path)
    for name in ("a.json", "b.json"):
        assert main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED,
                     "--output", str(tmp_path / name)]) == EXIT_OK
    a, b = (json.loads((tmp_path / n).read_text(encoding="utf-8")) for n in ("a.json", "b.json"))
    assert a["analysis"] == b["analysis"] and a["content_sha256"] == b["content_sha256"]


@pytest.mark.parametrize("run_id, message", [
    ("yok", "bulunamadı"),
    ("../dışarı", "Geçersiz run_id"),
])
def test_analyze_missing_or_invalid_run(tmp_path, capsys, run_id, message):
    results = copy_golden(tmp_path)
    assert main(["analyze", "--results-dir", str(results), "--run-id", run_id]) == EXIT_ERROR
    assert message in capsys.readouterr().err
    assert not (results / "analysis").exists()


def test_analyze_rejects_v1_and_inconsistent_inputs(tmp_path, capsys):
    v1 = copy_golden(tmp_path / "v1", "v1-a2f5d9f")
    assert main(["analyze", "--results-dir", str(v1), "--run-id", "golden-v1-a2f5d9f"]) == EXIT_ERROR
    assert "schema_version 1" in capsys.readouterr().err

    results = copy_golden(tmp_path / "bad")
    (results / f"{COMPLETED}.csv").unlink()
    assert main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED]) == EXIT_ERROR
    assert "eksik" in capsys.readouterr().err


def test_analyze_uses_config_output_dir_without_scenarios_file(tmp_path, capsys):
    copy_golden(tmp_path)
    cfg = tmp_path / "configs" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"base_url": "http://127.0.0.1:8080", "output_dir": "../results",
                               "scenarios_file": "yok.json"}), encoding="utf-8")
    assert main(["analyze", "--config", str(cfg), "--run-id", COMPLETED]) == EXIT_OK
    assert (tmp_path / "results" / "analysis" / f"{COMPLETED}.analysis.json").is_file()


def test_analyze_missing_config_without_results_dir(tmp_path, capsys):
    assert main(["analyze", "--config", str(tmp_path / "yok.json"), "--run-id", COMPLETED]) == EXIT_ERROR
    assert "Hata" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["--confidence", "1.5"], ["--bootstrap-resamples", "5"], ["--seed", "-3"]])
def test_analyze_invalid_parameters(tmp_path, capsys, args):
    results = copy_golden(tmp_path)
    assert main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED, *args]) == EXIT_USAGE
    assert "Geçersiz analiz parametresi" in capsys.readouterr().err


def test_analyze_parameters_are_recorded(tmp_path):
    results = copy_golden(tmp_path)
    out = tmp_path / "a.json"
    assert main(["analyze", "--results-dir", str(results), "--run-id", COMPLETED, "--output", str(out), "--seed", "9",
                 "--bootstrap-resamples", "300", "--confidence", "0.9", "--min-tail-samples", "5"]) == EXIT_OK
    params = json.loads(out.read_text(encoding="utf-8"))["analysis"]["method"]["parameters"]
    assert (params["seed"], params["bootstrap_resamples"], params["confidence"], params["min_tail_samples"]) == \
        (9, 300, 0.9, 5)


# --- uçtan uca: yeni yazıcı -> analiz (saat çapası dahil) ---
class _Clock:
    def __init__(self):
        self.now_ns = 1_000

    def __call__(self):
        return self.now_ns


class _Transport:
    def __init__(self, clock):
        self._clock, self._i = clock, 0

    def send(self, scenario, url, timeout_seconds):
        self._i += 1
        self._clock.now_ns += (2 + self._i % 3) * 1_000_000
        if self._i == 7:
            raise TransportTimeout("t")
        return TransportResponse(500 if self._i == 9 else 200, 3)

    def close(self):
        pass


def test_run_then_analyze_end_to_end_with_clock(tmp_path, capsys):
    clock = _Clock()
    config = LabConfig(base_url="http://127.0.0.1:8080", output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json")
    execute_run(config, [Scenario(name="a", method="GET", path="/a", repetitions=12, warmup_repetitions=2)],
                config_path=None, run_id="e2e", resolver=lambda h, p: ["127.0.0.1"],
                transport_factory=lambda: _Transport(clock), clock=clock, now=lambda: "2026-01-01T00:00:00+00:00",
                sleep=lambda s: None, code={"git_commit": "a" * 40, "git_dirty": False},
                wall_clock=lambda: 1_767_225_600_000_000_000)
    assert main(["analyze", "--results-dir", str(tmp_path / "results"), "--run-id", "e2e"]) == EXIT_OK
    analysis = json.loads((tmp_path / "results" / "analysis" / "e2e.analysis.json").read_text(encoding="utf-8"))
    analysis = analysis["analysis"]
    assert analysis["clock"]["available"] is True
    overall = analysis["overall"]
    assert overall["requests"] == {"total": 14, "warmup": 2, "measured": 12}
    assert (overall["measured"]["transport_errors"], overall["measured"]["http_errors"]) == (1, 1)
    assert overall["throughput"]["status"] == "ok"  # tek senaryo: ölçüm istekleri kesintisiz blok
    codes = {w["code"] for w in analysis["warnings"]}
    assert "clock_anchor_missing" not in codes and "input_hash_unavailable" in codes  # config_path verilmedi


# --- içe aktarma yalıtımı ---
def test_reader_and_analysis_modules_do_not_import_network_code():
    code = (
        "import sys; import hgs2_lab.analysis, hgs2_lab.reader, hgs2_lab.clock; "
        "bad = sorted(m for m in ('requests', 'urllib3', 'http.client', 'hgs2_lab.http_transport', "
        "'hgs2_lab.execution', 'hgs2_lab.target_guard', 'hgs2_lab.runner') if m in sys.modules); print(bad)"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"
