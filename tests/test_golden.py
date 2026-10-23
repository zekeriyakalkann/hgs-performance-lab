"""Altın örnek sonuç dosyalarıyla geriye dönük uyumluluk testleri (ağ yok).

tests/golden/ altındaki dosyalar ilgili commit'in GERÇEK yazıcısıyla, sahte taşıyıcı ve sahte saatle
üretildi (bkz. tests/golden/README.md). Dosyalar bayt bayt korunur (.gitattributes: -text); burada
SHA-256 özetleriyle sabitlenir. Bir altın dosyayı değiştirmek bilinçli bir şema kararı olmalıdır.
"""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hgs2_lab.config import LabConfig
from hgs2_lab.execution import execute_run
from hgs2_lab.models import RawResult
from hgs2_lab.reader import load_run
from hgs2_lab.scenarios import Scenario
from hgs2_lab.storage import SCHEMA_VERSION, ResultStore, UnsupportedSchemaError
from hgs2_lab.transport import TransportResponse

GOLDEN = Path(__file__).parent / "golden"
GOLDEN_SHA256 = {
    "v1-a2f5d9f/golden-v1-a2f5d9f.csv": "3f8cee698cc9ebf6d04645920716e7bd0bab20f63762f8051b45c9fc420d8007",
    "v1-a2f5d9f/golden-v1-a2f5d9f.json": "b1817d6b3ec6582abf4d89793e0672fe5b2cdd47fefd3e79a255422a501b43a5",
    "v2-76d15bb/golden-v2-76d15bb.csv": "5e0281bdbb331af2050fde53a0ca2180ef6d3ce2036db3b3d57ba6a41868c61f",
    "v2-76d15bb/golden-v2-76d15bb.json": "fd2629f0011e21e3babcbec5185a05e31dcdf67d16f9dd7618b8298029bbaeb3",
    "v2-a1331fd/golden-v2-a1331fd-aborted.partial.csv":
        "1851bf897ba381604018022b9b43e12b0f38bae8a47ede09aa10e23a7cafc6f7",
    "v2-a1331fd/golden-v2-a1331fd-aborted.partial.json":
        "b03537b7c0c38c2dd1392ebcbe910d0bda6342aa20d1f48d70026e08a9de01f4",
    "v2-a1331fd/golden-v2-a1331fd-completed.csv": "724fee7a45473f614ce36e29247f6fba6fe61c4958244c881352925e0b850909",
    "v2-a1331fd/golden-v2-a1331fd-completed.json":
        "dccbf2d108e4e4586481c797b17dd2974c63619c67b9fc3d9407c19638c8f779",
}
V2_RUNS = [  # (dizin, run_id, partial)
    ("v2-76d15bb", "golden-v2-76d15bb", False),
    ("v2-a1331fd", "golden-v2-a1331fd-completed", False),
    ("v2-a1331fd", "golden-v2-a1331fd-aborted", True),
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_golden_files_are_byte_exact():
    found = {p.relative_to(GOLDEN).as_posix() for p in GOLDEN.rglob("*") if p.suffix in (".csv", ".json")}
    assert found == set(GOLDEN_SHA256)
    for rel, digest in GOLDEN_SHA256.items():
        assert sha256(GOLDEN / rel) == digest, f"altın dosya değişmiş: {rel}"


def test_golden_files_contain_no_secrets_or_local_paths():
    for rel in GOLDEN_SHA256:
        text = (GOLDEN / rel).read_text(encoding="utf-8")
        assert "FAKE-GOLDEN-TOKEN" not in text  # sahte token yalnızca maskeli hali ile yer alır
        assert ":\\" not in text and "/home/" not in text and "/Users/" not in text


@pytest.mark.parametrize("directory, run_id, partial", V2_RUNS)
def test_existing_readers_still_read_v2_files_unchanged(directory, run_id, partial):
    store = ResultStore(GOLDEN / directory)
    stored = store.load_json(run_id, partial=partial)
    assert stored.metadata["schema_version"] == 2
    assert stored.results == store.load_csv(run_id, partial=partial)
    assert all(isinstance(r, RawResult) for r in stored.results)


@pytest.mark.parametrize("directory, run_id, partial", V2_RUNS)
def test_new_reader_reads_v2_files_without_modifying_them(directory, run_id, partial):
    before = {rel: sha256(GOLDEN / rel) for rel in GOLDEN_SHA256}
    run = load_run(GOLDEN / directory, run_id)
    assert (run.run_id, run.partial, run.schema_version) == (run_id, partial, 2)
    assert run.clock is None  # saat çapası bu dosyalardan sonra eklendi
    assert [f.role for f in run.files] == ["json", "csv"]
    for f in run.files:
        assert f.sha256 == sha256(GOLDEN / directory / f.name)
    assert {rel: sha256(GOLDEN / rel) for rel in GOLDEN_SHA256} == before


def test_v2_76d15bb_has_no_execution_metadata_and_is_accepted():
    run = load_run(GOLDEN / "v2-76d15bb", "golden-v2-76d15bb")
    assert "execution" not in run.metadata and run.execution is None
    assert len(run.results) == 8


def test_v2_a1331fd_execution_metadata_is_validated():
    completed = load_run(GOLDEN / "v2-a1331fd", "golden-v2-a1331fd-completed")
    assert completed.execution["status"] == "completed" and completed.execution["completed_requests"] == 8
    aborted = load_run(GOLDEN / "v2-a1331fd", "golden-v2-a1331fd-aborted")
    assert aborted.partial and aborted.execution["stop_reason"] == "consecutive_transport_errors"


def test_v1_files_are_rejected_with_clear_error():
    store = ResultStore(GOLDEN / "v1-a2f5d9f")
    with pytest.raises(UnsupportedSchemaError, match="schema_version 1.*yalnızca şema 2"):
        store.load_json("golden-v1-a2f5d9f")
    with pytest.raises(UnsupportedSchemaError, match="şema 1'e ait"):
        store.load_csv("golden-v1-a2f5d9f")
    with pytest.raises(UnsupportedSchemaError):
        load_run(GOLDEN / "v1-a2f5d9f", "golden-v1-a2f5d9f")


def test_crlf_line_endings_in_csv_are_read_identically(tmp_path):
    for name in ("golden-v2-a1331fd-completed.json", "golden-v2-a1331fd-completed.csv"):
        shutil.copy(GOLDEN / "v2-a1331fd" / name, tmp_path / name)
    csv_path = tmp_path / "golden-v2-a1331fd-completed.csv"
    csv_path.write_bytes(csv_path.read_bytes().replace(b"\n", b"\r\n"))
    assert load_run(tmp_path, "golden-v2-a1331fd-completed").results == \
        load_run(GOLDEN / "v2-a1331fd", "golden-v2-a1331fd-completed").results


# --- yeni yazıcı v2 sözleşmesini korur ---
class _Clock:
    def __init__(self):
        self.now_ns = 1_000

    def __call__(self):
        return self.now_ns


class _Transport:
    def __init__(self, clock):
        self._clock = clock

    def send(self, scenario, url, timeout_seconds):
        self._clock.now_ns += 2_000_000
        return TransportResponse(200, 3)

    def close(self):
        pass


def test_new_writer_keeps_v2_contract_and_only_adds_metadata_keys(tmp_path):
    clock = _Clock()
    config = LabConfig(base_url="http://127.0.0.1:8080", output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json")
    (tmp_path / "scenarios.json").write_text('{"scenarios": []}', encoding="utf-8")
    execute_run(config, [Scenario(name="a", method="GET", path="/a", repetitions=2)], config_path=None,
                run_id="new-run", resolver=lambda h, p: ["127.0.0.1"], transport_factory=lambda: _Transport(clock),
                clock=clock, now=lambda: "2026-01-01T00:00:00+00:00", sleep=lambda s: None,
                code={"git_commit": None, "git_dirty": None}, wall_clock=lambda: 1_767_225_600_000_000_000)

    golden_dir = GOLDEN / "v2-a1331fd"
    new_csv = (tmp_path / "results" / "new-run.csv").read_text(encoding="utf-8")
    golden_csv = (golden_dir / "golden-v2-a1331fd-completed.csv").read_text(encoding="utf-8")
    assert new_csv.splitlines()[0] == golden_csv.splitlines()[0]  # aynı CSV başlığı = aynı sürüm imzası

    new = json.loads((tmp_path / "results" / "new-run.json").read_text(encoding="utf-8"))
    golden = json.loads((golden_dir / "golden-v2-a1331fd-completed.json").read_text(encoding="utf-8"))
    assert new["schema_version"] == golden["schema_version"] == SCHEMA_VERSION == 2
    assert set(new) - set(golden) == {"clock", "dataset_kind"} and set(golden) <= set(new)
    assert new["dataset_kind"] == "measurement"
    assert set(new["results"][0]) == set(golden["results"][0])
    assert new["clock"]["wall_time_utc"] == "2026-01-01T00:00:00+00:00"
