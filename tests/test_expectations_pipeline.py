"""N7: beklenti sözleşmesi ile N4 sınıflandırıcının birlikte çalışması (A–H senaryoları) ve uçtan uca çevrimdışı hat:
sentetik HTTP yanıtı → N6 ayrıştırıcı → TestRecord → beklenti registry'si → beklenen/gözlenen → N4 → JSON.

Ağ yok (sahte taşıyıcı). Değerler sentetiktir; bu testler gerçek HGS2 davranışını doğrulamaz.
"""

import hashlib
import json
import socket
from pathlib import Path

import pytest

from hgs2_lab import execution
from hgs2_lab.classify import classify_record
from hgs2_lab.cli import EXIT_ERROR, EXIT_OK, main
from hgs2_lab.config import LabConfig, RunLimits
from hgs2_lab.execution import execute_run
from hgs2_lab.records import (
    EXPECTATION_SOURCE_FILE_V1,
    EXPECTATION_SOURCE_REGISTRY,
    ExpectationProvenance,
    ExpectedResult,
    TestRecord,
)
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import TransportConnectionError, TransportResponse, TransportTimeout

FIXTURES = Path(__file__).parent / "fixtures" / "expectations"
REGISTRY = FIXTURES / "synthetic-registry.json"
KART = "KART-SENTETIK-111"
TEXT = "text/plain;charset=UTF-8"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(execution, "code_info", lambda: {"git_commit": None, "git_dirty": None})


def prov(status="VERIFIED", scope="synthetic", issues=(), evidence_ids=("ev-1",)):
    return ExpectationProvenance(source=EXPECTATION_SOURCE_REGISTRY, expectation_id="exp-1", version=1,
                                 verification_status=status, scope=scope, evidence_ids=evidence_ids,
                                 evidence_issues=issues)


def expect(*, codes=(200,), outcomes=(), status="VERIFIED", scope="synthetic", transport=None, test_outcome=None,
           **kw):
    return ExpectedResult(status_codes=codes, business_outcomes=outcomes, expected_transport=transport,
                          expected_test_outcome=test_outcome, provenance=prov(status, scope, **kw))


def record(*, expected=None, status_code=200, body=None, outcome="PASS", transport=None, dataset="fixture",
           warnings=()):
    return TestRecord(record_id="r-1", source_type="lab_result", dataset_kind=dataset, test_outcome=outcome,
                      scenario_id="kart", status_code=status_code, business_outcome=body, transport_error=transport,
                      expected_result=expected, warnings=warnings)


def ev(c, field):
    return [e.value for e in c.evidence if e.field == field]


# --- A–H ---
def test_a_verified_expected_rejection_observed_rejection_is_pass():
    c = classify_record(record(expected=expect(outcomes=("REDDEDILDI",)), body="REDDEDILDI"))
    assert (c.classification, c.rule_ids, c.confidence) == ("PASS", ("H-EXPECTED-MATCH",), "high")
    [meta] = ev(c, "expectation")
    assert meta["verification_status"] == "VERIFIED" and meta["expectation_id"] == "exp-1"
    assert any("yalnızca 'synthetic' kapsamında" in text for text in c.limitations)


def test_b_verified_expected_acceptance_observed_rejection_is_reported():
    c = classify_record(record(expected=expect(outcomes=("ONAYLANDI",)), body="REDDEDILDI"))
    assert (c.classification, c.rule_ids) == ("APPLICATION_FAILURE", ("H-BUSINESS-MISMATCH",))
    mismatch = [e for e in c.evidence if e.source == "rule" and e.field == "business_outcome"]
    assert mismatch[0].value == "REDDEDILDI" and "ONAYLANDI" in mismatch[0].note


def test_http_status_match_and_mismatch_with_verified_expectation():
    assert classify_record(record(expected=expect(codes=(404,)), status_code=404)).classification == "PASS"
    c = classify_record(record(expected=expect(codes=(200,)), status_code=500, outcome="FAIL"))
    assert (c.classification, c.rule_ids) == ("APPLICATION_FAILURE", ("H-STATUS-MISMATCH",))


def test_c_unknown_expectation_is_never_decisive():
    c = classify_record(record(body="REDDEDILDI", warnings=("expectation_not_found",)))
    assert c.classification == "INCONCLUSIVE" and c.rule_ids == ("H-NO-EXPECTATION",)
    assert "expectation_not_found" in c.warnings and c.confidence is None


@pytest.mark.parametrize("status", ["DRAFT", "REVIEWED"])
@pytest.mark.parametrize("body, would_be, base_rule", [("ONAYLANDI", "PASS", "H-EXPECTED-MATCH"),
                                                       ("REDDEDILDI", "APPLICATION_FAILURE", "H-BUSINESS-MISMATCH")])
def test_d_unverified_expectation_is_compared_but_not_decisive(status, body, would_be, base_rule):
    c = classify_record(record(expected=expect(outcomes=("ONAYLANDI",), status=status), body=body))
    assert c.classification == "INCONCLUSIVE" and c.rule_ids == ("E-UNVERIFIED-EXPECTATION", base_rule)
    assert c.confidence is None and c.requires_review and "expectation_unverified" in c.warnings
    assert ev(c, "comparison") == [{"would_be": would_be, "rule": base_rule}]
    assert status in c.reason


def test_e_expectation_without_source_is_reported():
    expected = expect(outcomes=("ONAYLANDI",), status="DRAFT", evidence_ids=(),
                      issues=("field_not_verified:business_outcome", "no_evidence"))
    c = classify_record(record(expected=expected, body="ONAYLANDI"))
    assert c.classification == "INCONCLUSIVE" and "expectation_evidence_issues" in c.warnings
    [meta] = ev(c, "expectation")
    assert meta["evidence_ids"] == [] and "no_evidence" in meta["evidence_issues"]


def test_f_conflicting_expectations_are_not_collapsed():
    c = classify_record(record(body="ONAYLANDI", warnings=("expectation_conflict",)))
    assert (c.classification, c.rule_ids, c.requires_review) == ("INCONCLUSIVE", ("E-EXPECTATION-CONFLICT",), True)
    timeout = classify_record(record(status_code=None, transport="timeout", outcome="ERROR",
                                     warnings=("expectation_conflict",)))
    assert timeout.classification == "TIMEOUT" and "expectation_conflict" in timeout.warnings


@pytest.mark.parametrize("source", ["FAIL", "ERROR"])
def test_g_source_fail_is_preserved_even_when_expectation_matches(source):
    r = record(expected=expect(outcomes=("REDDEDILDI",)), body="REDDEDILDI", outcome=source)
    c = classify_record(r)
    assert c.classification == "INCONCLUSIVE" and c.rule_ids == ("H-CONFLICT-SOURCE-OUTCOME",)
    assert r.with_analysis(c).test_outcome == source


def test_skipped_source_is_not_pass():
    r = record(expected=expect(outcomes=("REDDEDILDI",)), status_code=None, outcome="SKIPPED")
    c = classify_record(r)
    assert c.classification != "PASS" and r.with_analysis(c).test_outcome == "SKIPPED"


def test_h_http_200_without_business_outcome():
    c = classify_record(record(expected=expect(outcomes=("ONAYLANDI",)), body=None))
    assert c.classification == "INCONCLUSIVE" and c.rule_ids == ("H-BUSINESS-MISSING",)
    # rules-v3 (N12, F-1): ayrıştırma özeti olmayan 2xx, "yanıt alınır" beklentisiyle de PASS olmaz.
    unverified = classify_record(record(expected=expect(codes=(), transport="response"), body=None))
    assert (unverified.classification, unverified.rule_ids, unverified.confidence) == (
        "INCONCLUSIVE", ("H-STATUS-OK-BODY-UNVERIFIED",), None)
    response_only = classify_record(record(expected=expect(codes=(), transport="response"), body="OK",
                                           warnings=("response_rule:R-TEXT-TOKEN",)))
    assert (response_only.classification, response_only.rule_ids, response_only.confidence) == (
        "PASS", ("H-TRANSPORT-MATCH",), "medium")
    assert "business_outcome_not_checked" in response_only.warnings


# --- taşıma ---
def test_transport_expectations():
    timeout = classify_record(record(expected=expect(codes=(), transport="timeout", test_outcome="ERROR"),
                                     status_code=None, transport="timeout", outcome="ERROR"))
    assert timeout.classification == "TIMEOUT" and "transport_matches_expectation" in timeout.warnings
    assert "test_outcome_differs_from_expectation" not in timeout.warnings
    unexpected = classify_record(record(expected=expect(outcomes=("ONAYLANDI",)), status_code=None,
                                        transport="timeout", outcome="ERROR"))
    assert unexpected.classification == "TIMEOUT" and "transport_differs_from_expectation" in unexpected.warnings
    drop = classify_record(record(expected=expect(outcomes=("ONAYLANDI",)), status_code=None,
                                  transport="connection_error", outcome="ERROR"))
    assert drop.classification == "TRANSPORT_FAILURE"
    responded = classify_record(record(expected=expect(codes=(), transport="timeout"), body="ONAYLANDI"))
    assert (responded.classification, responded.rule_ids) == ("APPLICATION_FAILURE", ("H-TRANSPORT-MISMATCH",))


# --- kapsam ---
def test_scope_must_match_dataset_kind():
    verified_synthetic = expect(outcomes=("REDDEDILDI",))
    real = classify_record(record(expected=verified_synthetic, body="REDDEDILDI", dataset="real"))
    assert real.classification == "INCONCLUSIVE" and real.rule_ids[0] == "E-SCOPE-MISMATCH"
    unknown = classify_record(record(expected=verified_synthetic, body="REDDEDILDI", dataset="unknown"))
    assert unknown.rule_ids[0] == "E-SCOPE-UNCONFIRMED"
    verified_real = classify_record(record(expected=expect(outcomes=("REDDEDILDI",), scope="real"),
                                           body="REDDEDILDI", dataset="real"))
    assert verified_real.classification == "PASS"
    synthetic_on_real = classify_record(record(expected=expect(outcomes=("REDDEDILDI",), scope="real"),
                                               body="REDDEDILDI", dataset="synthetic"))
    assert synthetic_on_real.rule_ids[0] == "E-SCOPE-MISMATCH"


def test_expected_test_outcome_is_evidence_only():
    c = classify_record(record(expected=expect(outcomes=("REDDEDILDI",), test_outcome="FAIL"), body="REDDEDILDI"))
    assert c.classification == "PASS" and "test_outcome_differs_from_expectation" in c.warnings
    assert [e.note for e in c.evidence if e.field == "test_outcome"] == ["beklenen FAIL"]


def test_legacy_expectations_keep_previous_behaviour_with_warning():
    legacy = ExpectedResult(status_codes=(200,), business_outcomes=("ONAYLANDI",),
                            provenance=ExpectationProvenance(source=EXPECTATION_SOURCE_FILE_V1))
    c = classify_record(record(expected=legacy, body="REDDEDILDI"))
    assert c.classification == "APPLICATION_FAILURE" and "expectation_verification_unspecified" in c.warnings
    no_provenance = classify_record(record(expected=ExpectedResult(status_codes=(200,), business_outcomes=("OK",)),
                                           body="OK"))
    assert no_provenance.classification == "PASS" and ev(no_provenance, "expectation") == []


# --- uçtan uca ---
BODIES = {
    "kart-pasif-cihaz": (200, b"REDDEDILDI"),
    "kart-gecerli": (200, b"REDDEDILDI"),
    "numara-taslak": (200, b"ONAYLANDI"),
    "parmak-incelendi": (200, b"REDDEDILDI"),
    "kaynaksiz": (200, b"ONAYLANDI"),
    "cakisan": (200, b"ONAYLANDI"),
    "surumlu": (200, json.dumps({"business_outcome": "REDDEDILDI", "kartNo": KART}).encode()),
    "sadece-eski": (200, b"ONAYLANDI"),
    "zaman-asimi-beklenen": TransportTimeout(f"Read timed out kartNo={KART}"),
    "kopma": TransportConnectionError("Remote end closed connection without response"),
    "celiskili-kanit": (200, b"ONAYLANDI"),
    "eslesmeyen": (200, b"ONAYLANDI"),
}
# senaryo → (kaynak sonuç, durum, iş sonucu, sınıf, kurallar, beklenti kimliği)
EXPECTED = {
    "kart-pasif-cihaz": ("PASS", 200, "REDDEDILDI", "PASS", ["H-EXPECTED-MATCH"], "exp-kart-pasif"),
    "kart-gecerli": ("PASS", 200, "REDDEDILDI", "APPLICATION_FAILURE", ["H-BUSINESS-MISMATCH"], "exp-kart-gecerli"),
    "numara-taslak": ("PASS", 200, "ONAYLANDI", "INCONCLUSIVE", ["E-UNVERIFIED-EXPECTATION", "H-EXPECTED-MATCH"],
                      "exp-numara-taslak"),
    "parmak-incelendi": ("PASS", 200, "REDDEDILDI", "INCONCLUSIVE",
                         ["E-UNVERIFIED-EXPECTATION", "H-BUSINESS-MISMATCH"], "exp-parmak-incelendi"),
    "kaynaksiz": ("PASS", 200, "ONAYLANDI", "INCONCLUSIVE", ["E-UNVERIFIED-EXPECTATION", "H-EXPECTED-MATCH"],
                  "exp-kaynaksiz"),
    "cakisan": ("PASS", 200, "ONAYLANDI", "INCONCLUSIVE", ["E-EXPECTATION-CONFLICT"], None),
    "surumlu": ("PASS", 200, "REDDEDILDI", "PASS", ["H-EXPECTED-MATCH"], "exp-eski-v2"),
    "sadece-eski": ("PASS", 200, "ONAYLANDI", "INCONCLUSIVE", ["H-NO-EXPECTATION"], None),
    "zaman-asimi-beklenen": ("ERROR", None, None, "TIMEOUT", ["H-TIMEOUT"], "exp-zaman-asimi"),
    "kopma": ("ERROR", None, None, "TRANSPORT_FAILURE", ["H-TRANSPORT"], None),
    "celiskili-kanit": ("PASS", 200, "ONAYLANDI", "INCONCLUSIVE", ["E-UNVERIFIED-EXPECTATION", "H-EXPECTED-MATCH"],
                        "exp-celiskili-kanit"),
    "eslesmeyen": ("PASS", 200, "ONAYLANDI", "INCONCLUSIVE", ["H-NO-EXPECTATION"], None),
}


class FakeTransport:
    def send(self, scenario, url, timeout_seconds):
        outcome = BODIES[scenario.name]
        if isinstance(outcome, Exception):
            raise outcome
        status, body = outcome
        ctype = "application/json" if body.startswith(b"{") else TEXT
        return TransportResponse(status, len(body), 1.0, body=body, content_type=ctype)

    def close(self):
        pass


class Clock:
    def __init__(self):
        self.ns = 0

    def __call__(self):
        self.ns += 1_000_000
        return self.ns


@pytest.fixture
def results_dir(tmp_path):
    config = LabConfig(base_url="http://127.0.0.1:8080", output_dir=tmp_path / "results",
                       scenarios_file=tmp_path / "scenarios.json", timeout_seconds=5.0,
                       limits=RunLimits(max_consecutive_transport_errors=100, max_error_rate=1.0))
    scenarios = [Scenario(name=n, method="POST", path=f"/api/{n}", warmup_repetitions=1) for n in BODIES]
    outcome = execute_run(config, scenarios, config_path=None, run_id="n7-run", resolver=lambda h, p: ["127.0.0.1"],
                          transport_factory=FakeTransport, clock=Clock(), now=lambda: "2026-10-26T00:00:00+00:00",
                          sleep=lambda s: None, wall_clock=lambda: 0)
    assert outcome.status == "completed"
    return tmp_path / "results"


def classify_cli(results_dir, out, *extra):
    return main(["results", "classify", "--run-id", "n7-run", "--results-dir", str(results_dir), "--output",
                 str(out), "--expectations", str(REGISTRY), *extra])


def test_end_to_end_pipeline_with_registry(results_dir, tmp_path, capsys):
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in results_dir.iterdir()}
    out = tmp_path / "n7.json"
    assert classify_cli(results_dir, out, "--dataset-kind", "fixture") == EXIT_OK
    captured = capsys.readouterr()
    content = json.loads(out.read_text(encoding="utf-8"))["classification"]
    records = {r["scenario_id"]: r for r in content["records"]}
    assert set(records) == set(EXPECTED)  # ısınma istekleri atlandı
    for name, (source, status, business, cls, rules, exp_id) in EXPECTED.items():
        r = records[name]
        analysis = r["analysis"]
        assert (r["test_outcome"], r["status_code"], r["business_outcome"], analysis["classification"],
                analysis["rule_ids"]) == (source, status, business, cls, rules), name
        provenance = (r["expected_result"] or {}).get("provenance")
        assert (provenance["expectation_id"] if provenance else None) == exp_id, name
        assert analysis["reason"] and TestRecord.from_dict(r).to_dict() == r
        if cls == "INCONCLUSIVE":
            assert analysis["confidence"] is None and analysis["requires_review"] is True
    assert records["surumlu"]["expected_result"]["provenance"]["version"] == 2
    assert "expectation_conflict" in records["cakisan"]["warnings"]
    assert "expectation_deprecated_only" in records["sadece-eski"]["warnings"]
    assert "expectation_not_found" in records["eslesmeyen"]["warnings"]
    assert "transport_matches_expectation" in records["zaman-asimi-beklenen"]["analysis"]["warnings"]
    assert {"would_be": "APPLICATION_FAILURE", "rule": "H-BUSINESS-MISMATCH"} in [
        e["value"] for e in records["parmak-incelendi"]["analysis"]["evidence"] if e["field"] == "comparison"]
    source = content["sources"][0]
    assert source["expectation_matches"] == {"conflict": 1, "deprecated_only": 1, "matched": 8, "not_found": 2}
    assert source["expected_result_sources"]["scenario_expected_status"] == 0  # registry varken geri düşülmez
    assert source["expectations"]["registry"]["conflicts"] == {"cakisan": ["exp-cakisan-a", "exp-cakisan-b"]}
    assert "content_sha256=" in captured.out and "cakisan" in captured.err
    blob = out.read_text(encoding="utf-8") + captured.out + captured.err
    assert KART not in blob and str(tmp_path) not in out.read_text(encoding="utf-8")
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in results_dir.iterdir()} == before
    assert classify_cli(results_dir, out, "--dataset-kind", "fixture") == 5  # üzerine yazılmaz


def test_end_to_end_scope_is_enforced(results_dir, tmp_path):
    out = tmp_path / "unknown.json"
    assert classify_cli(results_dir, out) == EXIT_OK  # ölçüm çalıştırması: veri türü bilinmiyor
    records = {r["scenario_id"]: r for r in json.loads(out.read_text(encoding="utf-8"))["classification"]["records"]}
    assert records["kart-pasif-cihaz"]["analysis"]["rule_ids"][0] == "E-SCOPE-UNCONFIRMED"
    assert records["kart-pasif-cihaz"]["analysis"]["classification"] == "INCONCLUSIVE"


def test_end_to_end_real_draft_example_is_not_decisive(results_dir, tmp_path):
    out = tmp_path / "real.json"
    assert main(["results", "classify", "--run-id", "n7-run", "--results-dir", str(results_dir), "--output", str(out),
                 "--expectations", str(FIXTURES / "hgs2-draft-example.json"), "--dataset-kind", "real"]) == EXIT_OK
    records = {r["scenario_id"]: r for r in json.loads(out.read_text(encoding="utf-8"))["classification"]["records"]}
    r = records["kart-pasif-cihaz"]
    assert r["analysis"]["classification"] == "INCONCLUSIVE"
    assert r["analysis"]["rule_ids"] == ["E-UNVERIFIED-EXPECTATION", "H-EXPECTED-MATCH"]
    assert r["expected_result"]["provenance"]["scope"] == "real"
    assert "non_verifying_source:ev-hgs2-authcontroller" in r["expected_result"]["provenance"]["evidence_issues"]


def test_end_to_end_rejects_invalid_registry(results_dir, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["expectations"][0]["status"] = "ONAYLI"
    bad.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "x.json"
    assert main(["results", "classify", "--run-id", "n7-run", "--results-dir", str(results_dir), "--output", str(out),
                 "--expectations", str(bad)]) == EXIT_ERROR
    assert not out.exists() and "expectations[0].status" in capsys.readouterr().err  # varsayılana geri düşülmez


def test_legacy_v1_file_still_supported(results_dir, tmp_path, capsys):
    v1 = tmp_path / "v1.json"
    v1.write_text(json.dumps({"expectations_version": 1, "scenarios": {"kart-gecerli": {
        "status_codes": [200], "business_outcomes": ["ONAYLANDI"]}}}), encoding="utf-8")
    out = tmp_path / "v1-out.json"
    assert main(["results", "classify", "--run-id", "n7-run", "--results-dir", str(results_dir), "--output", str(out),
                 "--expectations", str(v1)]) == EXIT_OK
    assert "eski biçimde" in capsys.readouterr().err
    records = {r["scenario_id"]: r for r in json.loads(out.read_text(encoding="utf-8"))["classification"]["records"]}
    assert records["kart-gecerli"]["analysis"]["classification"] == "APPLICATION_FAILURE"
    assert records["kart-gecerli"]["expected_result"]["provenance"]["source"] == "expectations_file_v1"
    assert "expectation_verification_unspecified" in records["kart-gecerli"]["analysis"]["warnings"]
