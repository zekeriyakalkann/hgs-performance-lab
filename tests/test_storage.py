import csv
import json
import os

import pytest
from factories import make_failed_result, make_result

from hgs2_lab.models import InvalidRunId, RawResult
from hgs2_lab.storage import (
    SCHEMA_VERSION,
    ResultExistsError,
    ResultStore,
    StorageError,
    UnsupportedSchemaError,
)

V1_FIELDS = [
    "run_id", "scenario", "iteration", "method", "url", "started_at", "elapsed_ms", "duration_ms",
    "status_code", "http_ok", "business_outcome", "error_type", "error", "response_bytes",
]

META = {
    "tool_version": "0.1.0",
    "started_at": "2026-01-01T00:00:00+00:00",
    "finished_at": "2026-01-01T00:01:00+00:00",
    "config": {"base_url": "http://h"},
    "scenarios": [{"name": "s"}],
}


def sample_results():
    return [
        make_result(seq=1, iteration=1, warmup=True, offset_ms=0.0),
        make_result(seq=2, iteration=1, status_code=500, http_ok=False, offset_ms=12.75, elapsed_ms=40.25,
                    duration_ms=40.25),
        make_failed_result(seq=3, iteration=2, offset_ms=53.0625,
                           error='TransportConnectionError: "x", y\nsatır2', error_type="connection_error"),
    ]


def test_save_creates_dir_and_exactly_two_files(tmp_path):
    out = tmp_path / "nested" / "out"
    csv_path, json_path = ResultStore(out).save("r1", sample_results(), META)
    assert csv_path.exists() and json_path.exists()
    assert sorted(p.name for p in out.iterdir()) == ["r1.csv", "r1.json"]  # geçici dosya kalmadı


@pytest.mark.parametrize("run_id", ["../x", "a/b", "", ".hidden", "CON"])
def test_invalid_run_id_rejected_and_nothing_written(tmp_path, run_id):
    out = tmp_path / "out"
    with pytest.raises(InvalidRunId):
        ResultStore(out).save(run_id, [make_result()], META)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_overwrite_is_blocked_and_originals_untouched(tmp_path):
    store = ResultStore(tmp_path)
    csv_path, json_path = store.save("r1", sample_results(), META)
    before = (csv_path.read_bytes(), json_path.read_bytes())
    with pytest.raises(ResultExistsError):
        store.save("r1", [make_result(elapsed_ms=999.0)], META)
    assert (csv_path.read_bytes(), json_path.read_bytes()) == before


def test_existing_single_file_blocks_save_and_creates_nothing_else(tmp_path):
    (tmp_path / "r1.csv").write_text("eski", encoding="utf-8")
    with pytest.raises(ResultExistsError):
        ResultStore(tmp_path).save("r1", [make_result()], META)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["r1.csv"]
    assert (tmp_path / "r1.csv").read_text(encoding="utf-8") == "eski"


def test_result_run_id_must_match(tmp_path):
    with pytest.raises(StorageError, match="run_id"):
        ResultStore(tmp_path).save("r2", [make_result(run_id="r1")], META)
    assert list(tmp_path.iterdir()) == []


def test_reserved_metadata_keys_rejected(tmp_path):
    for key in ("results", "schema_version", "run_id"):
        with pytest.raises(ValueError, match=key):
            ResultStore(tmp_path).save("r1", [make_result()], {key: 1})
    assert list(tmp_path.iterdir()) == []


def test_non_finite_metadata_fails_before_touching_disk(tmp_path):
    with pytest.raises(ValueError):
        ResultStore(tmp_path).save("r1", [make_result()], {"x": float("nan")})
    assert list(tmp_path.iterdir()) == []


def test_failed_second_publish_rolls_back_first(tmp_path, monkeypatch):
    real_replace = os.replace

    def flaky(src, dst):
        if str(dst).endswith(".json"):
            raise OSError("disk dolu")
        real_replace(src, dst)

    monkeypatch.setattr("hgs2_lab.storage.os.replace", flaky)
    with pytest.raises(StorageError, match="disk dolu"):
        ResultStore(tmp_path).save("r1", sample_results(), META)
    assert list(tmp_path.iterdir()) == []


def test_json_document_has_schema_metadata_and_results(tmp_path):
    _, json_path = ResultStore(tmp_path).save("r1", sample_results(), META)
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["run_id"] == "r1"
    for key, value in META.items():
        assert doc[key] == value
    assert len(doc["results"]) == 3
    assert list(doc["results"][0]) == RawResult.field_names()


def test_json_roundtrip_results_and_metadata(tmp_path):
    store = ResultStore(tmp_path)
    original = sample_results()
    store.save("r1", original, META)
    stored = store.load_json("r1")
    assert stored.results == original
    assert stored.metadata["tool_version"] == "0.1.0"
    assert stored.metadata["run_id"] == "r1"
    assert "results" not in stored.metadata


def test_csv_roundtrip_restores_types(tmp_path):
    store = ResultStore(tmp_path)
    original = sample_results()
    store.save("r1", original, META)
    loaded = store.load_csv("r1")
    assert loaded == original
    assert isinstance(loaded[0].http_ok, bool) and loaded[2].http_ok is None
    assert isinstance(loaded[0].iteration, int)
    assert isinstance(loaded[1].elapsed_ms, float)
    assert loaded[2].duration_ms is None and loaded[2].status_code is None


def test_csv_and_json_are_consistent(tmp_path):
    store = ResultStore(tmp_path)
    csv_path, json_path = store.save("r1", sample_results(), META)
    assert store.load_csv("r1") == store.load_json("r1").results
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == RawResult.field_names()
        rows = list(reader)
    json_rows = json.loads(json_path.read_text(encoding="utf-8"))["results"]
    assert [list(r) for r in json_rows] == [RawResult.field_names()] * 3
    assert len(rows) == len(json_rows)


def test_csv_cell_representation(tmp_path):
    csv_path, _ = ResultStore(tmp_path).save("r1", sample_results(), META)
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["http_ok"] == "true" and rows[1]["http_ok"] == "false"
    assert rows[2]["http_ok"] == "" and rows[2]["status_code"] == "" and rows[2]["duration_ms"] == ""
    assert rows[0]["error_type"] == "" and rows[0]["business_outcome"] == ""
    assert [r["warmup"] for r in rows] == ["true", "false", "false"]
    assert [r["seq"] for r in rows] == ["1", "2", "3"]
    assert [r["offset_ms"] for r in rows] == ["0.0", "12.75", "53.0625"]
    assert "schema_version" not in rows[0]  # CSV'de sürüm sütunu yok; yetkili kaynak JSON


def test_schema_version_is_2():
    assert SCHEMA_VERSION == 2


def test_v2_fields_roundtrip_losslessly_through_csv_and_json(tmp_path):
    store = ResultStore(tmp_path)
    original = sample_results()
    store.save("r1", original, META)
    for loaded in (store.load_csv("r1"), store.load_json("r1").results):
        assert [(r.seq, r.offset_ms, r.warmup) for r in loaded] == [(1, 0.0, True), (2, 12.75, False), (3, 53.0625, False)]
        assert all(type(r.seq) is int and type(r.offset_ms) is float and type(r.warmup) is bool for r in loaded)
        assert loaded == original


def test_v1_json_is_rejected_with_clear_message(tmp_path):
    v1_row = dict.fromkeys(V1_FIELDS)
    (tmp_path / "old1.json").write_text(
        json.dumps({"schema_version": 1, "run_id": "old1", "results": [v1_row]}), encoding="utf-8"
    )
    with pytest.raises(UnsupportedSchemaError, match=r"schema_version 1.*yalnızca şema 2"):
        ResultStore(tmp_path).load_json("old1")


def test_missing_schema_version_is_rejected(tmp_path):
    (tmp_path / "nov.json").write_text(json.dumps({"run_id": "nov", "results": []}), encoding="utf-8")
    with pytest.raises(UnsupportedSchemaError, match="schema_version None"):
        ResultStore(tmp_path).load_json("nov")


def test_v1_csv_is_rejected_with_clear_message(tmp_path):
    (tmp_path / "old1.csv").write_text(",".join(V1_FIELDS) + "\n", encoding="utf-8")
    with pytest.raises(UnsupportedSchemaError, match=r"başlığı şema 1'e ait.*yalnızca şema 2"):
        ResultStore(tmp_path).load_csv("old1")


def test_empty_results_are_saved(tmp_path):
    store = ResultStore(tmp_path)
    store.save("r1", [], META)
    assert store.load_csv("r1") == []
    assert store.load_json("r1").results == []


def test_load_csv_errors(tmp_path):
    store = ResultStore(tmp_path)
    with pytest.raises(StorageError):
        store.load_csv("yok")
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(StorageError, match="başlığı"):
        store.load_csv("bad")

    csv_path, _ = store.save("ok", [make_result(run_id="ok")], META)
    original_text = csv_path.read_text(encoding="utf-8")
    assert original_text.count(",1,false,GET,") == 1  # iteration sütunu (warmup ve method'dan önce)
    broken = original_text.replace(",1,false,GET,", ",x,false,GET,")
    (tmp_path / "broken.csv").write_text(broken, encoding="utf-8")
    with pytest.raises(StorageError, match="satır 2"):
        store.load_csv("broken")


def test_load_json_errors(tmp_path):
    store = ResultStore(tmp_path)
    with pytest.raises(StorageError):
        store.load_json("yok")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(StorageError, match="geçerli değil"):
        store.load_json("bad")
    (tmp_path / "old.json").write_text(json.dumps({"schema_version": 0, "run_id": "old", "results": []}), encoding="utf-8")
    with pytest.raises(StorageError, match="schema_version"):
        store.load_json("old")
    (tmp_path / "other.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "run_id": "baska", "results": []}), encoding="utf-8"
    )
    with pytest.raises(StorageError, match="run_id"):
        store.load_json("other")
    (tmp_path / "rows.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "run_id": "rows", "results": [{"run_id": "rows"}]}), encoding="utf-8"
    )
    with pytest.raises(StorageError, match="Geçersiz sonuç"):
        store.load_json("rows")
