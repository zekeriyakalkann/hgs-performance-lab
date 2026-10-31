"""Robust Z-score (F5) entegrasyon testi: gerçek yerel sentetik sunucuyla kampanya -> veri seti -> özellik tablosu ->
`detect robust-z`.

`pytest -m integration` ile seçilir; 127.0.0.1 dışına her bağlantı girişimi bağlantı kurulmadan reddedilir. Tüm
dosyalar testin geçici dizinindedir.
"""

import csv
import hashlib
import io
import json
import math
from pathlib import Path

import pytest
from local_http_server import install_network_guard

from hgs2_lab import execution, robust_z
from hgs2_lab.campaign_runner import run_campaign
from hgs2_lab.cli import EXIT_OK, main
from hgs2_lab.dataset import build_dataset_document
from hgs2_lab.features import FEATURES_FILE, LABELS_FILE, write_feature_table

pytestmark = pytest.mark.integration

NO_CODE = {"git_commit": None, "git_dirty": None}


def stream(fault):
    return [{"name": "stream", "warmup_repetitions": 2, "repetitions": 16, "fault": fault}]


CAMPAIGN = {
    "campaign_version": 1, "campaign_id": "rz", "dataset_kind": "synthetic", "seeds": [1], "timeout_seconds": 0.3,
    "plans": [
        {"plan_id": "normal-a", "scenarios": stream({"type": "none"})},
        {"plan_id": "normal-b", "scenarios": stream({"type": "none"})},
        {"plan_id": "fixed", "scenarios": stream({"type": "fixed_delay", "delay_ms": 30, "onset_after": 10})},
        {"plan_id": "random", "scenarios": stream({"type": "random_delay", "min_delay_ms": 20, "max_delay_ms": 40,
                                                   "onset_after": 10})},
        {"plan_id": "errors", "scenarios": stream({"type": "http_error", "status": 503, "onset_after": 14})},
    ],
}


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked:
        sock.close()
    assert attempts == []


def read_csv(path):
    return list(csv.DictReader(io.StringIO(Path(path).read_text(encoding="utf-8"))))


def test_campaign_to_robust_z_evaluation_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(execution, "code_info", lambda: NO_CODE)
    (tmp_path / "c.json").write_text(json.dumps(CAMPAIGN), encoding="utf-8")
    outcome = run_campaign(tmp_path / "c.json", output_dir=tmp_path / "camp", code=NO_CODE)
    assert outcome.all_valid
    (tmp_path / "ds.json").write_text(json.dumps(build_dataset_document(tmp_path / "camp", split_seed=3)),
                                      encoding="utf-8")
    write_feature_table(tmp_path / "camp", tmp_path / "ds.json", tmp_path / "ft")
    sources = {p.name: p.read_bytes() for p in (tmp_path / "ft").iterdir()}

    out = tmp_path / "eval.json"
    assert main(["detect", "robust-z", "--features-dir", str(tmp_path / "ft"), "--output", str(out)]) == EXIT_OK
    assert "kalibrasyon (train normal)" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in (tmp_path / "ft").iterdir()} == sources  # girdi salt okunur
    ev = json.loads(out.read_text(encoding="utf-8"))["evaluation"]

    feats, labs = read_csv(tmp_path / "ft" / FEATURES_FILE), read_csv(tmp_path / "ft" / LABELS_FILE)
    calibration = [float(f["duration_ms"]) for f, lab in zip(feats, labs) if f["split"] == "train"
                   and lab["planned_fault"] == "none" and lab["label_status"] == "confirmed" and f["success"] == "true"]
    assert ev["calibration"]["baseline"] == robust_z.calibrate(calibration).to_dict()  # yalnızca train normal
    assert ev["calibration"]["selected_rows"] == len(calibration) > 0
    assert ev["source"]["files"][FEATURES_FILE] == hashlib.sha256(sources[FEATURES_FILE]).hexdigest()

    # Skorlar yalnızca duration_ms'ten: aynı baseline ile bağımsız yeniden hesap; HTTP hataları skorlanmaz.
    baseline = robust_z.calibrate(calibration)
    by_key = {(f["split"], f["run_id"], int(f["seq"])): (f, lab) for f, lab in zip(feats, labs)}
    assert ev["predictions"]
    for p in ev["predictions"]:
        f, lab = by_key[(p["split"], p["run_id"], p["seq"])]
        assert f["success"] == "true" and lab["planned_fault"] in ("none", "fixed_delay", "random_delay")
        expected = robust_z.score(baseline, float(f["duration_ms"]))
        assert (p["status"], p["alarm"]) == (expected.status, expected.alarm)
        assert p["z"] == pytest.approx(expected.z) and math.isfinite(p["z"])
    errors = sum(1 for f, lab in zip(feats, labs) if lab["planned_fault"] == "http_error")
    excluded = sum(s["excluded"].get("excluded_unsuccessful", {}).get("http_error", 0) for s in ev["splits"].values())
    assert errors > 0 and excluded == errors

    # 20-40 ms enjekte gecikme, ~1 ms'lik loopback normaline göre eşiğin (≈ birkaç ms) çok üstündedir.
    threshold = ev["calibration"]["alarm_threshold_duration_ms"]
    assert threshold is not None and threshold < 20
    for split in ev["splits"].values():
        for e in split["episodes"]["records"]:
            assert e["detected"] is True and e["request_detection_delay"] == 0
            assert e["wall_clock_detection_delay_ms"] is None
    assert sum(s["episodes"]["episodes"] for s in ev["splits"].values()) == 2  # fixed + random, birer epizot
