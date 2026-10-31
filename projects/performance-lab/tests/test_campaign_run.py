"""Kampanya ve veri seti entegrasyon testleri: gerçek yerel sentetik sunucu (yalnızca 127.0.0.1) + gerçek taşıyıcı.

`pytest -m integration` ile seçilir. 127.0.0.1 dışına her bağlantı girişimi bağlantı kurulmadan reddedilir.
Kampanya modül başına bir kez çalıştırılır; dosyaları değiştiren testler kampanya dizininin kopyasını kullanır.
"""

import functools
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from local_http_server import install_network_guard

from hgs2_lab import execution, synthetic_experiment
from hgs2_lab.campaign import CATALOG_NAME, verify_campaign
from hgs2_lab.campaign_runner import run_campaign
from hgs2_lab.cli import EXIT_OK, EXIT_REJECTED, EXIT_STORAGE_ERROR, main
from hgs2_lab.dataset import DatasetError, build_dataset, build_dataset_document, parse_ratios
from hgs2_lab.reader import load_run
from hgs2_lab.synthetic_server import SyntheticServer

pytestmark = pytest.mark.integration

NO_CODE = {"git_commit": None, "git_dirty": None}
MIX = [
    {"name": "ok", "warmup_repetitions": 1, "repetitions": 3, "fault": {"type": "none"}},
    {"name": "fixed", "repetitions": 2, "fault": {"type": "fixed_delay", "delay_ms": 20}},
    {"name": "rnd", "repetitions": 2, "fault": {"type": "random_delay", "min_delay_ms": 5, "max_delay_ms": 40}},
    {"name": "err", "repetitions": 3, "fault": {"type": "http_error", "status": 503, "onset_after": 1}},
    {"name": "drop", "repetitions": 1, "fault": {"type": "connection_drop"}},
    {"name": "to", "repetitions": 1, "fault": {"type": "timeout"}},
]
CAMPAIGN = {
    "campaign_version": 1, "campaign_id": "it", "dataset_kind": "synthetic", "seeds": [1, 2], "timeout_seconds": 0.3,
    "limits": {"max_consecutive_transport_errors": 3},
    "plans": [
        {"plan_id": "p-a", "scenarios": MIX},
        {"plan_id": "p-b", "scenarios": [dict(s, fault={"type": "http_error", "status": 500})
                                         if s["name"] == "err" else s for s in MIX]},
        {"plan_id": "p-c", "scenarios": [MIX[0], MIX[1], MIX[3]]},  # rastgele gecikme / taşıma hatası yok
        {"plan_id": "p-dup", "scenarios": MIX},  # p-a ile özdeş tasarım, farklı grup
        {"plan_id": "p-fragile", "scenarios": [{"name": "drop", "repetitions": 4, "fault": {"type": "connection_drop"}}]},
    ],
}


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    attempts, blocked = install_network_guard(monkeypatch)
    yield attempts
    for sock in blocked:
        sock.close()
    assert attempts == []


@pytest.fixture(scope="module")
def campaign_dir(tmp_path_factory):
    base = tmp_path_factory.mktemp("campaign")
    manifest = base / "campaign.json"
    manifest.write_text(json.dumps(CAMPAIGN), encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:  # modül fixture'ı da ağ bekçisi altında çalışır
        attempts, blocked = install_network_guard(mp)
        mp.setattr(execution, "code_info", lambda: NO_CODE)
        outcome = run_campaign(manifest, output_dir=base / "out", code=NO_CODE)
        for sock in blocked:
            sock.close()
    assert attempts == []
    assert outcome.catalog["status"] == "completed"
    return base / "out"


def copy_of(campaign_dir, tmp_path):
    target = tmp_path / "copy"
    shutil.copytree(campaign_dir, target)
    return target


def catalog_of(root):
    return json.loads((root / CATALOG_NAME).read_text(encoding="utf-8"))


def rewrite_catalog(root, mutate):
    catalog = catalog_of(root)
    mutate(catalog)
    (root / CATALOG_NAME).write_text(json.dumps(catalog), encoding="utf-8")


def refresh_record(root, catalog, experiment_id, role):
    """Dosya değiştirildikten sonra katalog kaydını günceller (özet kontrolünü geçip içerik kontrolünü sınamak için)."""
    entry = next(e for e in catalog["experiments"] if e["experiment_id"] == experiment_id)
    record = next(f for f in entry["files"] if f["role"] == role)
    data = (root / record["path"]).read_bytes()
    record.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


# --- katalog ---
def test_catalog_records_valid_and_failed_experiments_with_reasons(campaign_dir):
    catalog = catalog_of(campaign_dir)
    by_id = {e["experiment_id"]: e for e in catalog["experiments"]}
    assert list(by_id) == [f"it.{p}.s{s}" for p in ("p-a", "p-b", "p-c", "p-dup", "p-fragile") for s in (1, 2)]
    assert catalog["summary"]["valid"] == 8 and catalog["summary"]["invalid"] == 2
    for seed in (1, 2):
        fragile = by_id[f"it.p-fragile.s{seed}"]
        assert fragile["status"] == "aborted" and not fragile["valid"]
        assert fragile["invalid_reasons"] == ["run_incomplete"]
        assert fragile["requests"]["recorded"] == 3 and fragile["labels_summary"]["not_executed"] == 1
        assert {f["role"] for f in fragile["files"]} == {"manifest", "results_json", "results_csv", "labels",
                                                        "server_events"}
        assert all(".partial." in f["path"] for f in fragile["files"] if f["role"] != "manifest")
    entry = by_id["it.p-a.s1"]
    assert entry["valid"] and entry["status"] == "completed" and entry["seed"] == 1 and entry["group"] == "p-a"
    assert entry["design_fingerprint"] == by_id["it.p-dup.s1"]["design_fingerprint"]
    assert catalog["process_model"] == "same_process" and catalog["hold_method"] == "sliced_sleep"


def test_catalog_hashes_match_files_and_paths_stay_inside(campaign_dir):
    for entry in catalog_of(campaign_dir)["experiments"]:
        for record in entry["files"]:
            path = (campaign_dir / record["path"]).resolve()
            assert campaign_dir.resolve() in path.parents
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == record["sha256"] and len(data) == record["size_bytes"]


def test_campaign_results_are_ordinary_v2_runs_marked_synthetic(campaign_dir):
    run = load_run(campaign_dir / "runs", "it.p-a.s1")
    assert run.schema_version == 2 and run.dataset_kind == "synthetic"
    assert run.metadata["synthetic"]["experiment_id"] == "it.p-a.s1"
    assert main(["analyze", "--results-dir", str(campaign_dir / "runs"), "--run-id", "it.p-a.s1",
                 "--output", str(campaign_dir.parent / "a.analysis.json")]) == EXIT_OK


# --- doğrulama ---
def test_verify_passes_on_untouched_campaign(campaign_dir):
    report = verify_campaign(campaign_dir)
    assert report["ok"], report["issues"]
    assert set(report["labels"]) == {f"it.{p}.s{s}" for p in ("p-a", "p-b", "p-c", "p-dup") for s in (1, 2)}


def test_verify_detects_corrupted_and_missing_files(campaign_dir, tmp_path):
    root = copy_of(campaign_dir, tmp_path)
    csv_path = root / "runs" / "it.p-b.s2.csv"
    csv_path.write_bytes(csv_path.read_bytes().replace(b"true", b"false", 1))
    (root / "runs" / "synthetic" / "it.p-c.s1.labels.json").unlink()
    issues = {(i["experiment_id"], i["rule"]) for i in verify_campaign(root)["issues"]}
    assert ("it.p-b.s2", "file_hash_mismatch") in issues and ("it.p-c.s1", "file_missing") in issues
    with pytest.raises(DatasetError, match=r"\[it.p-b.s2\] file_hash_mismatch"):
        build_dataset(root)


def test_verify_rejects_unsafe_catalog_paths(campaign_dir, tmp_path):
    root = copy_of(campaign_dir, tmp_path)
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")

    def mutate(catalog):
        catalog["experiments"][0]["files"][1]["path"] = "../outside.json"

    rewrite_catalog(root, mutate)
    issues = verify_campaign(root)["issues"]
    assert {"experiment_id": "it.p-a.s1", "rule": "path_unsafe"}.items() <= issues[0].items()


def test_verify_detects_label_inconsistency_even_when_hash_is_updated(campaign_dir, tmp_path):
    root = copy_of(campaign_dir, tmp_path)
    labels_path = root / "runs" / "synthetic" / "it.p-a.s2.labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels["verdict"]["valid"] = False
    labels_path.write_text(json.dumps(labels), encoding="utf-8")
    rewrite_catalog(root, lambda c: refresh_record(root, c, "it.p-a.s2", "labels"))
    issues = verify_campaign(root)["issues"]
    assert [(i["experiment_id"], i["rule"]) for i in issues] == [("it.p-a.s2", "labels_inconsistent")]


def test_verify_detects_tampered_campaign_manifest(campaign_dir, tmp_path):
    root = copy_of(campaign_dir, tmp_path)
    manifest = json.loads((root / "campaign-manifest.json").read_text(encoding="utf-8"))
    manifest["seeds"] = [1, 3]
    (root / "campaign-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def mutate(catalog):
        catalog["campaign_manifest"]["sha256"] = hashlib.sha256((root / "campaign-manifest.json").read_bytes()).hexdigest()

    rewrite_catalog(root, mutate)
    assert [i["rule"] for i in verify_campaign(root)["issues"]] == ["campaign_manifest_invalid"]


# --- veri seti ---
def splits_of(dataset):
    return {name: [e["experiment_id"] for e in split["experiments"]] for name, split in dataset["splits"].items()}


def test_dataset_is_deterministic_and_keeps_runs_and_groups_together(campaign_dir):
    a = build_dataset_document(campaign_dir, split_seed=3, now=lambda: "t1")
    b = build_dataset_document(campaign_dir, split_seed=3, now=lambda: "t2")
    assert a["dataset"] == b["dataset"] and a["content_sha256"] == b["content_sha256"]
    data = a["dataset"]
    where = {}
    for name, split in data["splits"].items():
        for item in split["experiments"]:
            assert item["run_id"] not in where
            where[item["run_id"]] = name
    for plan in ("p-a", "p-b", "p-c", "p-dup"):
        assert where[f"it.{plan}.s1"] == where[f"it.{plan}.s2"]  # aynı temel planın seed tekrarları aynı bölümde
    assert all(c["passed"] for c in data["integrity"]["checks"] if c["rule"] != "design_in_single_split")
    assert data["parameters"]["split_seed"] == 3 and data["source"]["campaign_id"] == "it"
    assert sorted(data["source"]["experiment_ids"]) == sorted(e["experiment_id"]
                                                              for e in catalog_of(campaign_dir)["experiments"])


def test_invalid_experiments_are_excluded_or_fail_by_policy(campaign_dir):
    data = build_dataset(campaign_dir, split_seed=1)
    excluded = {e["experiment_id"]: e for e in data["invalid_experiments"]["excluded"]}
    assert set(excluded) == {"it.p-fragile.s1", "it.p-fragile.s2"}
    assert excluded["it.p-fragile.s1"]["status"] == "aborted" and excluded["it.p-fragile.s1"]["reasons"] == ["run_incomplete"]
    assert all("p-fragile" not in s["groups"] for s in data["splits"].values())
    with pytest.raises(DatasetError, match="invalid_policy=fail.*it.p-fragile.s1"):
        build_dataset(campaign_dir, invalid_policy="fail")


def test_missing_classes_are_reported_not_invented(campaign_dir):
    for seed in range(8):
        data = build_dataset(campaign_dir, split_seed=seed)
        all_classes = set(data["targets"]["classification"]["classes"])
        reported = {w["split"]: set(w["classes"]) for w in data["warnings"] if w["code"] == "missing_classes"}
        for name, split in data["splits"].items():
            present = set(split["counts"]["classification"])
            if split["experiments"]:
                assert reported.get(name, set()) == all_classes - present
            assert present <= all_classes and all(v > 0 for v in split["counts"]["classification"].values())


def test_identical_designs_in_different_splits_are_reported(campaign_dir):
    apart = together = None
    for seed in range(50):
        data = build_dataset(campaign_dir, split_seed=seed)
        where = {g: n for n, s in data["splits"].items() for g in s["groups"]}
        codes = {w["code"] for w in data["warnings"]}
        if where["p-a"] != where["p-dup"]:
            apart = codes
        else:
            together = codes
        if apart is not None and together is not None:
            break
    assert apart is not None and "design_in_single_split" in apart
    assert together is not None and "design_in_single_split" not in together


def test_ratio_deviation_and_empty_split_are_reported_without_moving_records(campaign_dir):
    data = build_dataset(campaign_dir, split_seed=0, ratios=parse_ratios("0.8,0.1,0.1"))
    codes = [w["code"] for w in data["warnings"]]
    assert "ratio_deviation" in codes or "empty_split" in codes
    groups = [g for s in data["splits"].values() for g in s["groups"]]
    assert sorted(groups) == ["p-a", "p-b", "p-c", "p-dup"]  # her grup tam bir kez


def test_label_keys_injected_into_feature_files_are_detected(campaign_dir, tmp_path):
    root = copy_of(campaign_dir, tmp_path)
    path = root / "runs" / "it.p-a.s1.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["planned"] = {"fault": "timeout"}  # bir etiketin özellik dosyasına sızması
    path.write_text(json.dumps(document), encoding="utf-8")
    rewrite_catalog(root, lambda c: refresh_record(root, c, "it.p-a.s1", "results_json"))
    assert verify_campaign(root)["ok"]  # dosya düzeyinde tutarlı ...
    with pytest.raises(DatasetError, match="labels_absent_from_features.*it.p-a.s1"):  # ... ama sızıntı yakalanır
        build_dataset(root)


# --- güvenlik ve temizlik ---
def test_loopback_guard_rejects_every_experiment_without_requests(tmp_path):
    servers = []

    def factory(plan):
        servers.append(SyntheticServer(plan))
        return servers[-1]

    data = dict(CAMPAIGN, plans=CAMPAIGN["plans"][:2], seeds=[1])
    (tmp_path / "c.json").write_text(json.dumps(data), encoding="utf-8")
    outcome = run_campaign(tmp_path / "c.json", output_dir=tmp_path / "out", resolver=lambda h, p: ["203.0.113.9"],
                           server_factory=factory, code=NO_CODE)
    assert [e["status"] for e in outcome.catalog["experiments"]] == ["rejected", "rejected"]
    assert all(s.snapshot()["arrivals"] == 0 and s.is_closed for s in servers) and len(servers) == 2
    assert list((tmp_path / "out" / "runs").iterdir()) == []


def test_unexpected_error_in_one_experiment_cleans_up_and_others_continue(tmp_path, monkeypatch):
    servers = []

    def factory(plan):
        servers.append(SyntheticServer(plan))
        return servers[-1]

    real = synthetic_experiment.execute_run

    def flaky(config, scenarios, **kwargs):
        if kwargs["run_id"] == "it.p-c.s1":
            raise RuntimeError("beklenmeyen")
        return real(config, scenarios, **kwargs)

    monkeypatch.setattr(synthetic_experiment, "execute_run", flaky)
    data = dict(CAMPAIGN, plans=[CAMPAIGN["plans"][2]], seeds=[1, 2])
    (tmp_path / "c.json").write_text(json.dumps(data), encoding="utf-8")
    outcome = run_campaign(tmp_path / "c.json", output_dir=tmp_path / "out", server_factory=factory, code=NO_CODE)
    statuses = {e["experiment_id"]: (e["status"], e["valid"]) for e in outcome.catalog["experiments"]}
    assert statuses == {"it.p-c.s1": ("error", False), "it.p-c.s2": ("completed", True)}
    assert all(s.is_closed and s.stop() == [] for s in servers) and len(servers) == 2
    assert verify_campaign(tmp_path / "out")["ok"]  # başarısız deney katalogda doğru kayıtlı


def test_cli_campaign_verify_and_dataset_flow(tmp_path, capsys):
    data = dict(CAMPAIGN, plans=[CAMPAIGN["plans"][2]], seeds=[5])
    (tmp_path / "c.json").write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "out"
    assert main(["campaign", "validate", "--manifest", str(tmp_path / "c.json")]) == EXIT_OK
    assert main(["campaign", "run", "--manifest", str(tmp_path / "c.json"), "--output-dir", str(out)]) == EXIT_OK
    assert "geçerli: 1" in capsys.readouterr().out
    assert main(["campaign", "run", "--manifest", str(tmp_path / "c.json"), "--output-dir", str(out)]) == EXIT_REJECTED
    assert main(["campaign", "verify", "--campaign-dir", str(out)]) == EXIT_OK
    dataset = tmp_path / "ds.json"
    assert main(["dataset", "build", "--campaign-dir", str(out), "--output", str(dataset)]) == EXIT_OK
    assert "empty_split" in capsys.readouterr().out  # tek grup: validation/test boş, raporlandı
    assert main(["dataset", "build", "--campaign-dir", str(out), "--output", str(dataset)]) == EXIT_STORAGE_ERROR
    (out / "runs" / "it.p-c.s5.csv").write_text("bozuk", encoding="utf-8")
    assert main(["campaign", "verify", "--campaign-dir", str(out)]) == 1
    assert "[it.p-c.s5] file_hash_mismatch" in capsys.readouterr().err
