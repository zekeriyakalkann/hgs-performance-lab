"""Baseline kampanya planlarının gerçek yerel sentetik sunucuda (yalnızca 127.0.0.1) uçtan uca doğrulanması.

`pytest -m integration` ile seçilir. Manifestin her hata ailesini kapsayan alt kümesi tek seed ile çalıştırılır;
kampanya -> doğrulama -> veri seti -> özellik tablosu zinciri ve sayımların kaynaklar arası tutarlılığı sınanır.
"""

import csv
import io
import json
from pathlib import Path

import pytest
from local_http_server import install_network_guard

from hgs2_lab import execution
from hgs2_lab.campaign import verify_campaign
from hgs2_lab.campaign_runner import run_campaign
from hgs2_lab.dataset import build_dataset_document
from hgs2_lab.features import write_feature_table
from hgs2_lab.reader import load_run

pytestmark = pytest.mark.integration

MANIFEST = Path(__file__).resolve().parent.parent / "configs" / "campaign.baseline.example.json"
SUBSET = ("normal-steady", "fixed-small", "http503-mid", "drop-late", "timeout-late", "mixed-latency-error")
NO_CODE = {"git_commit": None, "git_dirty": None}


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked:
        sock.close()
    assert attempts == []


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    base = tmp_path_factory.mktemp("baseline")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["seeds"] = [101]
    data["plans"] = [p for p in data["plans"] if p["plan_id"] in SUBSET]
    (base / "c.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        attempts, blocked = install_network_guard(mp)
        mp.setattr(execution, "code_info", lambda: NO_CODE)
        outcome = run_campaign(base / "c.json", output_dir=base / "camp", code=NO_CODE)
        for sock in blocked:
            sock.close()
    assert attempts == []
    dataset = build_dataset_document(base / "camp", split_seed=1)
    (base / "ds.json").write_text(json.dumps(dataset), encoding="utf-8")
    table = write_feature_table(base / "camp", base / "ds.json", base / "features")
    return base, outcome.catalog, dataset["dataset"], table["table"]


def read_csv(path):
    return list(csv.DictReader(io.StringIO(Path(path).read_text(encoding="utf-8"), newline="")))


def test_every_designed_scenario_is_supported_and_confirmed(chain):
    base, catalog, _, _ = chain
    assert catalog["summary"]["valid"] == len(SUBSET) and catalog["summary"]["invalid"] == 0
    assert verify_campaign(base / "camp")["ok"]
    for entry in catalog["experiments"]:
        assert entry["labels_summary"]["confirmed"] == entry["requests"]["planned"]


def test_counts_agree_across_catalog_results_labels_dataset_and_csv(chain):
    base, catalog, dataset, table = chain
    planned = recorded = warmup = 0
    for entry in catalog["experiments"]:
        run = load_run(base / "camp" / "runs", entry["run_id"])
        labels = json.loads((base / "camp" / next(f["path"] for f in entry["files"] if f["role"] == "labels"))
                            .read_text(encoding="utf-8"))
        assert entry["requests"]["recorded"] == len(run.results) == len(labels["requests"])
        planned += entry["requests"]["planned"]
        recorded += len(run.results)
        warmup += sum(r.warmup for r in run.results)
    measured = recorded - warmup
    assert planned == recorded
    assert sum(s["counts"]["measured_requests"] for s in dataset["splits"].values()) == measured
    assert table["counts"]["total"]["rows"] == measured and table["counts"]["total"]["warmup_excluded"] == warmup
    assert len(read_csv(base / "features" / "features.csv")) == len(read_csv(base / "features" / "labels.csv")) == measured


def test_change_point_labels_follow_the_plan_and_stay_out_of_features(chain):
    base, _, _, _ = chain
    features = read_csv(base / "features" / "features.csv")
    labels = {(r["run_id"], r["seq"]): r for r in read_csv(base / "features" / "labels.csv")}
    for row in features:
        label = labels[(row["run_id"], row["seq"])]
        if label["planned_fault"] == "http_error":
            assert row["success"] == "false" and row["status_code"] == str(label["planned_status"])
            assert row["status_code"] in ("502", "503") and row["error_type"] == ""  # HTTP hatası taşıma hatası değil
        if label["planned_fault"] in ("connection_drop", "timeout"):
            assert row["duration_ms"] == "" and row["error_type"] in ("connection_error", "timeout")
        if label["planned_fault"] == "none":
            assert row["success"] == "true"
    header = (base / "features" / "features.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert not {"hold_ms_actual", "planned_fault", "expected_outcome", "scenario"} & set(header)


def test_groups_and_runs_never_cross_splits(chain):
    _, _, dataset, _ = chain
    where = {}
    for name, split in dataset["splits"].items():
        for item in split["experiments"]:
            assert where.setdefault(item["group"], name) == name
    checks = {c["rule"]: c["passed"] for c in dataset["integrity"]["checks"]}
    assert checks["run_in_single_split"] and checks["group_in_single_split"] and checks["labels_absent_from_features"]
