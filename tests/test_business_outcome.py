"""İş sonucu çıkarımı: yanıt → runner (response_parser) → RawResult → TestRecord → N4 (ağ yok).

Gerçek `ScenarioRunner` sahte bir taşıyıcıyla çalışır; soket açılmaz. Gövdelerdeki kişisel değerler sentetiktir.
"""

import json
import socket

import pytest

from hgs2_lab.classify import classify_record
from hgs2_lab.models import RawResult
from hgs2_lab.records import (
    CLASS_APPLICATION_FAILURE,
    CLASS_INCONCLUSIVE,
    CLASS_PASS,
    CLASS_TIMEOUT,
    CLASS_TRANSPORT_FAILURE,
    DATASET_FIXTURE,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_SKIPPED,
    QUALITY_PARTIAL,
    QUALITY_VALID,
    SOURCE_LAB_RESULT,
    ExpectedResult,
    RecordError,
    TestRecord,
    record_from_raw_result,
)
from hgs2_lab.response_parser import ParsedResponse
from hgs2_lab.runner import ScenarioRunner
from hgs2_lab.scenarios import Scenario
from hgs2_lab.transport import TransportConnectionError, TransportResponse, TransportTimeout

KART = "KART-SENTETIK-111"
ACCEPT = ExpectedResult(status_codes=(200,), business_outcomes=("ONAYLANDI",), description="geçerli kart kabul")
REJECT = ExpectedResult(status_codes=(200,), business_outcomes=("REDDEDILDI",), description="pasif cihaz reddi")
TEXT = "text/plain;charset=UTF-8"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class FakeTransport:
    def __init__(self, outcome):
        self.outcome = outcome

    def send(self, scenario, url, timeout_seconds):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class Clock:
    def __init__(self):
        self.ns = 1_000

    def __call__(self):
        self.ns += 1_000_000
        return self.ns


def run_one(outcome, expected_status=(200,)):
    """Gerçek runner yolu: (RawResult, ParsedResponse | None)."""
    runner = ScenarioRunner(FakeTransport(outcome), "http://127.0.0.1:8080", "run-n6", 5.0, sleep=lambda s: None,
                            now=lambda: "2026-10-26T00:00:00+00:00", clock=Clock(), wall_clock=lambda: 0)
    [result] = runner.run(Scenario(name="kart", method="POST", path="/api/auth/kart-okut",
                                   expected_status=tuple(expected_status)))
    entries = runner.response_parsing
    parsed = ParsedResponse.from_dict({k: v for k, v in entries[0].items() if k != "seq"}) if entries else None
    if entries:
        assert entries[0]["seq"] == result.seq
    return result, parsed


def response(body, status=200, content_type=TEXT):
    return TransportResponse(status_code=status, size_bytes=len(body), duration_ms=1.0, body=body,
                             content_type=content_type)


def analyse(outcome, expected=None, expected_status=(200,)):
    result, parsed = run_one(outcome, expected_status)
    record = record_from_raw_result(result, dataset_kind=DATASET_FIXTURE, expected=expected, parsed=parsed)
    return result, record, classify_record(record)


def evidence(c, field):
    return [e.value for e in c.evidence if e.field == field]


# --- davranış tablosu ---
def test_200_reject_expected_reject_is_pass():
    result, record, c = analyse(response(b"REDDEDILDI"), REJECT)
    assert result.business_outcome == "REDDEDILDI" and record.test_outcome == OUTCOME_PASS
    assert (c.classification, c.rule_ids, c.confidence) == (CLASS_PASS, ("H-EXPECTED-MATCH",), "high")
    assert evidence(c, "response_parsing") == [["response_rule:R-TEXT-TOKEN"]]


def test_200_reject_expected_accept_is_application_failure():
    _, record, c = analyse(response(b"REDDEDILDI"), ACCEPT)
    assert record.test_outcome == OUTCOME_PASS  # Lab'in HTTP denetimi geçti; kaynak sonuç korunur
    assert (c.classification, c.rule_ids) == (CLASS_APPLICATION_FAILURE, ("H-BUSINESS-MISMATCH",))
    assert "source_outcome_differs" in c.warnings and not c.requires_review


def test_200_reject_expectation_unknown_stays_uncertain():
    _, record, c = analyse(response(b"REDDEDILDI"), None)
    assert record.business_outcome == "REDDEDILDI"
    assert (c.classification, c.confidence, c.requires_review) == (CLASS_INCONCLUSIVE, None, True)
    assert "negative_business_outcome_observed" in c.warnings


@pytest.mark.parametrize("expected", [ACCEPT, REJECT])
def test_200_empty_body_never_infers_business_success(expected):
    result, record, c = analyse(response(b""), expected)
    assert result.business_outcome is None and "response_empty_body" in record.warnings
    assert (c.classification, c.rule_ids) == (CLASS_INCONCLUSIVE, ("H-BUSINESS-MISSING",))


def test_200_empty_body_status_only_expectation_is_not_pass():
    # rules-v3 (N12, F-1): boş 200 gövdesi, yalnızca durum kodu tuttu diye PASS sayılmaz.
    _, _, c = analyse(response(b""), ExpectedResult(status_codes=(200,)))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-STATUS-OK-EMPTY-BODY",)
    assert c.confidence is None and "response_body_empty" in c.warnings


def test_200_positive_body_status_only_expectation_is_explicitly_status_only():
    _, _, c = analyse(response(b"ONAYLANDI"), ExpectedResult(status_codes=(200,)))
    assert c.classification == CLASS_PASS and c.confidence == "medium"
    assert "business_outcome_not_checked" in c.warnings  # iş başarısı iddia edilmez


def test_200_malformed_json_is_warning_not_application_failure():
    result, record, c = analyse(response(b'{"business_outcome": "REDD', content_type="application/json"), ACCEPT)
    assert result.status_code == 200 and result.business_outcome is None
    assert record.data_quality_status == QUALITY_PARTIAL and "response_malformed_json" in record.warnings
    assert c.classification == CLASS_INCONCLUSIVE and c.classification != CLASS_APPLICATION_FAILURE
    assert ["response_rule:R-MALFORMED-JSON", "response_malformed_json"] in evidence(c, "response_parsing")


def test_500_keeps_status_and_body_separate():
    result, record, c = analyse(response(b"HATA", status=500), ACCEPT)
    assert (result.status_code, result.business_outcome, result.http_ok) == (500, "HATA", False)
    assert record.test_outcome == OUTCOME_FAIL
    assert (c.classification, c.rule_ids) == (CLASS_APPLICATION_FAILURE, ("H-STATUS-AND-BUSINESS-MISMATCH",))


def test_http_error_with_expected_error_and_negative_body():
    _, _, c = analyse(response(b"HATA", status=500), ExpectedResult(status_codes=(500,)), expected_status=(500,))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-STATUS-OK-NEGATIVE-BODY",)
    _, _, c2 = analyse(response(b"HATA", status=400), ExpectedResult(status_codes=(400,), business_outcomes=("HATA",)),
                       expected_status=(400,))
    assert c2.classification == CLASS_PASS  # beklenen hata yanıtı: test başarılı


def test_business_and_status_conflict():
    """İş sonucu beklenen, ama durum kodu değil: durum uyuşmazlığı ayrı kanıtlanır."""
    _, _, c = analyse(response(b"ONAYLANDI", status=503), ACCEPT)
    assert c.classification == CLASS_APPLICATION_FAILURE and c.rule_ids == ("H-STATUS-MISMATCH",)
    assert "gateway_status" in c.warnings and c.requires_review


def test_timeout_and_connection_drop_use_existing_error_model():
    result, record, c = analyse(TransportTimeout("Read timed out"), ACCEPT)
    assert (result.error_type, result.business_outcome, record.test_outcome) == ("timeout", None, OUTCOME_ERROR)
    assert c.classification == CLASS_TIMEOUT
    result, record, c = analyse(TransportConnectionError("Remote end closed connection"), ACCEPT)
    assert result.error_type == "connection_error" and c.classification == CLASS_TRANSPORT_FAILURE
    _, parsed = run_one(TransportTimeout("x"))
    assert parsed is None  # yanıt yoksa ayrıştırma özeti tutulmaz


def test_json_field_and_unsupported_type():
    _, record, c = analyse(response(json.dumps({"business_outcome": "ONAYLANDI", "kartNo": KART}).encode(),
                                    content_type="application/json"), ACCEPT)
    assert record.business_outcome == "ONAYLANDI" and c.classification == CLASS_PASS
    _, record, c = analyse(response(b"<p>REDDEDILDI</p>", content_type="text/html"), REJECT)
    assert record.business_outcome is None and "response_unsupported_content_type" in record.warnings
    assert c.classification == CLASS_INCONCLUSIVE


def test_large_body_is_not_parsed_and_says_so():
    _, record, c = analyse(response(b"REDDEDILDI" + b" " * 5000), REJECT)
    assert record.business_outcome is None and "response_body_too_large_not_parsed" in record.warnings
    assert c.classification == CLASS_INCONCLUSIVE


# --- kaynak sonucu korunur ---
def test_source_fail_is_never_turned_into_pass():
    _, record, c = analyse(response(b"REDDEDILDI", status=200), REJECT, expected_status=(201,))
    assert record.test_outcome == OUTCOME_FAIL  # Lab'in durum denetimi (201 bekliyordu) başarısız
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-CONFLICT-SOURCE-OUTCOME",)


def test_skipped_source_is_not_shown_as_pass():
    record = TestRecord(record_id="r-skip", source_type=SOURCE_LAB_RESULT, dataset_kind=DATASET_FIXTURE,
                        test_outcome=OUTCOME_SKIPPED, expected_result=REJECT)
    c = classify_record(record)
    assert record.with_analysis(c).test_outcome == OUTCOME_SKIPPED and c.classification != CLASS_PASS


# --- tutarlılık ve gizlilik ---
def test_parsed_summary_must_match_result():
    result, parsed = run_one(response(b"REDDEDILDI"))
    with pytest.raises(RecordError, match="iş sonucu"):
        record_from_raw_result(result, dataset_kind=DATASET_FIXTURE,
                               parsed=ParsedResponse.from_dict({**parsed.to_dict(), "business_outcome": "OK"}))
    with pytest.raises(RecordError, match="durum kodu"):
        record_from_raw_result(result, dataset_kind=DATASET_FIXTURE,
                               parsed=ParsedResponse.from_dict({**parsed.to_dict(), "status_code": 500}))
    with pytest.raises(RecordError):
        record_from_raw_result(result, dataset_kind=DATASET_FIXTURE, parsed={"rule_id": "R-TEXT-TOKEN"})


def test_valid_parse_keeps_quality_valid():
    _, record, _ = analyse(response(b"ONAYLANDI"), ACCEPT)
    assert record.data_quality_status == QUALITY_VALID


def test_sensitive_body_values_do_not_reach_result_record_or_analysis():
    bodies = [
        response(json.dumps({"business_outcome": "REDDEDILDI", "kartNo": KART}).encode(), content_type="application/json"),
        response(f"kartNo={KART}".encode()),
        response(f'{{"kartNo": "{KART}"'.encode(), content_type="application/json"),
        response(f"<b>{KART}</b>".encode(), content_type="text/html"),
    ]
    for body in bodies:
        result, parsed = run_one(body)
        record = record_from_raw_result(result, dataset_kind=DATASET_FIXTURE, expected=ACCEPT, parsed=parsed)
        analysed = record.with_analysis(classify_record(record))
        blob = json.dumps([result.to_dict(), parsed.to_dict(), analysed.to_dict()], ensure_ascii=False)
        assert KART not in blob


def test_raw_result_schema_is_unchanged():
    assert RawResult.field_names() == [
        "run_id", "seq", "scenario", "iteration", "warmup", "method", "url", "started_at", "offset_ms", "elapsed_ms",
        "duration_ms", "status_code", "http_ok", "business_outcome", "error_type", "error", "response_bytes"]
