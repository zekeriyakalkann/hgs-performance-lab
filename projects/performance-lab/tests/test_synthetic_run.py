"""`hgs2-lab synthetic run` uçtan uca entegrasyon testleri: yerel sentetik sunucu + gerçek RequestsTransport.

`pytest -m integration` ile seçilir. Hedef koruması (ön kontrol, ad çözümlemesi, bağlantı katmanı) değiştirilmeden
uygulanır; 127.0.0.1 dışına her bağlantı girişimi bağlantı kurulmadan reddedilir ve testi başarısız kılar.
"""

import functools
import hashlib
import json
from pathlib import Path

import pytest
from local_http_server import install_network_guard

from hgs2_lab import cli, execution
from hgs2_lab.cli import EXIT_ABORTED, EXIT_OK, EXIT_REJECTED, EXIT_SYNTHETIC_INVALID, main
from hgs2_lab.execution import PreflightError
from hgs2_lab.reader import load_run
from hgs2_lab.synthetic import build_plan, parse_manifest
from hgs2_lab.synthetic_experiment import run_synthetic_experiment
from hgs2_lab.synthetic_server import SyntheticServer

pytestmark = pytest.mark.integration

EXAMPLE = Path(__file__).resolve().parent.parent / "configs" / "synthetic.example.json"


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked:
        sock.close()
    assert attempts == []


@pytest.fixture(autouse=True)
def fixed_code_info(monkeypatch):
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})


def manifest(**overrides):
    data = {
        "manifest_version": 1, "experiment_id": "it-mix", "experiment_type": "fault_injection",
        "dataset_kind": "synthetic", "seed": 11, "timeout_seconds": 0.3,
        "limits": {"max_consecutive_transport_errors": 10},
        "scenarios": [
            {"name": "ok", "warmup_repetitions": 1, "repetitions": 4, "fault": {"type": "none"}},
            {"name": "fixed", "repetitions": 2, "fault": {"type": "fixed_delay", "delay_ms": 60}},
            {"name": "rnd", "repetitions": 3, "fault": {"type": "random_delay", "min_delay_ms": 5, "max_delay_ms": 40}},
            {"name": "err", "repetitions": 3, "fault": {"type": "http_error", "status": 503, "onset_after": 1}},
            {"name": "drop", "repetitions": 2, "fault": {"type": "connection_drop"}},
            {"name": "to", "repetitions": 1, "fault": {"type": "timeout"}},
        ],
    }
    data.update(overrides)
    return data


def write_manifest(tmp_path, data, name="manifest.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_synthetic_run_end_to_end_with_labels_and_analyze(tmp_path, capsys):
    path = write_manifest(tmp_path, manifest())
    results = tmp_path / "results"
    assert main(["synthetic", "run", "--manifest", str(path), "--results-dir", str(results), "--run-id", "syn1"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "durum: completed" in out and "deney geçerli: evet" in out
    assert "taşıma hatası: connection_error 2, timeout 1" in out

    # 1) İstemci sonuçları: şema v2, veri türü açıkça sentetik, planlanan hata YOK.
    run = load_run(results, "syn1")
    assert run.schema_version == 2 and run.dataset_kind == "synthetic" and not run.partial
    assert run.metadata["synthetic"]["experiment_id"] == "it-mix"
    assert run.metadata["target_label"] == "synthetic:it-mix"
    assert run.metadata["config"]["base_url"].startswith("http://127.0.0.1:")
    raw = (results / "syn1.json").read_text(encoding="utf-8")
    for leaked in ("connection_drop", "fixed_delay", "random_delay", "http_error", "delay_ms", "onset_after"):
        assert leaked not in raw
    by_seq = {r.seq: r for r in run.results}
    assert (by_seq[6].status_code, by_seq[6].http_ok) == (200, True)  # ilk "fixed"
    assert by_seq[6].duration_ms >= 60
    assert [(r.status_code, r.http_ok, r.error_type) for r in run.results if r.scenario == "err"] == [
        (200, True, None), (503, False, None), (503, False, None)]  # HTTP hatası taşıma hatası değildir
    assert [r.error_type for r in run.results if r.scenario in ("drop", "to")] == [
        "connection_error", "connection_error", "timeout"]

    # 2) Etiketler: beklenen ve gözlenen ayrı; hepsi doğrulandı.
    labels = read_json(results / "synthetic" / "syn1.labels.json")
    assert labels["verdict"] == {"valid": True, "reasons": []}
    assert labels["summary"]["confirmed"] == labels["summary"]["planned"] == 16
    assert labels["experiment"]["plan_sha256"] == run.metadata["synthetic"]["plan_sha256"]
    assert {f["name"] for f in labels["run"]["result_files"]} == {"syn1.json", "syn1.csv"}
    assert labels["run"]["result_files"][0]["sha256"] == hashlib.sha256((results / "syn1.json").read_bytes()).hexdigest()
    err = [r for r in labels["requests"] if r["scenario"] == "err"]
    assert [(r["expected"]["outcome"], r["observed"]["outcome"]) for r in err] == [
        ("success", "success"), ("http_error", "http_error"), ("http_error", "http_error")]

    # 3) Sunucu olayları: ayrı kaynak, istemci çapasına hizalı.
    events = read_json(results / "synthetic" / "syn1.server-events.json")
    assert events["summary"]["arrivals"] == 16 and events["summary"]["unexpected_requests"] == 0
    assert events["clock"]["offset_available"] is True
    first_fixed = next(e for e in events["events"] if e["route"] == "fixed")
    assert first_fixed["hold_ms_actual"] >= 60
    assert first_fixed["received_offset_ms"] >= by_seq[6].offset_ms  # sunucu, istemci başladıktan sonra alır

    # 4) F1 analizi sentetik sonuçları okur ve sentetik olduğunu belirtir.
    assert main(["analyze", "--results-dir", str(results), "--run-id", "syn1"]) == EXIT_OK
    analysis = read_json(results / "analysis" / "syn1.analysis.json")["analysis"]
    assert analysis["run"]["dataset_kind"] == "synthetic"
    assert "synthetic_data" in {w["code"] for w in analysis["warnings"]}
    measured = analysis["overall"]["measured"]
    assert (measured["http_errors"], measured["transport_errors"]) == (2, 3)
    assert measured["transport_errors_by_type"] == {"connection_error": 2, "timeout": 1}


def test_same_seed_reproduces_plan_and_labels_but_not_timings(tmp_path):
    path = write_manifest(tmp_path, manifest())
    a = run_synthetic_experiment(path, results_dir=tmp_path / "r", run_id="a")
    b = run_synthetic_experiment(path, results_dir=tmp_path / "r", run_id="b")
    assert a.valid and b.valid
    assert a.labels["experiment"]["plan_sha256"] == b.labels["experiment"]["plan_sha256"]
    strip = lambda doc: [(r["planned"], r["expected"], r["label_status"]) for r in doc["requests"]]  # noqa: E731
    assert strip(a.labels) == strip(b.labels)  # aynı plan, aynı beklenti, aynı etiket durumu


def test_aborted_experiment_is_reported_invalid_with_partial_labels(tmp_path, capsys):
    data = manifest(limits={"max_consecutive_transport_errors": 2})
    data["scenarios"] = [{"name": "drop", "repetitions": 5, "fault": {"type": "connection_drop"}}]
    path = write_manifest(tmp_path, data)
    results = tmp_path / "results"
    code = main(["synthetic", "run", "--manifest", str(path), "--results-dir", str(results), "--run-id", "ab"])
    assert code == EXIT_ABORTED
    assert "deney geçerli: HAYIR (run_incomplete)" in capsys.readouterr().out
    labels = read_json(results / "synthetic" / "ab.partial.labels.json")
    assert labels["verdict"]["valid"] is False and labels["run"]["execution_status"] == "aborted"
    assert (labels["summary"]["confirmed"], labels["summary"]["not_executed"]) == (2, 3)
    assert (results / "ab.partial.json").is_file() and (results / "synthetic" / "ab.partial.server-events.json").is_file()


def test_expectation_mismatch_is_reported_invalid(tmp_path, capsys, monkeypatch):
    """Sunucu planla çelişen bir planla çalışırsa (ör. 503 yerine 500) gözlenen beklenenden ayrılır."""
    data = manifest()
    path = write_manifest(tmp_path, data)
    tampered = json.loads(json.dumps(data))
    tampered["scenarios"][3]["fault"]["status"] = 500
    wrong_plan = build_plan(parse_manifest(tampered))
    factory = lambda plan: SyntheticServer(wrong_plan)  # noqa: E731
    monkeypatch.setattr(cli, "run_synthetic_experiment",
                        functools.partial(run_synthetic_experiment, server_factory=factory))
    results = tmp_path / "results"
    code = main(["synthetic", "run", "--manifest", str(path), "--results-dir", str(results), "--run-id", "mm"])
    assert code == EXIT_SYNTHETIC_INVALID
    assert "expectation_mismatch" in capsys.readouterr().out
    labels = read_json(results / "synthetic" / "mm.labels.json")
    contradicted = [r for r in labels["requests"] if r["label_status"] == "contradicted"]
    assert [(r["expected"]["status"], r["observed"]["status"]) for r in contradicted] == [(503, 500), (503, 500)]
    assert labels["summary"]["contradicted"] == 2 and labels["verdict"]["valid"] is False


def test_target_guard_is_not_bypassed(tmp_path):
    """Sentetik sunucu da normal bir hedeftir: çözümleme loopback dışı dönerse hiçbir istek gönderilmez."""
    created = []

    def factory(plan):
        created.append(SyntheticServer(plan))
        return created[-1]

    path = write_manifest(tmp_path, manifest())
    with pytest.raises(PreflightError, match="loopback dışı"):
        run_synthetic_experiment(path, results_dir=tmp_path / "r", run_id="g", resolver=lambda h, p: ["203.0.113.7"],
                                 server_factory=factory)
    assert created[0].snapshot()["arrivals"] == 0 and created[0].is_closed
    assert not (tmp_path / "r").exists()


def test_existing_outputs_are_not_overwritten(tmp_path, capsys):
    path = write_manifest(tmp_path, manifest())
    results = tmp_path / "results"
    assert main(["synthetic", "run", "--manifest", str(path), "--results-dir", str(results), "--run-id", "x"]) == EXIT_OK
    before = {p: p.read_bytes() for p in results.rglob("*") if p.is_file()}
    capsys.readouterr()
    assert main(["synthetic", "run", "--manifest", str(path), "--results-dir", str(results), "--run-id", "x"]) \
        == EXIT_REJECTED
    assert "hiçbir istek gönderilmedi" in capsys.readouterr().err
    assert {p: p.read_bytes() for p in results.rglob("*") if p.is_file()} == before


def test_matching_survives_timeout_holds_that_overlap_later_requests(tmp_path):
    """Zaman aşımında istemci devam eder, sunucu önceki isteği hâlâ bekletir: sonraki istekler eşzamanlı işlenir.
    Rota içi sıra geliş anında kilit altında atandığı için eşleştirme bozulmamalı (F3-A incelemesi)."""
    data = manifest(scenarios=[
        {"name": "to", "repetitions": 2, "fault": {"type": "timeout"}},
        {"name": "ok", "repetitions": 3, "fault": {"type": "none"}},
        {"name": "to2", "repetitions": 1, "fault": {"type": "timeout"}},
        {"name": "late", "repetitions": 2, "fault": {"type": "fixed_delay", "delay_ms": 20}},
    ])
    outcome = run_synthetic_experiment(write_manifest(tmp_path, data), results_dir=tmp_path / "r", run_id="ov")
    assert outcome.valid and outcome.server_leftover_threads == 0
    assert [r["label_status"] for r in outcome.labels["requests"]] == ["confirmed"] * 8

    events = read_json(outcome.server_events_path)
    assert events["process_model"] == "same_process" and len(events["timing_caveats"]) == 2
    planned = [e for e in events["events"] if e["kind"] == "planned"]
    assert [(e["route"], e["route_index"]) for e in planned] == [
        ("to", 1), ("to", 2), ("ok", 1), ("ok", 2), ("ok", 3), ("to2", 1), ("late", 1), ("late", 2)]
    held = planned[1]  # 2. zaman aşımı isteği
    after = planned[2]  # sonraki normal istek
    assert after["received_offset_ms"] < held["completed_offset_ms"]  # çakışma gerçekten oldu
    assert after["outcome"] == "responded" and held["outcome"] in ("held_then_closed", "stopped")


def test_example_manifest_runs_valid(tmp_path):
    outcome = run_synthetic_experiment(EXAMPLE, results_dir=tmp_path / "r", run_id="example")
    assert outcome.valid and outcome.run.completed and outcome.server_leftover_threads == 0
    assert outcome.labels["summary"]["planned"] == 55


def test_delay_fields_are_recorded_separately_in_events_and_labels(tmp_path):
    data = manifest(scenarios=[
        {"name": "ok", "repetitions": 3, "fault": {"type": "none"}},
        {"name": "d", "repetitions": 4, "fault": {"type": "fixed_delay", "delay_ms": 25}},
        {"name": "r", "repetitions": 4, "fault": {"type": "random_delay", "min_delay_ms": 5, "max_delay_ms": 30}},
    ])
    outcome = run_synthetic_experiment(write_manifest(tmp_path, data), results_dir=tmp_path / "r", run_id="dl")
    assert outcome.valid

    events = read_json(outcome.server_events_path)
    assert events["hold_method"]["name"] == "sliced_sleep" and events["schema_version"] == 1
    assert {"received_ns", "hold_ms_planned", "hold_ms_actual", "completed_ns"} <= set(events["timing_fields"])
    delayed = [e for e in events["events"] if e["route"] in ("d", "r")]
    for e in delayed:
        assert e["hold_ms_actual"] >= e["hold_ms_planned"] > 0
        assert e["received_offset_ms"] <= e["hold_started_offset_ms"] <= e["hold_ended_offset_ms"] \
            <= e["completed_offset_ms"]

    run = load_run(tmp_path / "r", "dl")
    by_seq = {r.seq: r for r in run.results}
    labels = outcome.labels
    assert "timing_fields" in labels
    for record in labels["requests"]:
        observed, server, planned = record["observed"], record["server"], record["planned"]
        assert observed["duration_ms"] == by_seq[record["index"]].duration_ms  # gözlenen = sonuç dosyası
        if planned["delay_ms"]:
            assert server["hold_ms_actual"] >= planned["delay_ms"]  # gerçekleşen >= planlanan, ayrı alanlarda
            assert observed["duration_ms"] >= server["hold_ms_actual"]  # istemci süresi beklemeyi kapsar
        else:
            assert server["hold_ms_actual"] is None

    raw = (tmp_path / "r" / "dl.json").read_text(encoding="utf-8")
    assert "hold_ms" not in raw and "delay_ms" not in raw  # gerçekleşen bekleme de sonuç dosyasına sızmaz


def test_server_is_stopped_and_no_labels_written_when_run_fails_unexpectedly(tmp_path, monkeypatch):
    from hgs2_lab import synthetic_experiment

    created = []

    def factory(plan):
        created.append(SyntheticServer(plan))
        return created[-1]

    def boom(*args, **kwargs):
        raise RuntimeError("beklenmeyen hata")

    monkeypatch.setattr(synthetic_experiment, "execute_run", boom)
    with pytest.raises(RuntimeError, match="beklenmeyen"):
        run_synthetic_experiment(write_manifest(tmp_path, manifest()), results_dir=tmp_path / "r", run_id="f",
                                 server_factory=factory)
    (server,) = created
    assert server.is_closed and server.stop() == []  # kapatıldı, iş parçacığı kalmadı; ikinci stop güvenli
    assert not (tmp_path / "r").exists()  # yarım etiket/olay dosyası yazılmadı
