"""Çevrimdışı analiz testleri: istatistik doğruluğu, örneklem yeterliliği, ısınma/hata ayrımı, throughput,
determinizm ve üzerine yazmayan çıktı (ağ yok; sentetik veriler)."""

import errno
import hashlib
import json
import os
import random
import statistics
from fractions import Fraction

import pytest
from factories import make_failed_result, make_result

from hgs2_lab.analysis import (
    STATIC_LIMITATIONS,
    AnalysisError,
    AnalysisExistsError,
    AnalysisParams,
    bootstrap_percentile_intervals,
    build_analysis,
    build_document,
    canonical_json,
    default_output_path,
    min_samples_for_percentile,
    quantile,
    write_document,
)
from hgs2_lab.clock import ClockAnchor
from hgs2_lab.reader import InputFile, RunData

FAST = AnalysisParams(bootstrap_resamples=200)
CLEAN_META = {
    "schema_version": 2, "run_id": "r1",
    "code": {"git_commit": "a" * 40, "git_dirty": False},
    "inputs": {"config_sha256": "c" * 64, "scenarios_sha256": "d" * 64, "hash_errors": {}},
}
COMPLETED_EXEC = {"status": "completed", "stop_reason": None, "planned_requests": 0, "completed_requests": 0}


def req(seq, scenario="s", *, warmup=False, duration=10.0, status=200, ok=True, error=None, offset=None,
        elapsed=None):
    offset = (seq - 1) * 20.0 if offset is None else offset
    common = dict(run_id="r1", seq=seq, scenario=scenario, iteration=1, warmup=warmup, offset_ms=offset)
    if error:
        return make_failed_result(**common, elapsed_ms=elapsed or 30.0, error_type=error)
    return make_result(**common, elapsed_ms=elapsed or duration, duration_ms=duration, status_code=status, http_ok=ok)


def run_data(results, *, partial=False, execution="auto", clock=None, metadata=None):
    results = tuple(results)
    if execution == "auto":
        execution = {**COMPLETED_EXEC, "planned_requests": len(results), "completed_requests": len(results)}
    return RunData(
        run_id="r1", partial=partial, schema_version=2, metadata={**CLEAN_META, **(metadata or {})},
        results=results, files=(InputFile("json", "r1.json", "0" * 64, 10), InputFile("csv", "r1.csv", "1" * 64, 5)),
        execution=execution, clock=clock,
    )


def codes(analysis, scope=None):
    return [w["code"] for w in analysis["warnings"] if scope is None or w["scope"] == scope]


# --- yüzdelik ---
def test_quantile_hand_computed_values():
    data = [1.0, 2.0, 3.0, 4.0]
    assert quantile(data, Fraction(1, 2)) == 2.5
    assert quantile(data, Fraction(9, 10)) == pytest.approx(3.7)  # h = 3 * 0.9 = 2.7 -> 3 + 0.7 * (4 - 3)
    assert quantile(data, Fraction(0)) == 1.0 and quantile(data, Fraction(1)) == 4.0
    assert quantile([7.0], Fraction(99, 100)) == 7.0
    assert quantile([1.0, 3.0, 5.0], Fraction(1, 2)) == 3.0  # tam sıra: interpolasyon yok


def test_quantile_matches_statistics_inclusive_method():
    rng = random.Random(1)
    for n in (2, 3, 37, 101, 1000):
        data = sorted(rng.lognormvariate(3, 0.5) for _ in range(n))
        cuts = statistics.quantiles(data, n=100, method="inclusive")
        for p in (50, 90, 95, 99):
            assert quantile(data, Fraction(p, 100)) == pytest.approx(cuts[p - 1], rel=1e-12)


def test_quantile_rejects_empty_and_out_of_range():
    with pytest.raises(ValueError):
        quantile([], Fraction(1, 2))
    with pytest.raises(ValueError):
        quantile([1.0], Fraction(3, 2))


def test_min_samples_rule():
    assert [min_samples_for_percentile(p, 10) for p in (50, 90, 95, 99)] == [1, 100, 200, 1000]
    assert [min_samples_for_percentile(p, 5) for p in (50, 90, 95, 99)] == [1, 50, 100, 500]
    assert min_samples_for_percentile(97, 10) == 334  # yukarı yuvarlanır: 10 / 0.03 = 333.3


# --- bootstrap ---
def test_bootstrap_is_deterministic_per_seed():
    rng = random.Random(2)
    data = sorted(rng.gauss(100, 10) for _ in range(200))
    assert len(set(data)) == 200
    a = bootstrap_percentile_intervals(data, [50, 90], resamples=300, confidence=Fraction(19, 20), seed=7)
    b = bootstrap_percentile_intervals(data, [50, 90], resamples=300, confidence=Fraction(19, 20), seed=7)
    c = bootstrap_percentile_intervals(data, [50, 90], resamples=300, confidence=Fraction(19, 20), seed=8)
    assert a == b and a != c
    for p in (50, 90):
        lower, upper = a[p]
        assert lower <= quantile(data, Fraction(p, 100)) <= upper


def test_bootstrap_interval_is_degenerate_for_constant_data():
    assert bootstrap_percentile_intervals([5.0] * 30, [50], resamples=100, confidence=Fraction(19, 20),
                                          seed=0) == {50: (5.0, 5.0)}


def test_group_bootstrap_streams_are_independent_of_other_groups():
    a = [req(i, "a", duration=float(i % 17)) for i in range(1, 41)]
    b = [req(i, "b", duration=float(i % 5)) for i in range(41, 61)]
    with_b = build_analysis(run_data(a + b), FAST)
    without_b = build_analysis(run_data(a), FAST)
    assert with_b["scenarios"][0]["response_time_ms"] == without_b["scenarios"][0]["response_time_ms"]


# --- sıfır, tek ve küçük örneklem ---
def test_zero_requests():
    analysis = build_analysis(run_data([]), FAST)
    overall = analysis["overall"]
    assert overall["requests"] == {"total": 0, "warmup": 0, "measured": 0}
    assert overall["rates"]["status"] == "no_data" and overall["rates"]["success_rate"] is None
    rt = overall["response_time_ms"]
    assert rt["status"] == "no_data" and rt["n"] == 0 and rt["min"] is None and rt["median"]["value"] is None
    assert overall["throughput"]["status"] == "no_data"
    assert analysis["scenarios"] == []
    assert codes(analysis, "overall") == ["no_measured_requests"]


def test_single_request():
    analysis = build_analysis(run_data([req(1, duration=12.5)]), FAST)
    rt = analysis["overall"]["response_time_ms"]
    assert (rt["n"], rt["min"], rt["max"]) == (1, 12.5, 12.5)
    assert rt["median"] == {"status": "ok", "value": 12.5, "min_samples": 1,
                            "ci": {"status": "insufficient_sample", "lower": None, "upper": None, "min_samples": 20}}
    for label, needed in (("p90", 100), ("p95", 200), ("p99", 1000)):
        assert rt[label]["status"] == "insufficient_sample" and rt[label]["value"] is None
        assert rt[label]["min_samples"] == needed
    assert analysis["overall"]["rates"]["success_rate"] == 1.0
    assert {"insufficient_sample", "insufficient_sample_ci", "throughput_not_computed"} <= set(codes(analysis))


def test_small_sample_reports_median_but_withholds_tail_percentiles():
    analysis = build_analysis(run_data([req(i, duration=float(i)) for i in range(1, 51)]), FAST)
    rt = analysis["overall"]["response_time_ms"]
    assert rt["median"]["value"] == 25.5 and rt["median"]["ci"]["status"] == "ok"
    assert rt["median"]["ci"]["lower"] <= 25.5 <= rt["median"]["ci"]["upper"]
    assert rt["p90"]["value"] is None and rt["p99"]["value"] is None
    warning = next(w for w in analysis["warnings"] if w["code"] == "insufficient_sample")
    assert "n=50" in warning["message"] and "p90 (gereken 100)" in warning["message"]


def test_large_sample_reports_all_percentiles_with_intervals():
    durations = [float(i) for i in range(1, 1001)]
    analysis = build_analysis(run_data([req(i, duration=d) for i, d in enumerate(durations, start=1)]), FAST)
    rt = analysis["overall"]["response_time_ms"]
    for label, p in (("median", 50), ("p90", 90), ("p95", 95), ("p99", 99)):
        assert rt[label]["status"] == "ok"
        assert rt[label]["value"] == quantile(durations, Fraction(p, 100))
        assert rt[label]["ci"]["status"] == "ok" and rt[label]["ci"]["lower"] <= rt[label]["ci"]["upper"]
    assert rt["p99"]["value"] == pytest.approx(990.01)
    assert "insufficient_sample" not in codes(analysis)


# --- ısınma ve hata türleri ---
def test_warmup_requests_are_counted_separately_and_excluded_from_metrics():
    records = [req(1, warmup=True, duration=5000.0), req(2, warmup=True, error="timeout")]
    records += [req(i, duration=10.0) for i in range(3, 6)]
    overall = build_analysis(run_data(records), FAST)["overall"]
    assert overall["requests"] == {"total": 5, "warmup": 2, "measured": 3}
    assert overall["warmup"]["successful"] == 1 and overall["warmup"]["transport_errors"] == 1
    assert overall["measured"]["failed"] == 0 and overall["rates"]["failure_rate"] == 0.0
    assert overall["response_time_ms"]["max"] == 10.0  # 5000 ms ısınma isteği dağılıma girmez


def test_http_errors_and_transport_errors_are_separated():
    records = [
        req(1, duration=10.0), req(2, duration=11.0),
        req(3, duration=1.0, status=500, ok=False), req(4, duration=2.0, status=404, ok=False),
        req(5, duration=3.0, status=500, ok=False),
        req(6, error="timeout"), req(7, error="connection_error"), req(8, error="timeout"),
    ]
    analysis = build_analysis(run_data(records), FAST)
    m = analysis["overall"]["measured"]
    assert (m["total"], m["http_responses"], m["successful"]) == (8, 5, 2)
    assert (m["http_errors"], m["transport_errors"], m["failed"]) == (3, 3, 6)
    assert m["http_errors_by_status"] == {"404": 1, "500": 2}
    assert m["transport_errors_by_type"] == {"connection_error": 1, "timeout": 2}
    rates = analysis["overall"]["rates"]
    assert (rates["success_rate"], rates["failure_rate"]) == (0.25, 0.75)
    assert (rates["http_error_rate"], rates["transport_error_rate"]) == (0.375, 0.375)
    rt = analysis["overall"]["response_time_ms"]
    assert (rt["n"], rt["min"], rt["max"]) == (2, 10.0, 11.0)  # yalnızca http_ok=true yanıtlar
    assert {"http_errors_present", "transport_errors_present"} <= set(codes(analysis, "overall"))


def test_no_successful_responses():
    analysis = build_analysis(run_data([req(1, error="timeout"), req(2, status=500, ok=False)]), FAST)
    assert analysis["overall"]["response_time_ms"]["status"] == "no_data"
    assert "no_successful_responses" in codes(analysis, "overall")


# --- throughput ---
def test_throughput_for_contiguous_measurement_window():
    records = [req(i, offset=(i - 1) * 10.0, elapsed=5.0, duration=4.0) for i in range(1, 11)]
    records[3] = req(4, offset=30.0, elapsed=5.0, duration=4.0, status=500, ok=False)
    tp = build_analysis(run_data(records), FAST)["overall"]["throughput"]
    assert tp["status"] == "ok" and tp["window_ms"] == 95.0  # ilk başlangıç 0, son bitiş 90 + 5
    assert tp["requests_per_second"] == pytest.approx(10 / 0.095)
    assert tp["successful_per_second"] == pytest.approx(9 / 0.095)


def test_throughput_not_computed_when_window_contains_other_requests():
    records, seq = [], 0
    for name in ("a", "b"):
        seq += 1
        records.append(req(seq, name, warmup=True))
        for _ in range(10):
            seq += 1
            records.append(req(seq, name))
    analysis = build_analysis(run_data(records), FAST)
    assert analysis["overall"]["throughput"]["status"] == "not_computed"
    assert "başka istekler" in analysis["overall"]["throughput"]["reason"]
    assert [s["throughput"]["status"] for s in analysis["scenarios"]] == ["ok", "ok"]  # senaryo içi blok kesintisiz
    assert "pooled_scenarios" in codes(analysis, "overall")


def test_throughput_needs_minimum_requests_and_monotonic_offsets():
    few = build_analysis(run_data([req(i) for i in range(1, 5)]), FAST)["overall"]["throughput"]
    assert few["status"] == "insufficient_sample" and few["requests_per_second"] is None
    records = [req(i, offset=float((i - 1) * 20)) for i in range(1, 11)]
    records[5] = req(6, offset=1.0)
    analysis = build_analysis(run_data(records), FAST)
    assert analysis["overall"]["throughput"]["status"] == "not_computed"
    assert "offsets_not_monotonic" in codes(analysis, "run")


# --- çalıştırma düzeyi sınırlılıklar ---
def test_partial_run_is_flagged():
    execution = {"status": "aborted", "stop_reason": "error_rate", "planned_requests": 10, "completed_requests": 2}
    analysis = build_analysis(run_data([req(1), req(2)], partial=True, execution=execution), FAST)
    assert analysis["run"]["partial"] and analysis["input"]["partial"]
    assert analysis["run"]["execution"] == {"available": True, "status": "aborted", "stop_reason": "error_rate",
                                            "planned_requests": 10, "recorded_requests": 2, "not_executed": 8}
    assert "run_incomplete" in codes(analysis, "run")
    assert any(text.startswith("Kısmi çalıştırma: 2 kayıtlı istek / 10 planlanan") for text in analysis["limitations"])


def test_missing_execution_and_clock_and_unknown_code_are_flagged():
    analysis = build_analysis(run_data([req(1)], execution=None, metadata={"code": None, "inputs": None}), FAST)
    assert analysis["run"]["execution"]["available"] is False
    assert {"execution_metadata_missing", "clock_anchor_missing", "code_state_unknown",
            "input_hash_unavailable"} <= set(codes(analysis, "run"))
    assert analysis["clock"]["available"] is False and analysis["clock"]["telemetry_alignment"] == "unavailable"


def test_clock_anchor_is_reported_without_claiming_cross_process_sync():
    anchor = ClockAnchor.capture(lambda: 100, lambda: 1_767_225_600_000_000_000)
    analysis = build_analysis(run_data([req(1)], clock=anchor), FAST)
    assert analysis["clock"]["available"] is True and analysis["clock"]["anchor"] == anchor.to_dict()
    assert analysis["clock"]["telemetry_alignment"] == "same_process_only"
    assert "doğrulanmamıştır" in analysis["clock"]["note"]
    assert "clock_anchor_missing" not in codes(analysis)


def test_static_limitations_are_always_present():
    limitations = build_analysis(run_data([req(1)]), FAST)["limitations"]
    assert limitations[: len(STATIC_LIMITATIONS)] == list(STATIC_LIMITATIONS)
    assert any("makine öğrenmesi" in text for text in limitations)


def test_input_provenance_and_method_parameters_are_recorded():
    analysis = build_analysis(run_data([req(1)]), AnalysisParams(seed=42, bootstrap_resamples=500))
    assert analysis["input"]["run_id"] == "r1" and analysis["input"]["schema_version"] == 2
    assert [f["sha256"] for f in analysis["input"]["files"]] == ["0" * 64, "1" * 64]
    assert analysis["method"]["parameters"]["seed"] == 42
    assert analysis["method"]["parameters"]["bootstrap_resamples"] == 500
    assert analysis["tool"]["name"] == "hgs2-lab"


# --- determinizm ---
def test_document_content_is_deterministic_and_excludes_generation_time():
    data = run_data([req(i, duration=float(i % 13)) for i in range(1, 61)])
    first = build_document(data, FAST, now=lambda: "2026-01-01T00:00:00+00:00")
    second = build_document(data, FAST, now=lambda: "2027-06-01T12:00:00+00:00")
    assert first["generated_at"] != second["generated_at"]
    assert first["analysis"] == second["analysis"]
    assert canonical_json(first["analysis"]) == canonical_json(second["analysis"])
    assert first["content_sha256"] == second["content_sha256"] == \
        hashlib.sha256(canonical_json(first["analysis"])).hexdigest()

    other_seed = build_document(data, AnalysisParams(bootstrap_resamples=200, seed=1))
    assert other_seed["content_sha256"] != first["content_sha256"]  # parametre değişince içerik değişir


def test_analysis_params_validation():
    for kwargs in ({"seed": -1}, {"seed": True}, {"bootstrap_resamples": 10}, {"confidence": 1.0},
                   {"confidence": 0.2}, {"confidence": float("nan")}, {"min_tail_samples": 0}):
        with pytest.raises(AnalysisError):
            AnalysisParams(**kwargs)
    assert AnalysisParams(confidence=0.95).confidence_fraction == Fraction(19, 20)


# --- çıktı yazımı ---
def test_default_output_path_separates_derived_data(tmp_path):
    assert default_output_path(tmp_path, run_data([])) == tmp_path / "analysis" / "r1.analysis.json"
    assert default_output_path(tmp_path, run_data([], partial=True)).name == "r1.partial.analysis.json"


def test_write_document_never_overwrites(tmp_path):
    path = tmp_path / "out" / "a.json"
    assert write_document({"x": 1}, path) == path
    assert json.loads(path.read_text(encoding="utf-8")) == {"x": 1}
    with pytest.raises(AnalysisExistsError):
        write_document({"x": 2}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"x": 1}
    assert sorted(p.name for p in path.parent.iterdir()) == ["a.json"]  # geçici dosya kalmaz


def test_write_document_loses_race_without_overwriting(tmp_path, monkeypatch):
    path = tmp_path / "a.json"
    real_link = os.link

    def racing_link(src, dst):  # denetimden sonra başka bir süreç dosyayı oluşturmuş olsun
        path.write_text("başkası", encoding="utf-8")
        return real_link(src, dst)

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(AnalysisExistsError):
        write_document({"x": 1}, path)
    assert path.read_text(encoding="utf-8") == "başkası"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]


def test_write_document_falls_back_when_hard_links_unsupported(tmp_path, monkeypatch):
    def no_link(src, dst):
        raise OSError(errno.EPERM, "hard link desteklenmiyor")

    monkeypatch.setattr(os, "link", no_link)
    path = tmp_path / "a.json"
    write_document({"x": 1}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"x": 1}
    with pytest.raises(AnalysisExistsError):
        write_document({"x": 2}, path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]


def test_write_document_rejects_nan_before_touching_disk(tmp_path):
    with pytest.raises(ValueError):
        write_document({"x": float("nan")}, tmp_path / "a.json")
    assert list(tmp_path.iterdir()) == []
