"""Kampanya ve veri seti birim testleri: manifest doğrulaması, deterministik açılım, güvenli yollar, bölme
algoritması, hata yalıtımı ve kesinti. Ağ ve soket kullanılmaz (deney yürütücü sahtedir)."""

import json
import os
import socket
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest
from factories import make_result

from hgs2_lab.campaign import (
    CATALOG_NAME,
    STATUS_ERROR,
    STATUS_NOT_RUN,
    STATUS_REJECTED,
    CampaignError,
    load_campaign,
    parse_campaign,
    safe_relative,
)
from hgs2_lab.campaign_runner import CampaignRejected, run_campaign
from hgs2_lab.dataset import SPLITS, DatasetError, assign_groups, parse_ratios
from hgs2_lab.execution import PreflightError

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "configs" / "campaign.example.json"
NO_CODE = {"git_commit": None, "git_dirty": None}


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


def campaign_data(**overrides):
    data = {
        "campaign_version": 1, "campaign_id": "c1", "dataset_kind": "synthetic", "seeds": [1, 2],
        "timeout_seconds": 0.5,
        "plans": [
            {"plan_id": "p-a", "scenarios": [
                {"name": "ok", "repetitions": 2, "fault": {"type": "none"}},
                {"name": "rnd", "repetitions": 3, "fault": {"type": "random_delay", "min_delay_ms": 1, "max_delay_ms": 50}},
            ]},
            {"plan_id": "p-b", "group": "shared", "scenarios": [
                {"name": "err", "repetitions": 2, "fault": {"type": "http_error", "status": 503}},
            ]},
        ],
    }
    data.update(overrides)
    return data


def write(tmp_path, data, name="campaign.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- kampanya manifesti ---
def test_valid_campaign_expands_plan_by_seed_in_order():
    campaign = parse_campaign(campaign_data())
    assert [e.experiment_id for e in campaign.experiments] == ["c1.p-a.s1", "c1.p-a.s2", "c1.p-b.s1", "c1.p-b.s2"]
    assert [e.group for e in campaign.experiments] == ["p-a", "p-a", "shared", "shared"]  # group varsayılanı plan_id
    first = campaign.experiments[0]
    assert first.manifest.experiment_id == "c1.p-a.s1" and first.manifest.seed == 1
    assert first.manifest_data["dataset_kind"] == "synthetic" and first.manifest_data["timeout_seconds"] == 0.5


def test_example_campaign_is_valid():
    campaign, digest = load_campaign(EXAMPLE)
    assert len(campaign.experiments) == 10 and len(digest) == 64
    assert len({e.group for e in campaign.experiments}) == 5


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(extra=1), "bilinmeyen alan"),
    (lambda d: d.pop("seeds"), "eksik alan.*seeds"),
    (lambda d: d.update(seeds=[]), "seeds"),
    (lambda d: d.update(seeds=[1, 1]), "tekrarlanamaz"),
    (lambda d: d.update(seeds=[True]), "seed"),
    (lambda d: d.update(seeds=[10**7]), "seed"),
    (lambda d: d.update(campaign_id="c.1"), "campaign_id"),
    (lambda d: d.update(campaign_id="../x"), "campaign_id"),
    (lambda d: d.update(dataset_kind="measurement"), "dataset_kind"),
    (lambda d: d.update(campaign_version=2), "campaign_version"),
    (lambda d: d["plans"][1].update(plan_id="p-a"), "benzersiz"),
    (lambda d: d["plans"][1].update(plan_id="P_A"), "plan_id"),
    (lambda d: d["plans"][1].update(group="../g"), "group"),
    (lambda d: d["plans"][0].update(foo=1), r"plans\[1\]: bilinmeyen alan"),
    (lambda d: d.update(limits={"max_requests": 99999}), "en fazla"),
    (lambda d: d.update(seeds=list(range(50)), plans=d["plans"] * 3), "en çok"),
])
def test_invalid_campaign_rejected(change, message):
    data = campaign_data()
    change(data)
    with pytest.raises(CampaignError, match=message):
        parse_campaign(data)


def test_invalid_scenario_error_names_plan_and_seed():
    data = campaign_data()
    data["plans"][1]["scenarios"][0]["fault"] = {"type": "explode"}
    with pytest.raises(CampaignError, match=r"plans\[2\] \(p-b\), seed 1: .*fault.type bilinmiyor"):
        parse_campaign(data)


def test_same_manifest_same_plan_and_seed_changes_only_random_draws():
    a, b = parse_campaign(campaign_data()), parse_campaign(campaign_data())
    assert a.plan_sha256 == b.plan_sha256
    assert [e.manifest_data for e in a.experiments] == [e.manifest_data for e in b.experiments]
    s1, s2 = a.experiments[0], a.experiments[1]  # aynı plan, farklı seed
    assert s1.plan.sha256 != s2.plan.sha256
    assert [e.delay_ms for e in s1.plan.route("rnd")] != [e.delay_ms for e in s2.plan.route("rnd")]
    assert [e.to_dict()["planned"] for e in s1.plan.route("ok")] == [e.to_dict()["planned"] for e in s2.plan.route("ok")]
    assert s1.design_fingerprint == s2.design_fingerprint  # tasarım seed'den bağımsız
    assert s1.design_fingerprint != a.experiments[2].design_fingerprint
    c = parse_campaign(campaign_data(seeds=[1, 3]))
    assert c.plan_sha256 != a.plan_sha256


# --- güvenli yollar ---
@pytest.mark.parametrize("bad", ["../x.json", "/etc/passwd", "C:/x.json", "C:\\x.json", "a\\b.json", "", ".",
                                 "runs/../../x", "runs/./x", 5, None])
def test_safe_relative_rejects_paths_outside_root(tmp_path, bad):
    with pytest.raises(ValueError):
        safe_relative(tmp_path, bad)


def test_safe_relative_accepts_nested_paths(tmp_path):
    assert safe_relative(tmp_path, "runs/synthetic/a.json") == (tmp_path / "runs" / "synthetic" / "a.json").resolve()


# --- bölme ---
RATIOS = {"train": Fraction(3, 5), "validation": Fraction(1, 5), "test": Fraction(1, 5)}


def test_assign_groups_is_deterministic_and_never_splits_groups():
    weights = {f"g{i}": 2 for i in range(10)}
    a = assign_groups(weights, RATIOS, 7)
    assert a == assign_groups(dict(reversed(list(weights.items()))), RATIOS, 7)  # girdi sırasından bağımsız
    assert set(a) == set(weights) and set(a.values()) <= set(SPLITS)
    counts = {s: sum(weights[g] for g, v in a.items() if v == s) for s in SPLITS}
    assert counts == {"train": 12, "validation": 4, "test": 4}
    assert any(assign_groups(weights, RATIOS, seed) != a for seed in range(1, 20))  # seed kararı etkiler


def test_assign_groups_with_too_few_groups_leaves_split_empty_instead_of_moving_records():
    for seed in range(10):
        a = assign_groups({"only-a": 3, "only-b": 1}, RATIOS, seed)
        assert set(a) == {"only-a", "only-b"}  # her grup tam olarak bir bölümde
        assert len(set(a.values())) < len(SPLITS)  # en az bir bölüm boş kalır; kayıt taşınmaz


@pytest.mark.parametrize("text", ["0.6,0.2", "0.6,0.2,0.3", "0,0.5,0.5", "-0.1,0.6,0.5", "a,b,c", "1/0,0,0"])
def test_invalid_ratios(text):
    with pytest.raises(DatasetError):
        parse_ratios(text)


def test_ratios_are_exact_fractions():
    assert parse_ratios("0.7,0.15,0.15") == {"train": Fraction(7, 10), "validation": Fraction(3, 20),
                                             "test": Fraction(3, 20)}


# --- kampanya yürütücüsü: hata yalıtımı ve kesinti (sahte deney yürütücü) ---
def fake_outcome(run_id, *, valid=True, status="completed"):
    labels = {"verdict": {"valid": valid, "reasons": [] if valid else [{"code": "expectation_mismatch"}]},
              "summary": {"planned": 2, "executed": 2, "confirmed": 2 if valid else 1, "contradicted": 0 if valid else 1,
                          "not_executed": 0}}
    run = SimpleNamespace(status=status, results=[make_result(run_id=run_id, seq=1),
                                                  make_result(run_id=run_id, seq=2, status_code=500, http_ok=False)])
    return SimpleNamespace(labels=labels, run=run)


def scripted(behaviour):
    calls = []

    def run_experiment(manifest_path, *, results_dir, run_id, **kwargs):
        calls.append(run_id)
        action = behaviour.get(run_id, "ok")
        if isinstance(action, BaseException):
            raise action
        return fake_outcome(run_id, valid=action == "ok", status="interrupted" if action == "interrupted"
                            else "completed")
    return run_experiment, calls


def test_failure_of_one_experiment_does_not_affect_others(tmp_path):
    path = write(tmp_path, campaign_data())
    out = tmp_path / "out"
    run_experiment, calls = scripted({
        "c1.p-a.s2": RuntimeError(f"disk dolu: {out.resolve()}"),
        "c1.p-b.s1": PreflightError("Hedef reddedildi"),
        "c1.p-b.s2": "invalid",
    })
    outcome = run_campaign(path, output_dir=out, run_experiment=run_experiment, code=NO_CODE)
    assert calls == ["c1.p-a.s1", "c1.p-a.s2", "c1.p-b.s1", "c1.p-b.s2"]  # hata sonrası devam edildi
    by_id = {e["experiment_id"]: e for e in outcome.catalog["experiments"]}
    assert by_id["c1.p-a.s1"]["valid"] and by_id["c1.p-a.s1"]["status"] == "completed"
    assert (by_id["c1.p-a.s2"]["status"], by_id["c1.p-a.s2"]["error"]["type"]) == (STATUS_ERROR, "RuntimeError")
    assert "<campaign_dir>" in by_id["c1.p-a.s2"]["error"]["message"]  # yerel mutlak yol yazılmaz
    assert str(out.resolve()) not in (out / CATALOG_NAME).read_text(encoding="utf-8")
    assert by_id["c1.p-b.s1"]["status"] == STATUS_REJECTED and not by_id["c1.p-b.s1"]["valid"]
    assert by_id["c1.p-b.s2"]["invalid_reasons"] == ["expectation_mismatch"]
    assert by_id["c1.p-a.s1"]["requests"] == {"planned": 5, "recorded": 2, "http_errors": 1, "transport_errors": 0}
    summary = outcome.catalog["summary"]
    assert (summary["valid"], summary["invalid"]) == (1, 3) and not outcome.all_valid
    assert outcome.catalog["status"] == "completed"
    assert sorted(p.name for p in (out / "manifests").iterdir()) == [f"{i}.json" for i in sorted(by_id)]


def test_interrupt_stops_campaign_and_records_remaining_as_not_run(tmp_path):
    path = write(tmp_path, campaign_data())
    run_experiment, calls = scripted({"c1.p-a.s2": KeyboardInterrupt()})
    outcome = run_campaign(path, output_dir=tmp_path / "out", run_experiment=run_experiment, code=NO_CODE)
    assert calls == ["c1.p-a.s1", "c1.p-a.s2"] and outcome.interrupted
    statuses = [e["status"] for e in outcome.catalog["experiments"]]
    assert statuses == ["completed", "interrupted", STATUS_NOT_RUN, STATUS_NOT_RUN]
    assert (tmp_path / "out" / CATALOG_NAME).is_file()  # katalog kesintide de yazıldı


def test_interrupt_inside_run_also_stops_campaign(tmp_path):
    path = write(tmp_path, campaign_data())
    run_experiment, calls = scripted({"c1.p-a.s1": "interrupted"})
    outcome = run_campaign(path, output_dir=tmp_path / "out", run_experiment=run_experiment, code=NO_CODE)
    assert calls == ["c1.p-a.s1"] and outcome.interrupted
    assert [e["status"] for e in outcome.catalog["experiments"]][1:] == [STATUS_NOT_RUN] * 3


def test_non_empty_output_dir_is_rejected_before_any_experiment(tmp_path):
    path = write(tmp_path, campaign_data())
    out = tmp_path / "out"
    out.mkdir()
    (out / "eski.txt").write_text("koru", encoding="utf-8")
    run_experiment, calls = scripted({})
    with pytest.raises(CampaignRejected, match="boş değil"):
        run_campaign(path, output_dir=out, run_experiment=run_experiment, code=NO_CODE)
    assert calls == [] and sorted(p.name for p in out.iterdir()) == ["eski.txt"]


def test_invalid_campaign_manifest_writes_nothing(tmp_path):
    path = write(tmp_path, campaign_data(seeds=[]))
    with pytest.raises(CampaignError):
        run_campaign(path, output_dir=tmp_path / "out", run_experiment=scripted({})[0], code=NO_CODE)
    assert not (tmp_path / "out").exists()


# --- içe aktarma yalıtımı ---
def test_campaign_and_dataset_modules_do_not_import_network_code():
    code = (
        "import sys; import hgs2_lab.campaign, hgs2_lab.dataset; "
        "bad = sorted(m for m in ('requests', 'urllib3', 'http.server', 'http.client', 'socketserver', "
        "'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.synthetic_server', "
        "'hgs2_lab.synthetic_experiment', 'hgs2_lab.campaign_runner') if m in sys.modules); print(bad)"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"
