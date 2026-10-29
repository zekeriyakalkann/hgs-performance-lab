"""expectations.py birim testleri: beklenti modeli, kanıt referansları, kanıt yeterliliği, registry ve eşleştirme.

Ağ yok. Fikstürler sentetiktir (`tests/fixtures/expectations/`); kişisel görünen değerler sahtedir.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, main
from hgs2_lab.expectations import (
    MATCH_CONFLICT,
    MATCH_DEPRECATED_ONLY,
    MATCH_MATCHED,
    MATCH_NO_SCENARIO,
    MATCH_NOT_FOUND,
    ExpectationsError,
    assess_evidence,
    load_registry,
    parse_registry,
    verification_blockers,
)
from hgs2_lab.records import (
    EXPECTATION_SOURCE_REGISTRY,
    ExpectationProvenance,
    ExpectedResult,
    RecordError,
    TestRecord,
)

FIXTURES = Path(__file__).parent / "fixtures" / "expectations"
REGISTRY = FIXTURES / "synthetic-registry.json"
KART = "KART-SENTETIK-111"


def evidence(**overrides):
    item = {"evidence_id": "ev-1", "source_type": "synthetic_fixture", "source_ref": "tests/x.py",
            "supports": ["http_status", "business_outcome"], "review_status": "REVIEWED"}
    item.update(overrides)
    return item


def expectation(**overrides):
    item = {"expectation_id": "exp-1", "version": 1, "scenario_id": "kart", "status": "VERIFIED",
            "scope": "synthetic", "expected_http_status": [200], "expected_business_outcome": ["REDDEDILDI"],
            "evidence_ids": ["ev-1"]}
    item.update(overrides)
    return item


def doc(expectations=None, evidences=None, **extra):
    return {"expectations_version": 2, "evidence": [evidence()] if evidences is None else evidences,
            "expectations": [expectation()] if expectations is None else expectations, **extra}


def issues_of(data):
    with pytest.raises(ExpectationsError) as info:
        parse_registry(data)
    return " | ".join(info.value.issues)


# --- model ---
def test_valid_expectation_and_round_trip():
    registry = parse_registry(doc())
    [exp] = registry.expectations
    assert (exp.expectation_id, exp.version, exp.scenario_id, exp.status, exp.scope) == (
        "exp-1", 1, "kart", "VERIFIED", "synthetic")
    assert exp.expected.status_codes == (200,) and exp.expected.business_outcomes == ("REDDEDILDI",)
    assert registry.assessments["exp-1"] == ()
    again = parse_registry(registry.to_dict())  # serileştir → yeniden yükle
    assert again.to_dict() == registry.to_dict() and again.content_sha256 == registry.content_sha256


@pytest.mark.parametrize("missing", ["expectation_id", "version", "scenario_id", "status", "scope"])
def test_missing_required_field(missing):
    item = expectation()
    del item[missing]
    assert "eksik zorunlu" in issues_of(doc([item]))


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"expectation_id": ""}, "expectation_id"),
        ({"scenario_id": "../x"}, "scenario_id"),
        ({"version": 0}, "version"),
        ({"version": True}, "version"),
        ({"status": "APPROVED"}, "status"),
        ({"scope": "prod"}, "scope"),
        ({"expected_http_status": [99]}, "100-599"),
        ({"expected_http_status": [200, 200]}, "yinelenen"),
        ({"expected_http_status": []}, "boş olmayan liste"),
        ({"expected_http_status": "200"}, "boş olmayan liste"),
        ({"expected_business_outcome": ["KABUL"]}, "tanıdığı değerler"),
        ({"expected_test_outcome": "UNKNOWN"}, "expected_test_outcome"),
        ({"expected_transport": "dns"}, "expected_transport"),
        ({"evidence_ids": ["ev-1", "ev-1"]}, "tekrarsız"),
        ({"evidence_ids": ["ev-yok"]}, "tanımsız kanıt"),
        ({"bilinmeyen": 1}, "bilinmeyen anahtar"),
        ({"description": "x" * 501}, "description"),
    ],
)
def test_invalid_expectation_fields(overrides, fragment):
    assert fragment in issues_of(doc([expectation(**overrides)]))


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_transport": "timeout"},  # taşıma hatası + durum kodu/iş sonucu
        {"expected_transport": "connection_error", "expected_http_status": None, "expected_business_outcome": None,
         "expected_test_outcome": "PASS"},  # taşıma hatası + kaynak PASS
    ],
)
def test_contradictory_fields_are_rejected(overrides):
    assert "çelişki" in issues_of(doc([expectation(**overrides, status="DRAFT", evidence_ids=[])]))


def test_unknown_business_outcome_is_null_not_success():
    registry = parse_registry(doc([expectation(expected_business_outcome=None,
                                               evidence_ids=["ev-1"])]))
    assert registry.expectations[0].expected.business_outcomes == ()
    assert "en az bir beklenen alan" in issues_of(doc([expectation(expected_http_status=None,
                                                                    expected_business_outcome=None)]))


def test_business_outcome_is_normalised():
    registry = parse_registry(doc([expectation(expected_business_outcome=[" reddedildi "])]))
    assert registry.expectations[0].expected.business_outcomes == ("REDDEDILDI",)


# --- doğrulama durumları ve kanıt yeterliliği ---
def test_draft_needs_no_evidence_but_reports_it():
    registry = parse_registry(doc([expectation(status="DRAFT", evidence_ids=[])], evidences=[]))
    assert registry.assessments["exp-1"] == ("field_not_verified:business_outcome", "field_not_verified:http_status",
                                             "no_evidence")


def test_reviewed_requires_at_least_one_reference():
    assert "REVIEWED en az bir kanıt" in issues_of(doc([expectation(status="REVIEWED", evidence_ids=[])]))
    parse_registry(doc([expectation(status="REVIEWED")], [evidence(review_status="UNREVIEWED")]))


@pytest.mark.parametrize(
    "ev, blocker",
    [
        (evidence(review_status="UNREVIEWED"), "evidence_unreviewed"),  # referans var ama incelenmedi
        (evidence(supports=["http_status"]), "field_not_verified:business_outcome"),  # bir alan desteksiz
        (evidence(source_type="unknown"), "field_not_verified"),
    ],
)
def test_verified_without_sufficient_evidence_is_rejected(ev, blocker):
    assert blocker in issues_of(doc(evidences=[ev]))


def test_verified_real_scope_rejects_code_review_and_synthetic_fixture():
    for source_type in ("source_code_review", "synthetic_fixture"):
        text = issues_of(doc([expectation(scope="real")], [evidence(source_type=source_type)]))
        assert "VERIFIED kanıtla gerekçelendirilemiyor" in text
    parse_registry(doc([expectation(scope="real")], [evidence(source_type="approved_business_rule")]))


def test_verified_with_reviewed_contradicting_evidence_is_rejected():
    evs = [evidence(), evidence(evidence_id="ev-2", source_type="manual_review", relation="contradicts",
                                supports=["business_outcome"])]
    assert "field_contradicted:business_outcome" in issues_of(doc([expectation(evidence_ids=["ev-1", "ev-2"])], evs))


def test_assessment_is_deterministic_and_blockers_subset():
    registry = load_registry(REGISTRY)
    exp = next(e for e in registry.expectations if e.expectation_id == "exp-celiskili-kanit")
    issues = assess_evidence(exp, registry.evidence)
    assert issues == registry.assessments[exp.expectation_id] == tuple(sorted(issues))
    assert {"contradicting_evidence:ev-celiski", "unknown_source:ev-bilinmeyen", "evidence_unreviewed"} <= set(issues)
    assert set(verification_blockers(issues)) <= set(issues)


# --- kanıt referansları ---
@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"source_ref": "C:\\Users\\birisi\\rapor.xml"}, "mutlak yerel yol"),
        ({"source_ref": "/home/birisi/rapor.xml"}, "mutlak yerel yol"),
        ({"source_ref": ""}, "source_ref"),
        ({"source_type": "blog"}, "source_type"),
        ({"supports": []}, "supports"),
        ({"supports": ["latency"]}, "supports"),
        ({"review_status": "OK"}, "review_status"),
        ({"relation": "maybe"}, "relation"),
        ({"location": "x" * 201}, "location"),
        ({"icerik": "dosya içeriği"}, "bilinmeyen anahtar"),
    ],
)
def test_invalid_evidence(overrides, fragment):
    assert fragment in issues_of(doc(expectations=[expectation(status="DRAFT")], evidences=[evidence(**overrides)]))


def test_duplicate_evidence_and_expectation_ids():
    assert "yinelenen kimlik" in issues_of(doc(evidences=[evidence(), evidence()]))
    assert "yinelenen kimlik" in issues_of(doc([expectation(), expectation(scenario_id="baska")]))


def test_evidence_text_is_masked_and_reference_preserved():
    registry = parse_registry(doc(evidences=[evidence(description=f"kartNo={KART} ile denendi",
                                                      location=f"ogrenciNo: OGR-1234 satırı")]))
    ref = registry.evidence["ev-1"]
    assert ref.source_ref == "tests/x.py" and ref.source_type == "synthetic_fixture"
    assert KART not in json.dumps(registry.to_dict(), ensure_ascii=False)
    assert "OGR-1234" not in ref.location


# --- registry ---
def test_fixture_registry_loads_with_source_and_summary():
    registry = load_registry(REGISTRY)
    summary = registry.summary()
    assert summary["source"]["file"] == "synthetic-registry.json"
    assert summary["source"]["sha256"] == hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    assert summary["by_status"] == {"DEPRECATED": 2, "DRAFT": 4, "REVIEWED": 1, "VERIFIED": 5}
    assert summary["conflicts"] == {"cakisan": ["exp-cakisan-a", "exp-cakisan-b"]}
    assert summary["unused_evidence"] == []
    assert [e.scenario_id for e in registry.expectations] == sorted(e.scenario_id for e in registry.expectations)


def test_registry_is_deterministic_and_order_independent():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    shuffled = copy.deepcopy(data)
    shuffled["expectations"].reverse()
    shuffled["evidence"].reverse()
    assert parse_registry(data).content_sha256 == parse_registry(shuffled).content_sha256
    assert load_registry(REGISTRY).content_sha256 == load_registry(REGISTRY).content_sha256


@pytest.mark.parametrize(
    "content, fragment",
    [
        (b"", "boş"),
        (b"   \n", "boş"),
        (b"{", "geçerli UTF-8 JSON"),
        (b"\xff\xfe", "geçerli UTF-8 JSON"),
        (b"[]", "nesne olmalı"),
        (b'{"expectations_version": 1, "expectations": [1]}', "expectations_version 2"),
        (b'{"expectations_version": 2, "expectations": []}', "boş olmayan liste"),
        (b'{"expectations_version": 2}', "eksik zorunlu"),
    ],
)
def test_bad_files_are_rejected_without_path(tmp_path, content, fragment):
    path = tmp_path / "beklenti.json"
    path.write_bytes(content)
    with pytest.raises(ExpectationsError) as info:
        load_registry(path)
    assert fragment in str(info.value) and str(tmp_path) not in str(info.value)


def test_missing_file(tmp_path):
    with pytest.raises(ExpectationsError, match="bulunamadı: yok.json") as info:
        load_registry(tmp_path / "yok.json")
    assert str(tmp_path) not in str(info.value)


def test_partially_invalid_file_is_rejected_entirely():
    data = doc([expectation(), expectation(expectation_id="exp-2", scenario_id="b", status="KESIN")])
    with pytest.raises(ExpectationsError) as info:
        parse_registry(data)
    assert len(info.value.issues) == 1 and "expectations[1].status" in info.value.issues[0]


def test_loading_never_modifies_the_file():
    before = REGISTRY.read_bytes()
    load_registry(REGISTRY)
    assert REGISTRY.read_bytes() == before


# --- eşleştirme ---
def test_matching_statuses():
    registry = load_registry(REGISTRY)
    matched = registry.match("kart-pasif-cihaz")
    assert matched.status == MATCH_MATCHED and matched.warning is None
    prov = matched.expected.provenance
    assert (prov.source, prov.expectation_id, prov.version, prov.verification_status, prov.scope, prov.evidence_ids) == (
        EXPECTATION_SOURCE_REGISTRY, "exp-kart-pasif", 1, "VERIFIED", "synthetic", ("ev-fixture-pasif",))
    assert matched.expected.expected_test_outcome == "PASS"
    assert registry.match("yok").status == MATCH_NOT_FOUND
    conflict = registry.match("cakisan")
    assert conflict.status == MATCH_CONFLICT and conflict.expected is None
    assert conflict.candidate_ids == ("exp-cakisan-a", "exp-cakisan-b") and conflict.warning == "expectation_conflict"
    assert registry.match("sadece-eski").status == MATCH_DEPRECATED_ONLY
    assert registry.match(None).status == MATCH_NO_SCENARIO and registry.match("").status == MATCH_NO_SCENARIO


def test_deprecated_version_is_skipped_for_newer_active_one():
    match = load_registry(REGISTRY).match("surumlu")
    assert match.status == MATCH_MATCHED and match.expected.provenance.expectation_id == "exp-eski-v2"
    assert match.expected.provenance.version == 2 and match.candidate_ids == ("exp-eski-v1", "exp-eski-v2")


def test_endpoint_id_is_not_used_for_matching():
    registry = load_registry(REGISTRY)  # iki beklenti aynı endpoint_id'yi paylaşıyor
    assert registry.match("POST /api/kart-okut").status == MATCH_NOT_FOUND
    assert registry.match("KART-PASIF-CIHAZ").status == MATCH_NOT_FOUND  # birebir; büyük/küçük harf duyarlı


def test_draft_and_unsourced_expectations_keep_their_status():
    registry = load_registry(REGISTRY)
    draft = registry.match("numara-taslak").expected.provenance
    assert draft.verification_status == "DRAFT" and "evidence_unreviewed" in draft.evidence_issues
    unsourced = registry.match("kaynaksiz").expected.provenance
    assert unsourced.evidence_ids == () and "no_evidence" in unsourced.evidence_issues


# --- kayıt modeli ile uyum ---
def test_expected_result_round_trip_and_legacy_shape():
    prov = ExpectationProvenance(source=EXPECTATION_SOURCE_REGISTRY, expectation_id="exp-1", version=3,
                                 verification_status="DRAFT", scope="real", evidence_ids=("ev-1",),
                                 evidence_issues=("no_evidence",))
    expected = ExpectedResult(status_codes=(200,), business_outcomes=("HATA",), expected_test_outcome="FAIL",
                              expected_transport="response", provenance=prov)
    assert ExpectedResult.from_dict(expected.to_dict()) == expected
    legacy = ExpectedResult.from_dict({"status_codes": [200], "business_outcomes": [], "description": None})
    assert legacy.provenance is None and legacy.expected_transport is None  # kayıt şeması 1 biçimi okunur
    record = TestRecord(record_id="r-1", source_type="lab_result", dataset_kind="fixture", test_outcome="PASS",
                        expected_result=expected)
    assert TestRecord.from_json(record.to_json()) == record


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "tahmin"},
        {"source": EXPECTATION_SOURCE_REGISTRY},  # sözleşme beklentisinde kimlik/sürüm/durum/kapsam zorunlu
        {"source": EXPECTATION_SOURCE_REGISTRY, "expectation_id": "e", "version": 0, "verification_status": "DRAFT",
         "scope": "real"},
        {"source": EXPECTATION_SOURCE_REGISTRY, "expectation_id": "e", "version": 1, "verification_status": "OK",
         "scope": "real"},
        {"source": "expectations_file_v1", "evidence_ids": ["../x"]},
    ],
)
def test_provenance_validation(kwargs):
    with pytest.raises(RecordError):
        ExpectationProvenance(**kwargs)


# --- CLI ---
def test_cli_validate_and_show(capsys):
    assert main(["expectations", "validate", "--file", str(REGISTRY)]) == EXIT_OK
    captured = capsys.readouterr()
    assert "DRAFT=4" in captured.out and "VERIFIED=5" in captured.out and "'cakisan'" in captured.err
    assert main(["expectations", "show", "--file", str(REGISTRY), "--scenario", "kart-pasif-cihaz"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "exp-kart-pasif v1" in out and "ev-fixture-pasif" in out and KART not in out
    assert main(["expectations", "show", "--file", str(REGISTRY), "--scenario", "yok"]) == EXIT_ERROR


def test_cli_validate_lists_all_issues(tmp_path, capsys):
    path = tmp_path / "bozuk.json"
    path.write_text(json.dumps(doc([expectation(status="X"), expectation(expectation_id="e2", scope="y")])),
                    encoding="utf-8")
    assert main(["expectations", "validate", "--file", str(path)]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert "expectations[0].status" in err and "expectations[1].scope" in err and str(tmp_path) not in err


def test_error_messages_never_echo_values(tmp_path, capsys):
    data = doc([expectation(scenario_id=f"kartNo={KART}", description=f"kartNo={KART} " * 60,
                            expected_business_outcome=[KART])],
               [evidence(source_ref=f"C:\\Users\\{KART}\\x", location=KART * 20)])
    text = issues_of(data)
    assert KART not in text
    path = tmp_path / "e.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main(["expectations", "validate", "--file", str(path)]) == EXIT_ERROR
    captured = capsys.readouterr()
    assert KART not in captured.out + captured.err


def test_expectations_module_does_not_import_network_code():
    root =Path(__file__).resolve().parents[1]
    code = ("import sys; import hgs2_lab.expectations, hgs2_lab.result_analysis; bad = sorted(m for m in "
            "('requests', 'urllib3', 'socket', 'http.client', 'hgs2_lab.http_transport', 'hgs2_lab.execution', "
            "'hgs2_lab.robust_z', 'hgs2_lab.detection', 'hgs2_lab.telemetry') if m in sys.modules); print(bad)")
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                          check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_cli_real_draft_example(capsys):
    assert main(["expectations", "show", "--file", str(FIXTURES / "hgs2-draft-example.json")]) == EXIT_OK
    out = capsys.readouterr().out
    assert "DRAFT\tkapsam=real" in out and "non_verifying_source" in out and "evidence_unreviewed" in out
