"""Özellik tablosu birim testleri: CSV biçim kuralları, sütun rolleri (etiket ayrımı), veri seti manifesti
doğrulaması, çıktı dizini koruması ve içe aktarma yalıtımı. Ağ ve soket kullanılmaz."""

import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from hgs2_lab.analysis import AnalysisOutputError
from hgs2_lab.features import (
    FEATURE_POLICIES,
    NOT_FEATURE_ROLES,
    OBSERVED_V1,
    ROLE_OBSERVED,
    ROLE_TARGET,
    Column,
    FeatureTableError,
    format_cell,
    load_dataset_manifest,
    render_csv,
    write_feature_table,
)
from hgs2_lab.models import RawResult
from hgs2_lab.synthetic import canonical_json

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def no_socket_connect(monkeypatch):
    def refuse(self, address):
        raise AssertionError(f"Birim testinde bağlantı girişimi: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


# --- biçim kuralları ---
@pytest.mark.parametrize("value, kind, text", [
    (None, "float", ""), (None, "bool", ""), (True, "bool", "true"), (False, "bool", "false"),
    (200, "int", "200"), (12.0, "float", "12.0"), (0.1, "float", "0.1"), (1.3688, "float", "1.3688"),
    (5, "float", "5.0"), ("timeout", "string", "timeout"),
])
def test_format_cell_rules(value, kind, text):
    assert format_cell(value, kind) == text


@pytest.mark.parametrize("value, kind", [(True, "int"), ("1", "int"), (1, "bool"), ("x", "float"), (True, "float")])
def test_format_cell_rejects_wrong_types(value, kind):
    with pytest.raises(FeatureTableError):
        format_cell(value, kind)


def test_render_csv_fixed_columns_lf_and_minimal_quoting():
    columns = (Column("a", ROLE_OBSERVED, "string", ""), Column("b", ROLE_OBSERVED, "float", ""))
    text = render_csv(columns, [{"b": 1.5, "a": "x,y"}, {"a": "z", "b": None}])
    assert text == 'a,b\n"x,y",1.5\nz,\n'  # sütun sırası satır sözlüğünden değil, tanımdan gelir
    assert "\r" not in text


# --- sütun rolleri ve etiket ayrımı ---
def test_default_policy_keeps_labels_and_design_out_of_features():
    features = {c.name: c for c in OBSERVED_V1.features}
    labels = {c.name: c for c in OBSERVED_V1.labels}
    assert "hold_ms_actual" not in features and labels["hold_ms_actual"].role == ROLE_TARGET
    assert labels["planned_fault"].role == ROLE_TARGET
    for name in ("scenario", "planned_fault", "planned_delay_ms", "planned_status", "expected_outcome", "label_status"):
        assert name not in features
    assert all(c.role in NOT_FEATURE_ROLES for c in OBSERVED_V1.labels)  # labels.csv'de özellik sütunu yok
    observed = [c.name for c in OBSERVED_V1.features if c.role == ROLE_OBSERVED]
    assert set(observed) <= set(RawResult.field_names()) | {"success"}  # yalnızca istemci gözlemleri
    assert [c.name for c in OBSERVED_V1.features][:3] == [c.name for c in OBSERVED_V1.labels][:3] == \
        ["split", "run_id", "seq"]  # ortak birleştirme anahtarı
    assert set(FEATURE_POLICIES) == {"observed-v1"}


def test_required_fields_are_present_in_features():
    names = [c.name for c in OBSERVED_V1.features]
    for required in ("run_id", "campaign_id", "plan_id", "group_id", "seed", "seq", "status_code", "success",
                     "duration_ms", "error_type", "split"):
        assert required in names
    assert len(names) == len(set(names))


# --- veri seti manifesti doğrulaması ---
def dataset_doc(content=None):
    content = content or {"splits": {}, "parameters": {}, "source": {}}
    return {"format": "hgs2-lab-synthetic-dataset", "dataset_schema_version": 1, "generated_at": "t",
            "content_sha256": hashlib.sha256(canonical_json(content)).hexdigest(), "dataset": content}


def test_dataset_manifest_hash_is_checked(tmp_path):
    good = tmp_path / "ds.json"
    good.write_text(json.dumps(dataset_doc()), encoding="utf-8")
    assert load_dataset_manifest(good)["dataset"] == {"splits": {}, "parameters": {}, "source": {}}
    tampered = dataset_doc()
    tampered["dataset"]["splits"] = {"train": {}}
    (tmp_path / "t.json").write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(FeatureTableError, match="dataset_manifest_tampered"):
        load_dataset_manifest(tmp_path / "t.json")


@pytest.mark.parametrize("payload, rule", [
    ("{bozuk", "dataset_manifest_unreadable"),
    (json.dumps({"format": "baska"}), "dataset_manifest_format"),
    (json.dumps({**dataset_doc(), "dataset_schema_version": 2}), "dataset_manifest_format"),
])
def test_dataset_manifest_format_errors(tmp_path, payload, rule):
    (tmp_path / "ds.json").write_text(payload, encoding="utf-8")
    with pytest.raises(FeatureTableError, match=rule):
        load_dataset_manifest(tmp_path / "ds.json")


def test_missing_dataset_manifest_is_reported(tmp_path):
    with pytest.raises(FeatureTableError, match="dataset_manifest_unreadable"):
        load_dataset_manifest(tmp_path / "yok.json")


def test_non_empty_output_dir_is_refused_before_anything_is_written(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "features.csv").write_text("eski", encoding="utf-8")
    with pytest.raises(AnalysisOutputError, match="boş değil"):
        write_feature_table(tmp_path / "camp", tmp_path / "ds.json", out)
    assert [p.name for p in out.iterdir()] == ["features.csv"]
    assert (out / "features.csv").read_text(encoding="utf-8") == "eski"


def test_unknown_policy_is_rejected(tmp_path):
    from hgs2_lab.features import build_feature_table

    with pytest.raises(FeatureTableError, match="bilinmeyen özellik politikası"):
        build_feature_table(tmp_path, tmp_path / "ds.json", policy="with-labels")


def test_features_module_does_not_import_network_code():
    code = (
        "import sys; import hgs2_lab.features; "
        "bad = sorted(m for m in ('requests', 'urllib3', 'http.server', 'http.client', 'socketserver', "
        "'hgs2_lab.http_transport', 'hgs2_lab.execution', 'hgs2_lab.synthetic_server', "
        "'hgs2_lab.campaign_runner') if m in sys.modules); print(bad)"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"
