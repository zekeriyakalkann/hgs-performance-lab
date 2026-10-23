"""Özellik tablosu entegrasyon testleri: gerçek yerel sentetik sunucuyla üretilmiş kampanya + veri seti.

`pytest -m integration` ile seçilir; 127.0.0.1 dışına her bağlantı girişimi reddedilir. Kampanya modül başına bir
kez çalıştırılır; dosyaları değiştiren testler kopya kullanır.
"""

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
from local_http_server import install_network_guard

from hgs2_lab import execution
from hgs2_lab.campaign_runner import run_campaign
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.dataset import SPLITS, build_dataset_document
from hgs2_lab.features import (
    FEATURES_FILE,
    LABELS_FILE,
    MANIFEST_FILE,
    OBSERVED_V1,
    FeatureTableError,
    build_feature_table,
    write_feature_table,
)
from hgs2_lab.reader import load_run
from hgs2_lab.synthetic import canonical_json

pytestmark = pytest.mark.integration

NO_CODE = {"git_commit": None, "git_dirty": None}
MIX = [
    {"name": "ok", "warmup_repetitions": 1, "repetitions": 3, "fault": {"type": "none"}},
    {"name": "fixed", "repetitions": 2, "fault": {"type": "fixed_delay", "delay_ms": 15}},
    {"name": "rnd", "repetitions": 2, "fault": {"type": "random_delay", "min_delay_ms": 5, "max_delay_ms": 30}},
    {"name": "err", "repetitions": 2, "fault": {"type": "http_error", "status": 503, "onset_after": 1}},
    {"name": "drop", "repetitions": 1, "fault": {"type": "connection_drop"}},
]
CAMPAIGN = {
    "campaign_version": 1, "campaign_id": "ft", "dataset_kind": "synthetic", "seeds": [1, 2], "timeout_seconds": 0.3,
    "limits": {"max_consecutive_transport_errors": 3},
    "plans": [
        {"plan_id": "p-a", "scenarios": MIX},
        {"plan_id": "p-b", "scenarios": [dict(s, fault={"type": "fixed_delay", "delay_ms": 25})
                                         if s["name"] == "fixed" else s for s in MIX]},
        {"plan_id": "p-c", "scenarios": MIX[:4]},
        {"plan_id": "p-d", "scenarios": [MIX[0], MIX[3]]},
        {"plan_id": "p-e", "scenarios": [MIX[0], MIX[1], MIX[4]]},
        {"plan_id": "p-fragile", "scenarios": [{"name": "drop", "repetitions": 4, "fault": {"type": "connection_drop"}}]},
    ],
}
LABEL_ONLY_TOKENS = ("fixed_delay", "random_delay", "http_error", "connection_drop", "confirmed")


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked:
        sock.close()
    assert attempts == []


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    base = tmp_path_factory.mktemp("features")
    (base / "c.json").write_text(json.dumps(CAMPAIGN), encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        attempts, blocked = install_network_guard(mp)
        mp.setattr(execution, "code_info", lambda: NO_CODE)
        run_campaign(base / "c.json", output_dir=base / "camp", code=NO_CODE)
        for sock in blocked:
            sock.close()
    assert attempts == []
    dataset = build_dataset_document(base / "camp", split_seed=4)
    (base / "ds.json").write_text(json.dumps(dataset), encoding="utf-8")
    return base / "camp", base / "ds.json"


def read_csv(path):
    return list(csv.DictReader(io.StringIO(Path(path).read_text(encoding="utf-8"), newline="")))


def copy_source(source, tmp_path):
    camp, ds = source
    shutil.copytree(camp, tmp_path / "camp")
    shutil.copy(ds, tmp_path / "ds.json")
    return tmp_path / "camp", tmp_path / "ds.json"


@pytest.fixture(scope="module")
def table(source, tmp_path_factory):
    out = tmp_path_factory.mktemp("table") / "out"
    document = write_feature_table(*source, out, now=lambda: "2026-01-01T00:00:00+00:00")
    return out, document


def test_same_inputs_give_byte_identical_csvs_and_content(source, table, tmp_path):
    out, document = table
    again = write_feature_table(*source, tmp_path / "again", now=lambda: "2027-01-01T00:00:00+00:00")
    for name in (FEATURES_FILE, LABELS_FILE):
        assert (out / name).read_bytes() == (tmp_path / "again" / name).read_bytes()
    assert again["content_sha256"] == document["content_sha256"] and again["generated_at"] != document["generated_at"]
    assert document["content_sha256"] == hashlib.sha256(canonical_json(document["table"])).hexdigest()


def test_manifest_hashes_match_written_files(table):
    out, document = table
    for name, info in document["table"]["files"].items():
        data = (out / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info["sha256"] and len(data) == info["size_bytes"]
        assert data.count(b"\n") == info["rows"] + 1 and b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")


def test_column_and_row_order_are_fixed(table):
    out, document = table
    header = (out / FEATURES_FILE).read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header == [c.name for c in OBSERVED_V1.features]
    rows = read_csv(out / FEATURES_FILE)
    order = {e["run_id"]: i for i, e in enumerate(document["table"]["experiments"])}
    keys = [(SPLITS.index(r["split"]), order[r["run_id"]], int(r["seq"])) for r in rows]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert [e["split"] for e in document["table"]["experiments"]] == sorted(
        (e["split"] for e in document["table"]["experiments"]), key=SPLITS.index)


def test_every_row_matches_its_run_and_split_and_source_record(source, table):
    camp, ds = source
    out, document = table
    dataset = json.loads(ds.read_text(encoding="utf-8"))["dataset"]
    split_of = {e["run_id"]: name for name, s in dataset["splits"].items() for e in s["experiments"]}
    rows = read_csv(out / FEATURES_FILE)
    seen_splits = {}
    for row in rows:
        assert row["split"] == split_of[row["run_id"]]
        seen_splits.setdefault(row["run_id"], set()).add(row["split"])
    assert all(len(s) == 1 for s in seen_splits.values())
    for run_id in {r["run_id"] for r in rows}:  # her satır kaynak sonuç kaydıyla birebir
        results = {r.seq: r for r in load_run(camp / "runs", run_id).results if not r.warmup}
        mine = [r for r in rows if r["run_id"] == run_id]
        assert [int(r["seq"]) for r in mine] == sorted(results)
        for row in mine:
            src = results[int(row["seq"])]
            assert row["duration_ms"] == ("" if src.duration_ms is None else repr(src.duration_ms))
            assert row["status_code"] == ("" if src.status_code is None else str(src.status_code))
            assert row["error_type"] == (src.error_type or "")
            assert row["success"] == ("true" if src.http_ok is True else "false")


def test_counts_per_split_match_manifest_and_dataset(source, table):
    _, ds = source
    out, document = table
    dataset = json.loads(ds.read_text(encoding="utf-8"))["dataset"]
    rows = read_csv(out / FEATURES_FILE)
    counts = document["table"]["counts"]
    for split in SPLITS:
        assert counts[split]["rows"] == sum(r["split"] == split for r in rows)
        assert counts[split]["rows"] == dataset["splits"][split]["counts"]["measured_requests"]
        assert counts[split]["experiments"] == dataset["splits"][split]["counts"]["experiments"]
    assert counts["total"]["rows"] == len(rows) and counts["total"]["warmup_excluded"] == counts["total"]["experiments"]


def test_labels_are_kept_out_of_feature_file(table):
    out, document = table
    text = (out / FEATURES_FILE).read_text(encoding="utf-8")
    header = text.splitlines()[0].split(",")
    assert "hold_ms_actual" not in header and "planned_fault" not in header and "scenario" not in header
    assert not any(token in text for token in LABEL_ONLY_TOKENS)  # plan/etiket değerleri hiç yazılmadı
    labels = read_csv(out / LABELS_FILE)
    features = read_csv(out / FEATURES_FILE)
    assert [(r["split"], r["run_id"], r["seq"]) for r in labels] == [(r["split"], r["run_id"], r["seq"]) for r in features]
    delays = [r for r in labels if r["planned_fault"] in ("fixed_delay", "random_delay")]
    assert delays and all(float(r["hold_ms_actual"]) >= float(r["planned_delay_ms"]) for r in delays)
    assert set(document["table"]["not_for_features"]) >= {"hold_ms_actual", "planned_fault", "scenario", "split"}


def test_invalid_experiments_follow_dataset_policy(table):
    _, document = table
    excluded = {e["experiment_id"] for e in document["table"]["excluded_experiments"]["excluded"]}
    assert excluded == {"ft.p-fragile.s1", "ft.p-fragile.s2"}
    assert all("p-fragile" not in e["run_id"] for e in document["table"]["experiments"])
    assert document["table"]["empty_experiments"] == []


def test_tampered_source_file_is_rejected_with_experiment_and_rule(source, tmp_path):
    camp, ds = copy_source(source, tmp_path)
    path = camp / "runs" / "ft.p-b.s1.csv"
    path.write_bytes(path.read_bytes().replace(b",200,", b",201,", 1))
    with pytest.raises(FeatureTableError, match=r"\[ft.p-b.s1\] file_hash_mismatch"):
        build_feature_table(camp, ds)


def test_missing_results_file_is_reported(source, tmp_path):
    camp, ds = copy_source(source, tmp_path)
    (camp / "runs" / "ft.p-c.s2.json").unlink()
    with pytest.raises(FeatureTableError, match=r"\[ft.p-c.s2\] file_missing"):
        build_feature_table(camp, ds)


def test_changed_split_decision_in_dataset_manifest_is_rejected(source, tmp_path):
    camp, ds = copy_source(source, tmp_path)
    document = json.loads(ds.read_text(encoding="utf-8"))
    splits = document["dataset"]["splits"]
    moved = splits["train"]["experiments"].pop(0)
    splits["test"]["experiments"].append(moved)
    document["content_sha256"] = hashlib.sha256(canonical_json(document["dataset"])).hexdigest()  # tutarlı sahtecilik
    ds.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(FeatureTableError, match=rf"\[{moved['experiment_id']}\] split_mismatch"):
        build_feature_table(camp, ds)


def test_catalog_changed_after_dataset_build_is_rejected(source, tmp_path):
    camp, ds = copy_source(source, tmp_path)
    catalog = json.loads((camp / "campaign.json").read_text(encoding="utf-8"))
    catalog["description"] = "sonradan değişti"
    (camp / "campaign.json").write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(FeatureTableError, match="catalog_changed"):
        build_feature_table(camp, ds)


def test_invalid_campaign_is_rejected(source, tmp_path):
    camp, ds = copy_source(source, tmp_path)
    (camp / "campaign-manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FeatureTableError, match="campaign_manifest_invalid"):
        build_feature_table(camp, ds)


def test_cli_features_and_no_overwrite(source, tmp_path, capsys):
    camp, ds = source
    out = tmp_path / "out"
    args = ["dataset", "features", "--campaign-dir", str(camp), "--dataset", str(ds), "--output-dir", str(out)]
    assert main(args) == EXIT_OK
    assert "features.csv" in capsys.readouterr().out
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert main(args) == EXIT_STORAGE_ERROR
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
    assert sorted(before) == sorted([FEATURES_FILE, LABELS_FILE, MANIFEST_FILE])
    bad = tmp_path / "bad"
    assert main(["dataset", "features", "--campaign-dir", str(tmp_path / "yok"), "--dataset", str(ds),
                 "--output-dir", str(bad)]) == EXIT_ERROR
    assert not bad.exists()  # doğrulama başarısızsa çıktı dizini oluşturulmaz
