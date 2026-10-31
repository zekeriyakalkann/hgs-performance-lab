"""Baseline hazırlık kampanyası manifesti (`configs/campaign.baseline.example.json`) birim testleri.

Tasarım iddialarını sınar: 12 temel plan, plan başına 3 seed, benzersiz kimlikler, deterministik plan, yalnızca
mevcut hata türleri, her anomali planında önce normal bölüm (bilinen değişim noktası), güvenlik sınırı tahmini ve
grupların seed tekrarlarını birlikte tutması. Ağ ve soket kullanılmaz.
"""

import socket
from collections import Counter
from pathlib import Path

import pytest

from hgs2_lab.campaign import load_campaign
from hgs2_lab.dataset import DEFAULT_RATIOS, assign_groups
from hgs2_lab.synthetic import FAULT_NONE, FAULT_TYPES, guard_forecast

MANIFEST = Path(__file__).resolve().parent.parent / "configs" / "campaign.baseline.example.json"
ANOMALY_FAULTS = FAULT_TYPES - {FAULT_NONE}


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


@pytest.fixture(scope="module")
def campaign():
    return load_campaign(MANIFEST)[0]


def measured(experiment):
    return [e for e in experiment.plan.entries if not e.warmup]


def test_design_size_seeds_and_unique_ids(campaign):
    assert len({e.plan_id for e in campaign.experiments}) == 12
    assert campaign.seeds == (101, 102, 103)
    ids = [e.experiment_id for e in campaign.experiments]
    assert len(ids) == 36 and len(set(ids)) == 36
    assert sum(len(e.plan.entries) for e in campaign.experiments) == 1488
    assert sum(len(measured(e)) for e in campaign.experiments) == 1380


def test_plan_is_deterministic(campaign):
    again, _ = load_campaign(MANIFEST)
    assert again.plan_sha256 == campaign.plan_sha256
    assert [e.manifest_data for e in again.experiments] == [e.manifest_data for e in campaign.experiments]


def test_seed_repeats_share_group_and_design(campaign):
    by_plan = {}
    for e in campaign.experiments:
        by_plan.setdefault(e.plan_id, []).append(e)
    for plan_id, items in by_plan.items():
        assert {e.group for e in items} == {plan_id} and len(items) == 3
        assert len({e.design_fingerprint for e in items}) == 1  # seed tasarımı değiştirmez
    assert len({items[0].design_fingerprint for items in by_plan.values()}) == 12  # planlar birbirinden farklı


def test_covers_every_supported_fault_and_onset(campaign):
    faults = {x.fault for e in campaign.experiments for x in measured(e)}
    assert faults == FAULT_TYPES  # yalnızca mevcut altyapının desteklediği türler, hepsi kullanılıyor
    onsets = [s.fault.onset_after for e in campaign.experiments for s in e.manifest.scenarios]
    assert any(o > 0 for o in onsets)


def test_anomaly_plans_start_normal_and_normal_plans_have_no_fault(campaign):
    for e in campaign.experiments:
        rows = measured(e)
        anomalous = [x.index for x in rows if x.fault != FAULT_NONE]
        if e.plan_id.startswith("normal-"):
            assert anomalous == []
        else:
            first = anomalous[0]
            assert sum(x.fault == FAULT_NONE for x in rows if x.index < first) >= 10  # önce normal bölüm


def test_expected_errors_do_not_trip_safety_limits(campaign):
    assert [e.experiment_id for e in campaign.experiments if guard_forecast(e.plan, e.manifest.limits)] == []


def test_group_split_cannot_cover_all_fault_families_in_test(campaign):
    """Belgelenen sınırlılık: 12 grup ve 0,6/0,2/0,2 ile test bölümü yalnızca 2 grup alır ve 5 anomali ailesinin
    tamamını hiçbir bölme seed'inde içeremez. Bu test, raporlanan bulgunun koddan yeniden üretilebilir olduğunu
    gösterir; gruplama politikası değiştirilmemiştir."""
    families = {}
    for e in campaign.experiments:
        families.setdefault(e.group, set()).update(x.fault for x in measured(e))
    weights = Counter(e.group for e in campaign.experiments)
    for seed in range(50):
        assignment = assign_groups(weights, DEFAULT_RATIOS, seed)
        test_groups = [g for g, s in assignment.items() if s == "test"]
        assert len(test_groups) == 2
        assert not ANOMALY_FAULTS <= set().union(*(families[g] for g in test_groups))
