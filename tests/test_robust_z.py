"""Robust Z-score dedektörü (F5) birim testleri: kalibrasyon, skorlama, sızıntı sınırları, metrikler ve CLI.

Ağ ve soket kullanılmaz; özellik tabloları `features.render_csv` ve `observed-v1` politikasıyla testte üretilir.
"""

import hashlib
import json
import math
import os
import random
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from hgs2_lab import detection, robust_z
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.detection import (
    DetectionError,
    TableRow,
    build_evaluation,
    calibrate_from_rows,
    detector_input,
    episodes_of,
    evaluate_split,
    load_feature_table,
    write_evaluation,
)
from hgs2_lab.features import (
    FEATURE_SCHEMA_VERSION,
    FEATURE_TABLE_FORMAT,
    FEATURES_FILE,
    LABELS_FILE,
    MANIFEST_FILE,
    OBSERVED_V1,
    render_csv,
)
from hgs2_lab.synthetic import canonical_json

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


# --- yardımcılar ---------------------------------------------------------------------------------------------
def row(split, run, seq, duration, fault="none", *, success=True, plan=None, scenario="s", status="confirmed",
        offset=None, iteration=None):
    """Bir ölçüm satırı: (features.csv sözlüğü, labels.csv sözlüğü)."""
    plan = plan or run.split(".")[0]
    delay = fault in ("fixed_delay", "random_delay")
    f = {"split": split, "run_id": run, "seq": seq, "campaign_id": "c", "group_id": plan, "plan_id": plan, "seed": 1,
         "iteration": iteration if iteration is not None else seq, "offset_ms": offset if offset is not None else seq * 2.0,
         "elapsed_ms": None if duration is None or not isinstance(duration, (int, float)) else duration + 0.1,
         "duration_ms": duration, "status_code": 200 if success else None, "success": success,
         "error_type": None if success else "timeout", "response_bytes": 2 if success else None}
    lab = {"split": split, "run_id": run, "seq": seq, "scenario": scenario, "planned_fault": fault,
           "planned_status": 200, "planned_delay_ms": 5.0 if delay else None,
           "expected_outcome": "success" if success else "transport_error",
           "hold_ms_actual": 5.5 if delay else None, "label_status": status}
    return f, lab


def write_table(directory, rows, *, tamper_manifest=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    features_text = render_csv(OBSERVED_V1.features, [f for f, _ in rows])
    labels_text = render_csv(OBSERVED_V1.labels, [lab for _, lab in rows])
    (directory / FEATURES_FILE).write_text(features_text, encoding="utf-8", newline="")
    (directory / LABELS_FILE).write_text(labels_text, encoding="utf-8", newline="")
    table = {
        "dataset_kind": "synthetic",
        "dataset": {"dataset_id": "d" * 64, "campaign_id": "c"},
        "split": {"split_seed": 1},
        "policy": OBSERVED_V1.to_dict(),
        "files": {name: {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
                  for name, text in ((FEATURES_FILE, features_text), (LABELS_FILE, labels_text))},
    }
    digest = hashlib.sha256(canonical_json(table)).hexdigest()
    if tamper_manifest:
        table["split"]["split_seed"] = 2
    (directory / MANIFEST_FILE).write_text(json.dumps({
        "format": FEATURE_TABLE_FORMAT, "feature_schema_version": FEATURE_SCHEMA_VERSION, "generated_at": "T",
        "content_sha256": digest, "table": table}), encoding="utf-8")
    return directory


NORMAL_TRAIN = [1.0, 1.1, 1.2, 0.9, 1.05, 1.15, 0.95, 1.3, 1.0, 1.1]


def standard_rows():
    """train: 1 normal + 1 gecikmeli çalıştırma; validation ve test: birer gecikmeli + normal çalıştırma."""
    rows = []
    for i, d in enumerate(NORMAL_TRAIN, start=1):
        rows.append(row("train", "n1.s1", i, d))
    for i, d in enumerate([1.0, 1.1, 30.0, 32.0, 31.0], start=1):
        rows.append(row("train", "lat.s1", i, d, "none" if i <= 2 else "fixed_delay"))
    rows.append(row("train", "err.s1", 1, None, "http_error", success=False))
    for split in ("validation", "test"):
        for i, d in enumerate([1.05, 0.98, 1.12, 9.0, 20.0, 25.0], start=1):  # 4.-6. istek gecikmeli
            rows.append(row(split, f"{split[0]}lat.s1", i, d, "none" if i <= 3 else "random_delay"))
        for i, d in enumerate([1.0, 1.2, 0.2], start=1):
            rows.append(row(split, f"{split[0]}norm.s1", i, d))
    return rows


def table_rows(rows):
    return [TableRow(f["split"], f["run_id"], f["seq"], f, lab) for f, lab in rows]


# --- 1-6: kalibrasyon ve skorlama ------------------------------------------------------------------------------
def test_calibration_computes_median_and_mad_in_log_space():
    xs = [0.0, 0.1, 0.2, 0.3, 0.4]
    b = robust_z.calibrate([math.exp(x) for x in xs])
    assert b.n == 5 and b.status == robust_z.BASELINE_OK
    assert b.median_log == pytest.approx(0.2) and b.mad_log == pytest.approx(0.1)
    assert b.median_duration_ms == pytest.approx(math.exp(0.2))
    # Elle: medyan(x) ve medyan(|x - medyan|), çift sayıda öğede ortalama
    b2 = robust_z.calibrate([math.exp(x) for x in (0.0, 0.2, 0.4, 1.0)])
    assert b2.median_log == pytest.approx(0.3) and b2.mad_log == pytest.approx(0.2)


def test_large_delay_is_flagged_and_threshold_is_strict_upper_tail():
    b = robust_z.calibrate([math.exp(x) for x in (0.0, 0.1, 0.2, 0.3, 0.4)])
    big = robust_z.score(b, 10.0)
    assert big.status == "scored" and big.alarm is True
    assert big.z == pytest.approx(0.6745 * (math.log(10.0) - 0.2) / 0.1)
    edge = robust_z.threshold_duration_ms(b)  # z > 3.5 ⇔ duration > edge
    assert edge == pytest.approx(math.exp(0.2 + 3.5 * 0.1 / 0.6745))
    assert robust_z.score(b, edge * 1.001).alarm is True and robust_z.score(b, edge * 0.999).alarm is False


def test_low_latency_is_not_an_anomaly():
    b = robust_z.calibrate(NORMAL_TRAIN)
    low = robust_z.score(b, 0.001)
    assert low.z < -3.5 and low.alarm is False  # yalnızca üst kuyruk


def test_scores_are_deterministic_and_calibration_is_order_independent():
    shuffled = NORMAL_TRAIN[:]
    random.Random(3).shuffle(shuffled)
    b1, b2 = robust_z.calibrate(NORMAL_TRAIN), robust_z.calibrate(shuffled)
    assert b1 == b2
    assert [robust_z.score(b1, d) for d in (0.5, 1.0, 5.0, 50.0)] == [robust_z.score(b2, d) for d in (0.5, 1.0, 5.0, 50.0)]


@pytest.mark.parametrize("values", [[1.5] * 7, [2.0], [1.0, 1.0, 1.0, 9.0]])
def test_zero_mad_gives_degenerate_baseline_and_no_scores(values):
    b = robust_z.calibrate(values)
    assert b.mad_log == 0 and b.status == robust_z.BASELINE_DEGENERATE
    p = robust_z.score(b, 100.0)
    assert (p.status, p.z, p.alarm, p.reason) == ("degenerate_baseline", None, None, "mad_zero")
    assert robust_z.threshold_duration_ms(b) is None
    assert robust_z.score(b, 100.0) == p  # deterministik


INVALID = [(0, "non_positive"), (0.0, "non_positive"), (-1.0, "non_positive"), (float("nan"), "nan"),
           (float("inf"), "infinite"), (float("-inf"), "infinite"), (None, "missing"), (True, "not_a_number"),
           ("1.0", "not_a_number")]


@pytest.mark.parametrize("value,reason", INVALID)
def test_invalid_durations_are_never_treated_as_normal(value, reason):
    b = robust_z.calibrate(NORMAL_TRAIN)
    p = robust_z.score(b, value)
    assert (p.status, p.reason, p.z, p.alarm) == ("invalid_input", reason, None, None)
    with pytest.raises(robust_z.CalibrationError, match=reason):
        robust_z.calibrate(NORMAL_TRAIN + [value])  # sessizce dışlanmaz


def test_empty_calibration_set_is_an_error():
    with pytest.raises(robust_z.CalibrationError, match="boş"):
        robust_z.calibrate([])


# --- 7-10: girdi politikası ve kalibrasyon kapsamı --------------------------------------------------------------
def test_detector_input_is_an_explicit_duration_only_allowlist():
    assert robust_z.INPUT_FIELDS == ("duration_ms",)
    f, lab = row("test", "r.s1", 1, 2.5)
    assert detector_input(TableRow("test", "r.s1", 1, f, lab)) == {"duration_ms": 2.5}
    # Manifest offset_ms'i observed_feature olarak işaretler; dedektör girdisi rolden türetilmez.
    roles = {c.name: c.role for c in OBSERVED_V1.features}
    assert roles["offset_ms"] == "observed_feature" and "offset_ms" not in robust_z.INPUT_FIELDS
    assert build_evaluation_from(standard_rows())["detector"]["input_fields"] == ["duration_ms"]


def build_evaluation_from(rows):
    with tempfile.TemporaryDirectory() as d:
        return build_evaluation(write_table(Path(d) / "ft", rows))


def predictions(ev):
    return [(p["split"], p["run_id"], p["seq"], p["status"], p["x"], p["z"], p["alarm"]) for p in ev["predictions"]]


def test_position_fields_design_metadata_and_labels_do_not_change_predictions():
    base = build_evaluation_from(standard_rows())
    rng = random.Random(7)
    perturbed = []
    for f, lab in standard_rows():
        f = dict(f, iteration=rng.randint(1, 999), offset_ms=rng.uniform(0, 1e6), seed=rng.randint(0, 9))
        lab = dict(lab, planned_delay_ms=rng.uniform(1, 99), hold_ms_actual=rng.uniform(1, 99),
                   expected_outcome="success", scenario=f"x{rng.randint(0, 9)}")
        if f["split"] != "train" and lab["planned_fault"] in ("none", "random_delay"):  # değerlendirme etiketleri
            lab["planned_fault"] = rng.choice(["none", "random_delay", "fixed_delay"])
        perturbed.append((f, lab))
    other = build_evaluation_from(perturbed)
    assert predictions(other) == predictions(base)  # (anahtar, x, z, alarm) birebir aynı
    assert other["calibration"]["baseline"] == base["calibration"]["baseline"]
    # seq yalnızca anahtardır: train dışı satırların seq'leri kaydırılsa da skorlar değişmez
    shifted = [(dict(f, seq=f["seq"] + 100), dict(lab, seq=lab["seq"] + 100)) if f["split"] != "train" else (f, lab)
               for f, lab in standard_rows()]
    assert [p[3:] for p in predictions(build_evaluation_from(shifted))] == [p[3:] for p in predictions(base)]


def test_calibration_uses_only_confirmed_successful_normal_train_rows():
    rows = standard_rows()
    rows += [row("train", "u.s1", 1, 500.0, status="contradicted"),  # doğrulanmamış normal
             row("train", "f.s1", 1, None, success=False)]  # başarısız normal
    rows_t = table_rows(rows)
    baseline, info = calibrate_from_rows(rows_t)
    expected = robust_z.calibrate(NORMAL_TRAIN + [1.0, 1.1])  # n1 + lat'ın onset öncesi iki normal satırı
    assert baseline == expected
    assert info["splits_used"] == ["train"] and info["selected_rows"] == 12
    assert info["excluded_train_rows"] == {"not_normal": 4, "unconfirmed_label": 1, "unsuccessful": 1}


def test_validation_and_test_data_never_enter_calibration():
    base, _ = calibrate_from_rows(table_rows(standard_rows()))
    changed = [(dict(f, duration_ms=f["duration_ms"] * 1000 if f["duration_ms"] else None), lab)
               if f["split"] != "train" else (f, lab) for f, lab in standard_rows()]
    changed += [row("validation", "vx.s1", 1, 1e6), row("test", "tx.s1", 1, 1e-6)]
    assert calibrate_from_rows(table_rows(changed))[0] == base
    # train'in anormal satırları da baseline'a girmez
    anomalous = [(dict(f, duration_ms=999.0), lab) if lab["planned_fault"] != "none" and f["success"] else (f, lab)
                 for f, lab in standard_rows()]
    assert calibrate_from_rows(table_rows(anomalous))[0] == base
    with pytest.raises(robust_z.CalibrationError):  # train normal yoksa kalibrasyon yok (val/test'e düşülmez)
        calibrate_from_rows(table_rows([r for r in standard_rows() if r[0]["split"] != "train"]))


def test_invalid_duration_in_train_normal_fails_calibration_but_is_reported_elsewhere(tmp_path):
    bad = standard_rows() + [row("train", "n1.s1", 99, float("nan"))]
    with pytest.raises(robust_z.CalibrationError, match="nan"):
        build_evaluation(write_table(tmp_path / "a", bad))
    ev = build_evaluation(write_table(tmp_path / "b", standard_rows() + [row("test", "tnorm.s1", 9, float("inf")),
                                                                         row("test", "tnorm.s1", 10, 0.0)]))
    test = ev["splits"]["test"]
    assert test["unscored_in_scope"] == {"invalid_input:infinite": 1, "invalid_input:non_positive": 1}
    assert test["scored_rows"] == test["in_scope_rows"] - 2  # geçersizler normal sayılmaz, metriklere girmez


# --- metrikler ve epizotlar ------------------------------------------------------------------------------------
def test_metrics_on_standard_table(tmp_path):
    ev = build_evaluation(write_table(tmp_path / "ft", standard_rows()))
    v = ev["splits"]["validation"]
    rl = v["request_level"]
    assert (rl["tp"], rl["fp"], rl["tn"], rl["fn"]) == (3, 0, 6, 0)
    assert rl["precision"]["value"] == 1.0 and rl["recall"]["value"] == 1.0 and rl["false_positive_rate"]["value"] == 0.0
    ep = v["episodes"]
    assert (ep["episodes"], ep["evaluable"], ep["detected"]) == (1, 1, 1)
    assert ep["records"][0]["start_seq"] == 4 and ep["records"][0]["request_detection_delay"] == 0
    assert ep["records"][0]["start_to_alarm_request_offset_ms"] == 0.0
    assert v["normal_false_alarms"]["normal_only_runs"]["runs"] == 1
    assert v["by_family"]["fixed_delay"]["represented"] is False
    assert v["coverage"]["latency_families_not_represented"] == ["fixed_delay"]
    train = ev["splits"]["train"]
    assert train["excluded"] == {"excluded_unsuccessful": {"http_error": 1}}  # HTTP hatası görevin dışında
    assert train["role"].startswith("calibration_in_sample")
    assert all(p["status"] == "scored" for p in ev["predictions"])
    assert not any(p["run_id"] == "err.s1" for p in ev["predictions"])  # hatalı istek dedektöre verilmez


def test_episode_definition_delay_and_pre_episode_false_alarm():
    base = robust_z.calibrate(NORMAL_TRAIN)
    rows = table_rows([
        row("test", "a.s1", 1, 1.0), row("test", "a.s1", 2, 50.0),  # epizot öncesi alarm: FP
        row("test", "a.s1", 3, 1.0, "random_delay", offset=10.0), row("test", "a.s1", 4, 50.0, "random_delay", offset=13.5),
        row("test", "a.s1", 5, 1.0),
        row("test", "a.s1", 6, 50.0, "random_delay", offset=20.0),  # ayrı (ikinci) epizot
        row("test", "a.s1", 7, 50.0, "fixed_delay", scenario="other"),  # başka senaryo: ayrı epizot
        row("test", "a.s1", 8, None, "fixed_delay", success=False, scenario="third"),  # değerlendirilemez
    ])
    assert [[r.seq for r in e] for e in episodes_of(rows)] == [[7], [3, 4], [6], [8]]  # (run_id, scenario) sırası
    preds = {r.key: robust_z.score(base, r.features["duration_ms"]) for r in rows
             if detection.task_scope(r) == detection.SCOPE_IN}
    s = evaluate_split("test", rows, preds)
    recs = {e["start_seq"]: e for e in s["episodes"]["records"]}
    assert recs[3]["detected"] is True and recs[3]["request_detection_delay"] == 1
    assert recs[3]["start_to_alarm_request_offset_ms"] == 3.5  # istek başlangıçları arası; alarm zamanı değil
    assert recs[6]["request_detection_delay"] == 0 and recs[7]["detected"] is True
    assert recs[8]["evaluable"] is False and recs[8]["detected"] is None
    assert s["episodes"]["detection_rate"] == {"value": 1.0, "numerator": 3, "denominator": 3, "status": "ok"}
    assert s["request_level"]["fp"] == 1 and s["request_level"]["fn"] == 1


def test_episode_counted_once_undetected_in_denominator_and_no_fabricated_wall_clock_delay():
    base = robust_z.calibrate(NORMAL_TRAIN)
    rows = table_rows([
        row("test", "a.s1", 1, 1.0),
        row("test", "a.s1", 2, 1.0, "fixed_delay"), row("test", "a.s1", 3, 50.0, "fixed_delay"),
        row("test", "a.s1", 4, 60.0, "fixed_delay"),  # ikinci alarm: aynı epizot, ikinci tespit sayılmaz
        row("test", "a.s1", 5, None, "http_error", success=False),  # epizodu bitirir, epizoda girmez
        row("test", "a.s1", 6, None, "fixed_delay", success=False),  # gecikme planlı ama başarısız: skorlanmaz
        row("test", "a.s1", 7, 1.0, "fixed_delay"),  # alarm yok: tespit edilmeyen epizot
        row("test", "a.s1", 8, None, "none", success=False),  # başarısız normal: TN değildir
    ])
    preds = {r.key: robust_z.score(base, r.features["duration_ms"]) for r in rows
             if detection.task_scope(r) == detection.SCOPE_IN}
    s = evaluate_split("test", rows, preds)
    ep = s["episodes"]
    first, second = ep["records"]
    assert (first["start_seq"], first["end_seq"], first["first_alarm_seq"]) == (2, 4, 3)
    assert first["request_detection_delay"] == 1 and first["start_to_alarm_request_offset_ms"] == 2.0
    assert (second["start_seq"], second["end_seq"], second["unsuccessful_rows"]) == (6, 7, 1)
    assert second["evaluable"] is True and second["detected"] is False
    assert ep["detected"] == 1 and ep["detection_rate"] == {"value": 0.5, "numerator": 1, "denominator": 2, "status": "ok"}
    # Alarm üretim zamanı kaydedilmiyor: wall-clock gecikmesi hiçbir düzeyde uydurulmaz.
    assert first["wall_clock_detection_delay_ms"] is None and second["wall_clock_detection_delay_ms"] is None
    assert ep["wall_clock_detection_delay_ms"]["value"] is None
    assert ep["wall_clock_detection_delay_ms"]["status"] == "not_available"
    assert ep["by_family"]["fixed_delay"]["wall_clock_detection_delay_ms"]["status"] == "not_available"
    assert "delay_ms" not in first and "delay_ms" not in ep
    # Operasyonel hatalar gecikme metriklerinden ayrı: recall paydası yalnızca skorlanan gecikme satırları.
    rl = s["request_level"]
    assert (rl["tp"], rl["fp"], rl["tn"], rl["fn"]) == (2, 0, 1, 2)
    assert rl["recall"]["denominator"] == 4 and rl["false_positive_rate"]["denominator"] == 1
    ops = s["operational_failures"]
    assert ops["rows"] == 3 and ops["latency_planned_rows_failed"] == 1
    assert ops["by_planned_fault"] == {"fixed_delay": 1, "http_error": 1, "none": 1}
    assert ops["by_observed_outcome"] == {"timeout": 3}
    assert s["excluded"] == {"excluded_unsuccessful": {"fixed_delay": 1, "http_error": 1, "none": 1}}
    assert set(preds) == {r.key for r in rows if r.features["success"]}  # başarısızlar dedektöre verilmez


def test_metrics_never_divide_by_zero():
    base = robust_z.calibrate(NORMAL_TRAIN)
    only_normal = table_rows([row("test", "a.s1", i, 1.0) for i in range(1, 4)])
    preds = {r.key: robust_z.score(base, 1.0) for r in only_normal}
    s = evaluate_split("test", only_normal, preds)
    rl = s["request_level"]
    assert rl["precision"] == {"value": None, "numerator": 0, "denominator": 0, "status": "no_alarms"}
    assert rl["recall"] == {"value": None, "numerator": 0, "denominator": 0, "status": "no_positive_rows"}
    assert s["episodes"]["detection_rate"]["status"] == "no_evaluable_episodes"
    assert s["episodes"]["request_detection_delay"] == {"n": 0, "min": None, "median": None, "max": None}
    assert s["by_family"]["random_delay"]["recall"]["status"] == "not_represented"
    empty = evaluate_split("validation", only_normal, preds)  # bölümde hiç satır yok
    assert empty["rows"] == 0 and empty["request_level"]["false_positive_rate"]["status"] == "no_normal_rows"


def test_degenerate_baseline_is_reported_and_metrics_are_null(tmp_path):
    rows = [row("train", "n.s1", i, 1.5) for i in range(1, 6)] + [row("test", "t.s1", 1, 40.0, "fixed_delay"),
                                                                    row("test", "t.s1", 2, 1.5)]
    ev = build_evaluation(write_table(tmp_path / "ft", rows))
    assert ev["calibration"]["baseline"]["status"] == "degenerate_baseline"
    assert "degenerate_baseline" in ev["calibration"]["warning"]
    assert ev["calibration"]["alarm_threshold_duration_ms"] is None
    test = ev["splits"]["test"]
    assert test["scored_rows"] == 0 and test["unscored_in_scope"] == {"degenerate_baseline:mad_zero": 2}
    assert test["request_level"]["recall"]["value"] is None and test["episodes"]["evaluable"] == 0
    assert {p["status"] for p in ev["predictions"]} == {"degenerate_baseline"}
    assert build_evaluation(write_table(tmp_path / "again" / "ft", rows)) == ev  # deterministik


# --- 11: tablo doğrulaması, çıktı ve CLI -----------------------------------------------------------------------
def test_feature_table_integrity_is_checked(tmp_path):
    good = write_table(tmp_path / "ok", standard_rows())
    document, rows = load_feature_table(good)
    assert len(rows) == len(standard_rows()) and document["table"]["policy"]["name"] == "observed-v1"
    with pytest.raises(DetectionError, match="manifest_tampered"):
        load_feature_table(write_table(tmp_path / "m", standard_rows(), tamper_manifest=True))
    tampered = write_table(tmp_path / "c", standard_rows())
    text = (tampered / FEATURES_FILE).read_text(encoding="utf-8").replace(",30.0,", ",3.0,")
    (tampered / FEATURES_FILE).write_text(text, encoding="utf-8", newline="")
    with pytest.raises(DetectionError, match="file_hash_mismatch"):
        load_feature_table(tampered)
    with pytest.raises(DetectionError, match="manifest_unreadable"):
        load_feature_table(tmp_path / "missing")


def test_evaluation_document_is_deterministic_traceable_and_not_overwritten(tmp_path):
    ft = write_table(tmp_path / "ft", standard_rows())
    before = {p.name: p.read_bytes() for p in ft.iterdir()}
    a = write_evaluation(ft, tmp_path / "a.json", now=lambda: "T1")
    b = write_evaluation(ft, tmp_path / "b.json", now=lambda: "T2")
    assert a["content_sha256"] == b["content_sha256"] and a["evaluation"] == b["evaluation"]
    assert {p.name: p.read_bytes() for p in ft.iterdir()} == before  # özellik tablosu salt okunur
    src = a["evaluation"]["source"]
    assert src["files"][FEATURES_FILE] == hashlib.sha256(before[FEATURES_FILE]).hexdigest()
    assert src["feature_manifest"]["content_sha256"] == json.loads(before[MANIFEST_FILE])["content_sha256"]
    assert a["evaluation"]["detector"]["threshold"] == 3.5 and a["evaluation"]["detector"]["direction"].startswith("upper")
    from hgs2_lab.analysis import AnalysisExistsError
    with pytest.raises(AnalysisExistsError):
        write_evaluation(ft, tmp_path / "a.json")
    labels_only = {"planned_fault", "expected_outcome", "hold_ms_actual", "planned_delay_ms", "label_status"}
    assert all(labels_only.isdisjoint(p) for p in a["evaluation"]["predictions"])


def test_cli_detect_writes_refuses_overwrite_and_reports_errors(tmp_path, capsys):
    ft = write_table(tmp_path / "ft", standard_rows())
    out = tmp_path / "eval.json"
    assert main(["detect", "robust-z", "--features-dir", str(ft), "--output", str(out)]) == EXIT_OK
    printed = capsys.readouterr().out
    assert "kalibrasyon (train normal): n=12" in printed and "test" in printed and out.exists()
    content = out.read_bytes()
    assert main(["detect", "robust-z", "--features-dir", str(ft), "--output", str(out)]) == EXIT_STORAGE_ERROR
    assert out.read_bytes() == content
    bad = write_table(tmp_path / "bad", standard_rows(), tamper_manifest=True)
    assert main(["detect", "robust-z", "--features-dir", str(bad), "--output", str(tmp_path / "x.json")]) == EXIT_ERROR
    assert not (tmp_path / "x.json").exists()
    degenerate = write_table(tmp_path / "deg", [row("train", "n.s1", i, 1.5) for i in range(1, 4)])
    assert main(["detect", "robust-z", "--features-dir", str(degenerate), "--output", str(tmp_path / "d.json")]) == EXIT_OK
    assert "degenerate_baseline" in capsys.readouterr().err


def test_detection_modules_do_not_import_network_code():
    code = (
        "import sys; import hgs2_lab.detection, hgs2_lab.robust_z; "
        "bad = sorted(m for m in ('requests', 'urllib3', 'socket', 'http.client', 'socketserver', "
        "'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.synthetic_server', 'hgs2_lab.telemetry') "
        "if m in sys.modules); print(bad)"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"
