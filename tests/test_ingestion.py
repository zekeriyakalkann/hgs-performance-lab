"""N9: veri alım sözleşmesi (ingestion.py) — kabul/ret kuralları, etiket incelemesi, tekrar, kapsam ayrımı,
şema 1 uyumu, maskeleme ve mevcut hatta (N7 eşleştirme → N4) aktarım. Ağ yok; paketler sentetiktir.
"""

import copy
import hashlib
import json
import socket
from pathlib import Path

import pytest

from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, EXIT_STORAGE_ERROR, main
from hgs2_lab.ingestion import IngestionError, build_ingestion_document, parse_ingestion
from hgs2_lab.records import TestRecord
from hgs2_lab.result_analysis import load_expectations

FIX = Path(__file__).parent / "fixtures"
BATCH = FIX / "ingestion" / "fixture-batch.json"
REGISTRY = FIX / "expectations" / "synthetic-registry.json"
SECRETS = ("KART-SENTETIK-111", "FAKE-TOKEN-913")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def batch():
    return json.loads(BATCH.read_text(encoding="utf-8"))


def entry(record_id="r-1", source_id="s-1", **record):
    return {"source_record_id": source_id,
            "record": {"record_id": record_id, "source_type": "junit_xml", "dataset_kind": "real",
                       "test_outcome": "FAIL", **record}}


def real_batch(*entries):
    return {"ingestion_version": 1, "batch_id": "b-1", "dataset_kind": "real", "entries": list(entries)}


def test_fixture_batch_accept_reject_duplicate():
    result = parse_ingestion(batch())
    assert [r.record_id for r in result.records] == ["r-fx-1", "r-fx-2", "r-fx-3", "r-fx-5", "r-fx-6", "r-fx-8",
                                                     "r-fx-10"]
    assert [(r["index"], r["source_record_id"]) for r in result.rejected] == [(3, None), (8, "fx-karisik-tur")]
    assert "source_record_id" in result.rejected[0]["reason"] and "karışamaz" in result.rejected[1]["reason"]
    assert result.duplicates == [{"index": 6, "source_record_id": "fx-junit-kart-gecerli", "duplicate_of_index": 0}]
    s = result.summary()
    assert s["entries_received"] == 10 == s["accepted"] + s["rejected"] + s["duplicates"]
    assert (s["labels_accepted"], s["labels_withheld_unreviewed"], s["without_source_reference"]) == (1, 1, 3)


def test_reviewed_label_is_accepted_unreviewed_is_withheld():
    result = parse_ingestion(batch())
    by_id = {r.record_id: r for r in result.records}
    assert (by_id["r-fx-1"].label, by_id["r-fx-1"].label_source) == ("APPLICATION_FAILURE", "human_review")
    assert by_id["r-fx-2"].label is None and "label_unreviewed" in by_id["r-fx-2"].warnings
    prov = {e["record_id"]: e for e in result.entries}
    assert prov["r-fx-2"]["proposed_label"] == "APPLICATION_FAILURE"
    assert prov["r-fx-1"]["label_review"] == {"status": "REVIEWED", "evidence_ref": "FIKSTUR-INCELEME-1",
                                              "reviewer_role": "qa"}


@pytest.mark.parametrize(
    "review, reference",
    [
        ({"status": "REVIEWED"}, {"source_file": "a.xml"}),  # kanıt referansı yok
        ({"status": "REVIEWED", "evidence_ref": "E-1"}, None),  # kaynak referansı yok
        (None, {"source_file": "a.xml"}),  # inceleme yok
    ],
)
def test_label_without_full_evidence_is_not_verified(review, reference):
    item = entry(label="APPLICATION_FAILURE", label_source="human_review")
    if review is not None:
        item["label_review"] = review
    if reference is not None:
        item["source_reference"] = reference
    [record] = parse_ingestion(real_batch(item)).records
    assert record.label is None and "label_unreviewed" in record.warnings


def test_real_batch_rejects_synthetic_plan_labels_and_mixed_kinds():
    synthetic_label = entry(label="none", label_source="synthetic_plan")
    mixed = entry(record_id="r-2", source_id="s-2", dataset_kind="synthetic")
    result = parse_ingestion(real_batch(synthetic_label, mixed))
    assert result.records == [] and len(result.rejected) == 2
    assert "synthetic_plan" in result.rejected[0]["reason"] and "karışamaz" in result.rejected[1]["reason"]


def test_optional_fields_missing_and_unknown_outcome_are_kept_without_invention():
    result = parse_ingestion(real_batch(entry(test_outcome="UNKNOWN")))
    [record] = result.records
    assert record.test_outcome == "UNKNOWN" and record.scenario_id is None and record.expected_result is None
    assert record.status_code is None and record.business_outcome is None and record.label is None
    assert "source_reference_missing" in record.warnings


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda e: e.pop("source_record_id"), "source_record_id"),
        (lambda e: e.update(source_record_id="../x y"), "source_record_id"),
        (lambda e: e.update(extra=1), "bilinmeyen"),
        (lambda e: e["record"].update(test_outcome="OK"), "test_outcome"),
        (lambda e: e["record"].update(gizli=1), "record geçersiz"),
        (lambda e: e.update(record="x"), "record"),
        (lambda e: e.update(source_reference={"source_file": "C:\\Users\\x\\r.xml"}), "yalnızca dosya adı"),
        (lambda e: e.update(source_reference={"source_file": "r.xml", "source_sha256": "ABC"}), "source_sha256"),
        (lambda e: e.update(label_review={"status": "OK"}), "label_review"),
    ],
)
def test_invalid_entries_are_rejected_individually(mutate, fragment):
    bad = entry(record_id="r-bad", source_id="s-bad")
    mutate(bad)
    result = parse_ingestion(real_batch(entry(), bad))
    assert [r.record_id for r in result.records] == ["r-1"] and len(result.rejected) == 1
    assert fragment in result.rejected[0]["reason"]


@pytest.mark.parametrize(
    "data, fragment",
    [
        ([], "kökü"),
        ({"ingestion_version": 2, "batch_id": "b", "dataset_kind": "real", "entries": [{}]}, "ingestion_version"),
        ({"ingestion_version": 1, "batch_id": "../b", "dataset_kind": "real", "entries": [{}]}, "batch_id"),
        ({"ingestion_version": 1, "batch_id": "b", "dataset_kind": "prod", "entries": [{}]}, "dataset_kind"),
        ({"ingestion_version": 1, "batch_id": "b", "dataset_kind": "real", "entries": []}, "entries"),
        ({"ingestion_version": 1, "batch_id": "b", "dataset_kind": "real"}, "eksik"),
    ],
)
def test_invalid_envelope_accepts_nothing(data, fragment):
    with pytest.raises(IngestionError, match=fragment):
        parse_ingestion(data)


def test_duplicate_record_id_with_different_source_id_is_duplicate():
    result = parse_ingestion(real_batch(entry(), entry(source_id="s-2")))
    assert len(result.records) == 1 and result.duplicates[0]["duplicate_of_index"] == 0


def test_schema_1_record_is_accepted():
    result = parse_ingestion(batch())
    legacy = next(r for r in result.records if r.record_id == "r-fx-8")
    assert legacy.expected_result.status_codes == (200,) and legacy.expected_result.provenance is None


def test_sensitive_values_are_masked_everywhere():
    result = parse_ingestion(batch())
    hassas = next(r for r in result.records if r.record_id == "r-fx-6")
    assert "REDDEDILDI" in hassas.error_message and "***REDACTED***" in hassas.error_message
    assert result.summary()["records_with_masked_text"] == 1
    document = build_ingestion_document(result, now=lambda: "t")
    blob = json.dumps(document, ensure_ascii=False)
    for secret in SECRETS:
        assert secret not in blob
    bad = real_batch(entry(source_id="s-1"), {"source_record_id": "s-2", "record": {
        "record_id": "r-2", "source_type": "junit_xml", "dataset_kind": "real", "test_outcome": f"kartNo={SECRETS[0]}"}})
    assert SECRETS[0] not in json.dumps(parse_ingestion(bad).rejected)


def test_document_routes_records_through_existing_pipeline():
    result = parse_ingestion(batch())
    registry, source = load_expectations(REGISTRY)
    document = build_ingestion_document(result, expectations=registry, expectations_source=source, now=lambda: "t")
    content = document["classification"]
    records = {r["record_id"]: r for r in content["records"]}
    assert list(records) == [r.record_id for r in result.records]  # sıra ve küme korunur
    assert content["summary"]["expectation_matching"] == {"requested": True, "embedded_expected_result": 1,
                                                          "by_match_status": {"matched": 2, "no_scenario_id": 4}}
    lab = records["r-fx-10"]
    assert lab["expected_result"]["provenance"]["expectation_id"] == "exp-kart-pasif"
    assert (lab["analysis"]["classification"], lab["analysis"]["rule_ids"]) == ("PASS", ["H-EXPECTED-MATCH"])
    junit = records["r-fx-1"]
    assert junit["test_outcome"] == "FAIL" and junit["analysis"]["classification"] == "APPLICATION_FAILURE"
    assert "expectation_not_observable_in_junit" in junit["analysis"]["warnings"]
    assert "embedded_expected_result_kept" in records["r-fx-8"]["warnings"]
    assert content["summary"]["by_test_outcome"] == {"ERROR": 1, "FAIL": 2, "PASS": 3, "UNKNOWN": 1}
    assert content["summary"]["ingestion"]["accepted"] == len(content["records"])
    for r in content["records"]:
        TestRecord.from_dict(r)
    assert build_ingestion_document(result, now=lambda: "t") == build_ingestion_document(result, now=lambda: "t")


def test_cli_ingest_analyze(tmp_path, capsys):
    before = hashlib.sha256(BATCH.read_bytes()).hexdigest()
    out = tmp_path / "alim.json"
    args = ["ingest", "analyze", "--file", str(BATCH), "--expectations", str(REGISTRY), "--output", str(out)]
    assert main(args) == EXIT_ERROR  # yazıldı, ama girdi reddedildi
    captured = capsys.readouterr()
    assert "kabul 7, ret 2, tekrar 1" in captured.out and "Reddedilen girdi #3" in captured.err
    for secret in SECRETS:
        assert secret not in captured.out + captured.err + out.read_text(encoding="utf-8")
    assert main(args) == EXIT_STORAGE_ERROR
    assert hashlib.sha256(BATCH.read_bytes()).hexdigest() == before


def test_cli_ingest_clean_batch_and_errors(tmp_path, capsys):
    clean = tmp_path / "temiz.json"
    data = batch()
    data["entries"] = [copy.deepcopy(data["entries"][0])]
    clean.write_text(json.dumps(data), encoding="utf-8")
    assert main(["ingest", "analyze", "--file", str(clean), "--output", str(tmp_path / "o1.json")]) == EXIT_OK
    broken = tmp_path / "bozuk.json"
    broken.write_text("{", encoding="utf-8")
    assert main(["ingest", "analyze", "--file", str(broken), "--output", str(tmp_path / "o2.json")]) == EXIT_ERROR
    assert main(["ingest", "analyze", "--file", str(tmp_path / "yok.json"), "--output", str(tmp_path / "o3.json")]) \
        == EXIT_ERROR
    bad_registry = tmp_path / "reg.json"
    bad_registry.write_text("{}", encoding="utf-8")
    assert main(["ingest", "analyze", "--file", str(clean), "--expectations", str(bad_registry),
                 "--output", str(tmp_path / "o4.json")]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert str(tmp_path) not in err
    assert not any((tmp_path / f"o{i}.json").exists() for i in (2, 3, 4))
