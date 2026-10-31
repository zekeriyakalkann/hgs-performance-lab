"""Sonuç okuyucu testleri: dosya keşfi, sürüm politikası, CSV/JSON tutarlılığı, metadata doğrulaması (ağ yok)."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from factories import make_failed_result, make_result

from hgs2_lab.clock import ClockAnchor
from hgs2_lab.models import InvalidRunId
from hgs2_lab.reader import RunDataError, find_run_files, load_run
from hgs2_lab.storage import (
    READABLE_SCHEMA_VERSIONS,
    SCHEMA_VERSION,
    StorageError,
    UnsupportedSchemaError,
    _render_csv,
)

GOLDEN = Path(__file__).parent / "golden" / "v2-a1331fd"
COMPLETED = "golden-v2-a1331fd-completed"
ABORTED = "golden-v2-a1331fd-aborted"


def write_run(directory, run_id, results, metadata=None, *, partial=False, csv_results=None):
    """Tutarsız veriyi de yazabilen yardımcı (ResultStore.save tutarsızlığı reddeder)."""
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{run_id}.partial" if partial else run_id
    rows = [r.to_dict() for r in results]
    document = {"schema_version": SCHEMA_VERSION, "run_id": run_id, **(metadata or {}), "results": rows}
    (directory / f"{stem}.json").write_text(json.dumps(document), encoding="utf-8")
    csv_rows = rows if csv_results is None else [r.to_dict() for r in csv_results]
    (directory / f"{stem}.csv").write_text(_render_csv(csv_rows), encoding="utf-8", newline="")


def edit_golden_json(tmp_path, run_id, edit, partial=False):
    stem = f"{run_id}.partial" if partial else run_id
    for suffix in (".json", ".csv"):
        shutil.copy(GOLDEN / f"{stem}{suffix}", tmp_path / f"{stem}{suffix}")
    path = tmp_path / f"{stem}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    edit(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def two_results():
    return [make_result(), make_failed_result()]


# --- sürüm politikası ---
def test_version_policy_constants():
    assert SCHEMA_VERSION == 2 and READABLE_SCHEMA_VERSIONS == frozenset({2})


@pytest.mark.parametrize("version", [1, 3, "2", 2.0, True, None])
def test_unsupported_or_malformed_schema_version_rejected(tmp_path, version):
    def edit(document):
        if version is None:
            del document["schema_version"]
        else:
            document["schema_version"] = version

    edit_golden_json(tmp_path, COMPLETED, edit)
    with pytest.raises(UnsupportedSchemaError, match="schema_version"):
        load_run(tmp_path, COMPLETED)


# --- dosya keşfi ---
def test_finds_complete_and_partial_files():
    assert find_run_files(GOLDEN, COMPLETED) == (False, GOLDEN / f"{COMPLETED}.csv", GOLDEN / f"{COMPLETED}.json")
    partial, csv_path, json_path = find_run_files(GOLDEN, ABORTED)
    assert partial and json_path.name == f"{ABORTED}.partial.json"


def test_missing_run_is_reported(tmp_path):
    with pytest.raises(RunDataError, match="bulunamadı"):
        load_run(tmp_path, "yok")


def test_missing_csv_is_reported(tmp_path):
    shutil.copy(GOLDEN / f"{COMPLETED}.json", tmp_path / f"{COMPLETED}.json")
    with pytest.raises(RunDataError, match=f"eksik: {COMPLETED}.csv"):
        load_run(tmp_path, COMPLETED)


def test_both_complete_and_partial_is_ambiguous(tmp_path):
    write_run(tmp_path, "r1", [make_result()])
    write_run(tmp_path, "r1", [make_result()], partial=True)
    with pytest.raises(RunDataError, match="belirsiz"):
        load_run(tmp_path, "r1")


def test_unsafe_run_id_rejected(tmp_path):
    with pytest.raises(InvalidRunId):
        load_run(tmp_path, "../dışarı")


def test_file_hashes_names_and_sizes_come_from_read_bytes():
    run = load_run(GOLDEN, COMPLETED)
    for f in run.files:
        data = (GOLDEN / f.name).read_bytes()
        assert f.sha256 == hashlib.sha256(data).hexdigest() and f.size_bytes == len(data)
        assert "/" not in f.name and "\\" not in f.name  # yalnızca dosya adı


def test_non_utf8_file_rejected(tmp_path):
    write_run(tmp_path, "r1", [make_result()])
    (tmp_path / "r1.csv").write_bytes(b"\xff\xfe bozuk")
    with pytest.raises(RunDataError, match="UTF-8"):
        load_run(tmp_path, "r1")


def test_corrupt_json_rejected(tmp_path):
    write_run(tmp_path, "r1", [make_result()])
    (tmp_path / "r1.json").write_text("{bozuk", encoding="utf-8")
    with pytest.raises(StorageError, match="geçerli değil"):
        load_run(tmp_path, "r1")


# --- CSV/JSON tutarlılığı ve kayıt bütünlüğü ---
def test_csv_json_value_mismatch_names_fields(tmp_path):
    write_run(tmp_path, "r1", two_results(), csv_results=[make_result(duration_ms=99.0), make_failed_result()])
    with pytest.raises(RunDataError, match=r"1\. kayıtta uyuşmuyor \(alanlar: duration_ms\)"):
        load_run(tmp_path, "r1")


def test_csv_json_count_mismatch(tmp_path):
    write_run(tmp_path, "r1", two_results(), csv_results=[make_result()])
    with pytest.raises(RunDataError, match="kayıt sayıları"):
        load_run(tmp_path, "r1")


def test_seq_gap_rejected(tmp_path):
    write_run(tmp_path, "r1", [make_result(seq=1), make_failed_result(seq=3)])
    with pytest.raises(RunDataError, match="seq kesintisiz değil"):
        load_run(tmp_path, "r1")


def test_row_run_id_mismatch_rejected(tmp_path):
    write_run(tmp_path, "r1", [make_result(run_id="baska")])
    with pytest.raises(RunDataError, match="run_id"):
        load_run(tmp_path, "r1")


def test_empty_results_are_valid(tmp_path):
    write_run(tmp_path, "r1", [])
    run = load_run(tmp_path, "r1")
    assert run.results == () and run.execution is None and run.clock is None


# --- metadata doğrulaması ---
def _set(path, value):
    def edit(document):
        target = document
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return edit


@pytest.mark.parametrize("path, value, message", [
    (("execution", "status"), "bitti", "execution.status bilinmiyor"),
    (("execution", "completed_requests"), 7, "kayıt sayısıyla"),
    (("execution", "planned_requests"), -1, "planned_requests"),
    (("execution", "planned_requests"), 9, "8/9 istek"),
    (("execution", "stop_reason"), "duration_limit", "stop_reason dolu olamaz"),
    (("execution", "status"), "aborted", "kısmi \\(.partial\\) olarak adlandırılmamış"),
    (("execution",), "tamam", "execution bir nesne"),
    (("started_at",), "dün", "ISO 8601"),
    (("finished_at",), "2026-10-23T10:00:10", "saat dilimi"),
    (("monotonic_duration_ms",), -5, "monotonic_duration_ms"),
    (("tool_version",), 1, "tool_version"),
    (("target_label",), ["x"], "target_label"),
    (("code", "git_dirty"), "hayır", "git_dirty"),
    (("inputs", "hash_errors"), [], "hash_errors"),
    (("scenarios",), [{"name": "login"}], "tanımlı olmayan senaryo\\(lar\\) var: items"),
    (("clock",), {"monotonic_ns": 1}, "clock alanları"),
])
def test_invalid_metadata_rejected(tmp_path, path, value, message):
    edit_golden_json(tmp_path, COMPLETED, _set(path, value))
    with pytest.raises(RunDataError, match=f"Metadata geçersiz: .*{message}"):
        load_run(tmp_path, COMPLETED)


def test_completed_status_in_partial_file_rejected(tmp_path):
    edit_golden_json(tmp_path, ABORTED, _set(("execution", "status"), "completed"), partial=True)
    with pytest.raises(RunDataError, match="kısmi .* 'completed'"):
        load_run(tmp_path, ABORTED)


def test_utc_z_suffix_and_null_clock_accepted(tmp_path):
    def edit(document):
        document["started_at"] = "2026-10-23T10:00:01Z"
        document["clock"] = None  # hiç istek başlamadıysa yazılan değer

    edit_golden_json(tmp_path, COMPLETED, edit)
    assert load_run(tmp_path, COMPLETED).clock is None


def test_unknown_metadata_keys_are_ignored_for_forward_compatibility(tmp_path):
    edit_golden_json(tmp_path, COMPLETED, _set(("future_key",), {"anything": 1}))
    assert load_run(tmp_path, COMPLETED).metadata["future_key"] == {"anything": 1}


def test_valid_clock_is_parsed(tmp_path):
    anchor = ClockAnchor.capture(lambda: 5, lambda: 1_767_225_600_000_000_000)
    edit_golden_json(tmp_path, COMPLETED, _set(("clock",), anchor.to_dict()))
    assert load_run(tmp_path, COMPLETED).clock == anchor
