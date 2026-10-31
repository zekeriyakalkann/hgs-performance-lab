"""Sentetik deney birim testleri: manifest doğrulaması, plan determinizmi, etiketleme, veri türü ayrımı ve
`synthetic validate|plan` komutları. Ağ ve soket kullanılmaz."""

import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from factories import make_failed_result, make_result

from hgs2_lab.analysis import build_analysis
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.config import LabConfig
from hgs2_lab.execution import PreflightError, execute_run
from hgs2_lab.metadata import build_run_metadata
from hgs2_lab.models import RawResult
from hgs2_lab.reader import RunDataError, load_run
from hgs2_lab.scenarios import Scenario
from hgs2_lab.storage import ResultStore
from hgs2_lab.synthetic import (
    EXCLUDED_FIELDS,
    IDENTIFIER_FIELDS,
    MODEL_INPUT_CANDIDATE_FIELDS,
    ManifestError,
    build_labels,
    build_plan,
    check_plan_limits,
    guard_forecast,
    load_manifest,
    parse_manifest,
    timeout_hold_ms,
)

EXAMPLE = Path(__file__).resolve().parent.parent / "configs" / "synthetic.example.json"
GOLDEN = Path(__file__).parent / "golden" / "v2-a1331fd"


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


def manifest_data(**overrides):
    data = {
        "manifest_version": 1, "experiment_id": "exp-1", "experiment_type": "fault_injection",
        "dataset_kind": "synthetic", "seed": 7, "timeout_seconds": 1.0,
        "limits": {"max_consecutive_transport_errors": 10},
        "scenarios": [
            {"name": "ok", "warmup_repetitions": 1, "repetitions": 3, "fault": {"type": "none"}},
            {"name": "slow", "repetitions": 4, "fault": {"type": "random_delay", "min_delay_ms": 10, "max_delay_ms": 90}},
            {"name": "fixed", "repetitions": 2, "fault": {"type": "fixed_delay", "delay_ms": 40}},
            {"name": "err", "repetitions": 4, "fault": {"type": "http_error", "status": 503, "onset_after": 2}},
            {"name": "drop", "repetitions": 2, "fault": {"type": "connection_drop"}},
            {"name": "to", "repetitions": 1, "fault": {"type": "timeout"}},
        ],
    }
    data.update(overrides)
    return data


def with_scenario(index, **changes):
    data = manifest_data()
    data["scenarios"][index].update(changes)
    return data


# --- manifest doğrulaması ---
def test_valid_manifest_and_example_file():
    manifest = parse_manifest(manifest_data())
    assert manifest.experiment_id == "exp-1" and manifest.dataset_kind == "synthetic"
    assert [s.path for s in manifest.scenarios][:2] == ["/synthetic/ok", "/synthetic/slow"]
    example, digest = load_manifest(EXAMPLE)
    assert example.experiment_id == "syn-fault-mix-001" and len(digest) == 64
    check_plan_limits(example, build_plan(example))
    assert guard_forecast(build_plan(example), example.limits) is None


@pytest.mark.parametrize("change, message", [
    (lambda d: d.pop("seed"), "eksik alan.*seed"),
    (lambda d: d.update(extra=1), "bilinmeyen alan.*extra"),
    (lambda d: d["scenarios"][0].update(colour="red"), r"scenarios\[1\]: bilinmeyen alan"),
    (lambda d: d["scenarios"][0].pop("fault"), r"scenarios\[1\]: eksik alan.*fault"),
    (lambda d: d["scenarios"][2]["fault"].pop("delay_ms"), "eksik alan.*delay_ms"),
    (lambda d: d["scenarios"][2]["fault"].update(status=500), "bilinmeyen alan.*status"),
    (lambda d: d["scenarios"][0]["fault"].update(onset_after=1), "bilinmeyen alan.*onset_after"),
    (lambda d: d.update(dataset_kind="measurement"), "dataset_kind 'synthetic' olmalı"),
    (lambda d: d.update(experiment_type="load_test"), "experiment_type"),
    (lambda d: d.update(manifest_version=2), "manifest_version"),
    (lambda d: d.update(experiment_id="../x"), "experiment_id"),
    (lambda d: d.update(seed=-1), "seed"),
    (lambda d: d.update(seed=True), "seed"),
    (lambda d: d.update(timeout_seconds=60), "timeout_seconds"),
    (lambda d: d.update(scenarios=[]), "boş olmayan"),
    (lambda d: d["scenarios"][1].update(name="ok"), "benzersiz"),
    (lambda d: d["scenarios"][1].update(name="Büyük Harf"), "name"),
    (lambda d: d["scenarios"][1].update(method="DELETE"), "GET veya POST"),
    (lambda d: d["scenarios"][1].update(repetitions=0), "repetitions"),
    (lambda d: d["scenarios"][1].update(repetitions=5000), "repetitions"),
    (lambda d: d.update(limits={"max_requests": 5}), "max_requests"),
    (lambda d: d.update(limits={"max_requests": 99999}), "en fazla"),
])
def test_invalid_manifest_rejected(change, message):
    data = manifest_data()
    change(data)
    with pytest.raises(ManifestError, match=message):
        parse_manifest(data)


@pytest.mark.parametrize("fault, message", [
    ({"type": "explode"}, "fault.type bilinmiyor"),
    ({"type": "fixed_delay", "delay_ms": -1}, "delay_ms"),
    ({"type": "fixed_delay", "delay_ms": 600}, "delay_ms"),  # > zaman aşımının yarısı (500 ms): belirsiz beklenti
    ({"type": "fixed_delay", "delay_ms": float("nan")}, "sonlu"),
    ({"type": "random_delay", "min_delay_ms": 50, "max_delay_ms": 10}, "büyük olamaz"),
    ({"type": "random_delay", "min_delay_ms": 0, "max_delay_ms": 10_000}, "max_delay_ms"),
    ({"type": "http_error", "status": 200}, "status"),
    ({"type": "http_error", "status": 600}, "status"),
    ({"type": "http_error", "status": 500, "onset_after": 4}, "onset_after"),  # hiç uygulanmaz
    ({"type": "connection_drop", "onset_after": -1}, "onset_after"),
    ("none", "nesne"),
])
def test_invalid_fault_rejected(fault, message):
    with pytest.raises(ManifestError, match=message):
        parse_manifest(with_scenario(1, fault=fault))


def test_plan_duration_must_fit_limits():
    data = manifest_data(limits={"max_duration_seconds": 1})
    data["scenarios"][2].update(repetitions=100, fault={"type": "fixed_delay", "delay_ms": 400})
    manifest = parse_manifest(data)
    with pytest.raises(ManifestError, match="max_duration_seconds"):
        check_plan_limits(manifest, build_plan(manifest))


# --- plan ---
def test_plan_order_matches_engine_execution_order():
    plan = build_plan(parse_manifest(manifest_data()))
    assert [e.index for e in plan.entries] == list(range(1, 18))
    ok = plan.route("ok")
    assert [(e.warmup, e.iteration, e.route_index) for e in ok] == [(True, 1, 1), (False, 1, 2), (False, 2, 3),
                                                                   (False, 3, 4)]
    err = plan.route("err")
    assert [e.fault for e in err] == ["none", "none", "http_error", "http_error"]  # onset_after = 2
    assert [e.expected_outcome for e in err] == ["success", "success", "http_error", "http_error"]
    assert err[2].expected_status == 503
    drop, timeout = plan.route("drop")[0], plan.route("to")[0]
    assert (drop.status, drop.expected_error_type) == (None, "connection_error")
    assert (timeout.expected_error_type, timeout.delay_ms) == ("timeout", timeout_hold_ms(1.0)) == ("timeout", 1500.0)
    fixed = plan.route("fixed")
    assert all(e.delay_ms == 40.0 and e.min_duration_ms == 40.0 for e in fixed)


def test_same_seed_same_plan_different_seed_different_random_delays():
    a = build_plan(parse_manifest(manifest_data()))
    b = build_plan(parse_manifest(manifest_data()))
    c = build_plan(parse_manifest(manifest_data(seed=8)))
    assert a == b and a.sha256 == b.sha256
    assert a.sha256 != c.sha256
    delays_a = [e.delay_ms for e in a.route("slow")]
    assert delays_a != [e.delay_ms for e in c.route("slow")]
    assert all(10 <= d <= 90 for d in delays_a) and len(set(delays_a)) == 4
    # Rastgele olmayan senaryolar tohumdan bağımsızdır.
    assert [e.to_dict() for e in a.route("err")] == [e.to_dict() for e in c.route("err")]


def test_random_delays_of_a_scenario_do_not_depend_on_other_scenarios():
    full = build_plan(parse_manifest(manifest_data()))
    data = manifest_data()
    data["scenarios"] = [s for s in data["scenarios"] if s["name"] == "slow"]
    alone = build_plan(parse_manifest(data))
    assert [e.delay_ms for e in full.route("slow")] == [e.delay_ms for e in alone.route("slow")]


def test_plan_hash_is_stable_value():
    # Algoritma veya kanonik biçim değişirse bu özet değişir; bu bilinçli bir sürüm kararı olmalıdır.
    plan = build_plan(parse_manifest(manifest_data()))
    assert plan.sha256 == build_plan(parse_manifest(copy.deepcopy(manifest_data()))).sha256
    assert plan.to_dict()["plan_algorithm_version"] == 1


def test_guard_forecast_warns_when_expected_errors_trip_limits():
    data = manifest_data(limits={"max_consecutive_transport_errors": 2})
    plan = build_plan(parse_manifest(data))
    assert "max_consecutive_transport_errors" in guard_forecast(plan, parse_manifest(data).limits)


# --- etiketler ---
def observed_for(entry, *, run_id="r1", **overrides):
    common = dict(run_id=run_id, seq=entry.index, scenario=entry.scenario, iteration=entry.iteration,
                  warmup=entry.warmup, offset_ms=entry.index * 10.0, url=f"http://127.0.0.1:1/synthetic/{entry.scenario}")
    if entry.expected_outcome == "transport_error":
        return make_failed_result(**common, error_type=entry.expected_error_type, **overrides)
    status = entry.expected_status
    duration = (entry.min_duration_ms or 0.0) + 2.0
    values = dict(common, duration_ms=duration, elapsed_ms=duration, status_code=status, http_ok=status < 400)
    values.update(overrides)
    return make_result(**values)


def server_for(plan, entries=None):
    entries = plan.entries if entries is None else entries
    return {"events": [{"kind": "planned", "route": e.scenario, "route_index": e.route_index,
                        "planned_fault": e.fault, "status_sent": e.status, "hold_ms_actual": e.delay_ms,
                        "outcome": "responded"} for e in entries],
            "unexpected_requests": 0, "dropped_events": 0, "errors": []}


def labels(manifest, plan, results, server=None, status="completed", partial=False):
    return build_labels(manifest, "f" * 64, plan, run_id="r1", partial=partial, execution_status=status,
                        results=results, result_files=[], server=server or server_for(plan), server_events_file=None)


def setup_plan():
    manifest = parse_manifest(manifest_data())
    return manifest, build_plan(manifest)


def test_all_expectations_confirmed_is_valid():
    manifest, plan = setup_plan()
    doc = labels(manifest, plan, [observed_for(e) for e in plan.entries])
    assert doc["verdict"] == {"valid": True, "reasons": []}
    assert doc["summary"]["confirmed"] == len(plan.entries) and doc["dataset_kind"] == "synthetic"
    record = doc["requests"][-1]
    assert record["planned"]["fault"] == "timeout" and record["observed"]["error_type"] == "timeout"
    assert record["agreement"] == {"match": True, "reasons": []} and record["label_status"] == "confirmed"
    assert doc["experiment"]["plan_sha256"] == plan.sha256 and doc["experiment"]["manifest"]["seed"] == 7


def test_expected_and_observed_are_kept_separate_and_mismatches_reported():
    manifest, plan = setup_plan()
    results = [observed_for(e) for e in plan.entries]
    err_index = plan.route("err")[2].index - 1
    results[err_index] = observed_for(plan.entries[err_index], status_code=500, http_ok=False)  # 503 bekleniyordu
    fixed_index = plan.route("fixed")[0].index - 1
    results[fixed_index] = observed_for(plan.entries[fixed_index], duration_ms=5.0, elapsed_ms=5.0)
    ok_index = plan.route("ok")[1].index - 1
    results[ok_index] = make_failed_result(**{k: getattr(results[ok_index], k) for k in
                                              ("run_id", "seq", "scenario", "iteration", "warmup", "offset_ms")})
    doc = labels(manifest, plan, results)
    assert doc["verdict"]["valid"] is False
    assert [r["code"] for r in doc["verdict"]["reasons"]] == ["expectation_mismatch"]
    rec = doc["requests"][err_index]
    assert rec["expected"]["status"] == 503 and rec["observed"]["status"] == 500  # beklenen yerine gözlenen yazılmaz
    assert rec["label_status"] == "contradicted" and "beklenen durum 503" in rec["agreement"]["reasons"][0]
    assert "kısa" in doc["requests"][fixed_index]["agreement"]["reasons"][0]
    assert "gözlenen transport_error" in doc["requests"][ok_index]["agreement"]["reasons"][0]
    assert doc["summary"]["contradicted"] == 3


def test_partial_run_marks_not_executed_and_invalid():
    manifest, plan = setup_plan()
    results = [observed_for(e) for e in plan.entries[:5]]
    doc = labels(manifest, plan, results, server=server_for(plan, plan.entries[:5]), status="aborted", partial=True)
    assert doc["verdict"]["valid"] is False
    assert [r["code"] for r in doc["verdict"]["reasons"]] == ["run_incomplete"]
    assert doc["summary"]["not_executed"] == len(plan.entries) - 5
    assert doc["requests"][5]["observed"] is None and doc["requests"][5]["label_status"] == "not_executed"


def test_result_plan_join_mismatch_is_reported():
    manifest, plan = setup_plan()
    results = [observed_for(e) for e in plan.entries]
    results[0] = observed_for(plan.entries[0], scenario="baska")
    doc = labels(manifest, plan, results)
    assert "result_plan_mismatch" in [r["code"] for r in doc["verdict"]["reasons"]]
    assert doc["requests"][0]["label_status"] == "unjoinable"


@pytest.mark.parametrize("mutate, code", [
    (lambda s: s["events"].pop(3), "server_missing_arrival"),
    (lambda s: s["events"][3].update(planned_fault="http_error"), "server_fault_mismatch"),
    (lambda s: s["events"].append({**s["events"][0], "route_index": 99}), "server_extra_arrivals"),
    (lambda s: s.update(unexpected_requests=2), "unexpected_server_requests"),
    (lambda s: s.update(dropped_events=1), "server_events_truncated"),
    (lambda s: s.update(errors=["ValueError"]), "server_errors"),
])
def test_server_inconsistencies_invalidate_experiment(mutate, code):
    manifest, plan = setup_plan()
    server = server_for(plan)
    mutate(server)
    doc = labels(manifest, plan, [observed_for(e) for e in plan.entries], server=server)
    assert doc["verdict"]["valid"] is False and code in [r["code"] for r in doc["verdict"]["reasons"]]


def test_field_roles_classify_every_result_field_exactly_once():
    roles = list(MODEL_INPUT_CANDIDATE_FIELDS) + list(IDENTIFIER_FIELDS) + list(EXCLUDED_FIELDS)
    assert sorted(roles) == sorted(RawResult.field_names()) and len(roles) == len(set(roles))


def test_labels_document_declares_ground_truth_fields_separately():
    manifest, plan = setup_plan()
    roles = labels(manifest, plan, [observed_for(e) for e in plan.entries])["field_roles"]
    assert "planned.fault" in roles["ground_truth_only"] and "scenario" in roles["identifiers_not_features"]
    assert not set(roles["ground_truth_only"]) & set(RawResult.field_names())


# --- metadata, okuyucu ve analiz: veri türü ayrımı ---
SYN_META = {"experiment_id": "exp-1", "plan_sha256": "a" * 64, "manifest_sha256": "b" * 64, "seed": 7}


def write_run(tmp_path, metadata):
    results = [make_result(run_id="r1")]
    ResultStore(tmp_path).save("r1", results, metadata)


def test_metadata_requires_consistent_dataset_kind(tmp_path):
    config = LabConfig(base_url="http://127.0.0.1:1", output_dir=tmp_path, scenarios_file=tmp_path / "s.json")
    args = dict(config_path=None, monotonic_duration_ms=1.0, code={"git_commit": None, "git_dirty": None})
    meta = build_run_metadata(config, [], "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00",
                              dataset_kind="synthetic", synthetic=dict(SYN_META), **args)
    assert meta["dataset_kind"] == "synthetic" and meta["synthetic"]["experiment_id"] == "exp-1"
    for kwargs in ({"dataset_kind": "real"}, {"dataset_kind": "synthetic"}, {"synthetic": dict(SYN_META)}):
        with pytest.raises(ValueError):
            build_run_metadata(config, [], "a", "b", **args, **kwargs)


def test_execute_run_rejects_inconsistent_dataset_kind_before_any_request(tmp_path):
    config = LabConfig(base_url="http://127.0.0.1:1", output_dir=tmp_path, scenarios_file=tmp_path / "s.json")

    def factory():
        raise AssertionError("taşıyıcı oluşturulmamalı")

    with pytest.raises(PreflightError, match="synthetic"):
        execute_run(config, [Scenario(name="a", method="GET", path="/a")], config_path=None, run_id="r1",
                    resolver=lambda h, p: ["127.0.0.1"], transport_factory=factory, dataset_kind="synthetic")
    assert not tmp_path.joinpath("r1.json").exists()


def test_reader_reports_dataset_kind_and_validates_synthetic_section(tmp_path):
    write_run(tmp_path / "ok", {"dataset_kind": "synthetic", "synthetic": dict(SYN_META)})
    assert load_run(tmp_path / "ok", "r1").dataset_kind == "synthetic"
    write_run(tmp_path / "m", {"dataset_kind": "measurement"})
    assert load_run(tmp_path / "m", "r1").dataset_kind == "measurement"
    assert load_run(GOLDEN, "golden-v2-a1331fd-completed").dataset_kind is None  # eski dosya: bilinmiyor

    for name, meta, message in (
        ("a", {"dataset_kind": "gercek"}, "dataset_kind bilinmiyor"),
        ("b", {"dataset_kind": "synthetic"}, "synthetic bölümü yok"),
        ("c", {"synthetic": dict(SYN_META)}, "açıkça işaretlenmeli"),
        ("d", {"dataset_kind": "measurement", "synthetic": dict(SYN_META)}, "açıkça işaretlenmeli"),
        ("e", {"dataset_kind": "synthetic", "synthetic": {**SYN_META, "plan_sha256": ""}}, "plan_sha256"),
        ("f", {"dataset_kind": "synthetic", "synthetic": {**SYN_META, "seed": "7"}}, "seed"),
    ):
        write_run(tmp_path / name, meta)
        with pytest.raises(RunDataError, match=message):
            load_run(tmp_path / name, "r1")


def test_analysis_flags_synthetic_data_and_ignores_labels(tmp_path):
    write_run(tmp_path / "s", {"dataset_kind": "synthetic", "synthetic": dict(SYN_META)})
    analysis = build_analysis(load_run(tmp_path / "s", "r1"))
    assert analysis["run"]["dataset_kind"] == "synthetic"
    assert analysis["run"]["synthetic"] == SYN_META
    assert "synthetic_data" in [w["code"] for w in analysis["warnings"]]
    assert any(text.startswith("Sentetik veri") for text in analysis["limitations"])

    write_run(tmp_path / "m", {"dataset_kind": "measurement"})
    measured = build_analysis(load_run(tmp_path / "m", "r1"))
    assert measured["run"]["synthetic"] is None and "synthetic_data" not in [w["code"] for w in measured["warnings"]]


def test_manifest_and_label_module_does_not_import_network_code():
    code = (
        "import sys; import hgs2_lab.synthetic; "
        "bad = sorted(m for m in ('requests', 'urllib3', 'http.server', 'http.client', 'socketserver', "
        "'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.synthetic_server') if m in sys.modules); "
        "print(bad)"
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"


# --- CLI: validate / plan (istek göndermez) ---
def test_cli_synthetic_validate(capsys):
    assert main(["synthetic", "validate", "--manifest", str(EXAMPLE)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "syn-fault-mix-001" in out and "plan_sha256:" in out and "dataset_kind: synthetic" in out
    assert "http_error (ilk 3 istek normal)" in out


def test_cli_synthetic_invalid_manifest(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(with_scenario(0, fault={"type": "explode"})), encoding="utf-8")
    assert main(["synthetic", "validate", "--manifest", str(bad)]) == EXIT_ERROR
    assert "Manifest geçersiz" in capsys.readouterr().err
    assert main(["synthetic", "validate", "--manifest", str(tmp_path / "yok.json")]) == EXIT_ERROR


def test_cli_synthetic_plan_output_is_reproducible_and_not_overwritten(tmp_path, capsys):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert main(["synthetic", "plan", "--manifest", str(EXAMPLE), "--output", str(a)]) == EXIT_OK
    assert main(["synthetic", "plan", "--manifest", str(EXAMPLE), "--output", str(b)]) == EXIT_OK
    assert a.read_bytes() == b.read_bytes()  # aynı manifest + seed -> bayt bayt aynı plan
    plan = json.loads(a.read_text(encoding="utf-8"))
    assert plan["seed"] == 20261024 and len(plan["entries"]) == 55
    before = a.read_bytes()
    assert main(["synthetic", "plan", "--manifest", str(EXAMPLE), "--output", str(a)]) == EXIT_STORAGE_ERROR
    assert a.read_bytes() == before


def test_cli_synthetic_plan_warns_about_guard_limits(tmp_path, capsys):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest_data(limits={"max_consecutive_transport_errors": 2})), encoding="utf-8")
    assert main(["synthetic", "plan", "--manifest", str(path)]) == EXIT_OK
    assert "UYARI" in capsys.readouterr().err


# --- F3-B: bekleme mekanizması ve gecikme alanları (soket yok: sunucu başlatılmaz) ---
def delay_plan(delay_ms=5, fault="fixed_delay", repetitions=1):
    data = manifest_data(scenarios=[{"name": "d", "repetitions": repetitions,
                                     "fault": {"type": fault, "delay_ms": delay_ms} if fault == "fixed_delay"
                                     else {"type": fault}}])
    return build_plan(parse_manifest(data))


def test_hold_waits_at_least_planned_and_reports_interval():
    from hgs2_lab.synthetic_server import SyntheticServer

    srv = SyntheticServer(delay_plan())
    started, ended, stopped = srv._hold(5.0)
    assert not stopped and ended > started
    assert (ended - started) / 1e6 >= 5.0  # planlanandan kısa olamaz


def test_hold_reacts_to_stop_within_a_slice_and_does_not_busy_wait():
    import threading
    import time

    from hgs2_lab.synthetic_server import HOLD_SLICE_SECONDS, SyntheticServer

    assert HOLD_SLICE_SECONDS <= 0.05  # durdurma tepki süresinin üst sınırı küçük kalmalı
    srv = SyntheticServer(delay_plan())
    timer = threading.Timer(0.3, srv._stop_event.set)
    cpu0, wall0 = time.process_time(), time.perf_counter()
    timer.start()
    try:
        started, ended, stopped = srv._hold(10_000.0)
    finally:
        timer.cancel()
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    assert stopped and 0.3 <= (ended - started) / 1e9 < 0.3 + 1.0
    assert cpu < wall * 0.5  # meşgul bekleme olsaydı ~%100 olurdu


class _FakeHandler:
    """`_handle` için soketsiz handler taklidi; yanıt yazımı istemci gitmiş gibi hata verir."""

    def __init__(self, path, fail_on_send=False):
        self.headers = {}
        self.command, self.path = "GET", path
        self.close_connection = False
        self.sent = []
        self._fail = fail_on_send

    def send_plain(self, status, body, close=False):
        if self._fail:
            raise ConnectionResetError("istemci gitti")
        self.sent.append(status)


def test_hold_is_recorded_even_if_client_is_gone_before_response():
    from hgs2_lab.synthetic_server import SyntheticServer

    srv = SyntheticServer(delay_plan(delay_ms=2))
    srv._handle(_FakeHandler("/synthetic/d", fail_on_send=True))
    (event,) = srv.snapshot()["events"]
    assert event["outcome"] == "client_gone" and event["status_sent"] is None
    assert event["hold_ms_actual"] is not None and event["hold_ms_actual"] >= 2.0
    assert event["hold_ms_actual"] == (event["hold_ended_ns"] - event["hold_started_ns"]) / 1e6


def test_event_timing_fields_are_ordered_and_hold_only_when_planned():
    from hgs2_lab.synthetic_server import SyntheticServer

    plan = build_plan(parse_manifest(manifest_data(scenarios=[
        {"name": "ok", "repetitions": 1, "fault": {"type": "none"}},
        {"name": "d", "repetitions": 1, "fault": {"type": "fixed_delay", "delay_ms": 3}},
    ])))
    srv = SyntheticServer(plan)
    srv._handle(_FakeHandler("/synthetic/ok"))
    srv._handle(_FakeHandler("/synthetic/d"))
    plain, delayed = srv.snapshot()["events"]
    assert plain["hold_ms_planned"] == 0.0
    assert (plain["hold_ms_actual"], plain["hold_started_ns"], plain["hold_ended_ns"]) == (None, None, None)
    assert delayed["hold_ms_planned"] == 3.0 and delayed["hold_ms_actual"] >= 3.0
    assert delayed["received_ns"] <= delayed["hold_started_ns"] < delayed["hold_ended_ns"] <= delayed["completed_ns"]


def test_server_hold_short_is_detected_but_not_for_stopped_or_non_delay_faults():
    manifest, plan = setup_plan()
    results = [observed_for(e) for e in plan.entries]
    fixed = plan.route("fixed")[0]
    to = plan.route("to")[0]

    server = server_for(plan)
    server["events"][fixed.index - 1]["hold_ms_actual"] = fixed.delay_ms - 0.5  # planlanandan kısa
    doc = labels(manifest, plan, results, server=server)
    assert "server_hold_short" in [r["code"] for r in doc["verdict"]["reasons"]]

    server = server_for(plan)
    server["events"][fixed.index - 1]["hold_ms_actual"] = None  # gecikme hatasında bekleme kaydı yok
    assert not labels(manifest, plan, results, server=server)["verdict"]["valid"]

    server = server_for(plan)
    server["events"][to.index - 1].update(hold_ms_actual=10.0, outcome="stopped")  # kapanışta kesilen zaman aşımı
    assert labels(manifest, plan, results, server=server)["verdict"]["valid"]


def test_labels_define_the_four_timing_concepts_separately():
    manifest, plan = setup_plan()
    doc = labels(manifest, plan, [observed_for(e) for e in plan.entries])
    timing = doc["timing_fields"]
    assert {"planned.delay_ms", "server.hold_ms_actual", "observed.duration_ms"} <= set(timing)
    assert "server.hold_ms_actual" in doc["field_roles"]["ground_truth_only"]  # gerçek etiket, model girdisi değil
    fixed = next(r for r in doc["requests"] if r["planned"]["fault"] == "fixed_delay")
    assert fixed["planned"]["delay_ms"] == 40.0 and fixed["server"]["hold_ms_actual"] == 40.0
    assert fixed["observed"]["duration_ms"] != fixed["server"]["hold_ms_actual"]  # ayrı kaynaklar, ayrı alanlar
