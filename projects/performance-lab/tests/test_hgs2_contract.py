"""N11 birim testleri: HGS2 API sözleşmesindeki yanıt biçimleri → yanıt ayrıştırıcısı → sınıflandırıcı (ağ yok).

Yanıt biçimleri gerçek HGS2 kaynak kodundan STATİK olarak çıkarılmıştır (README "Gerçek HGS2 API sözleşmesi").
Gövdeler sentetiktir; bu testler gerçek HGS2 ile canlı entegrasyon testi DEĞİLDİR. Gerçek HGS2'ye, veritabanına
veya donanıma hiçbir istek gönderilmez.
"""

import json

import pytest

from hgs2_lab.classify import NEGATIVE_BUSINESS_OUTCOMES, classify_record
from hgs2_lab.models import RawResult
from hgs2_lab.records import DATASET_SYNTHETIC, ExpectedResult, record_from_raw_result
from hgs2_lab.response_parser import (
    RECOGNIZED_BUSINESS_OUTCOMES,
    SENSOR_STATUS_OUTCOMES,
    UNRECOGNIZED_BODY_RULES,
    parse_response,
)

TEXT = "text/plain;charset=UTF-8"  # AuthController / TerminalEnrollmentController: produces = "text/plain;charset=UTF-8"
JSON = "application/json"
KART = "KART-SENTETIK-999"  # sentetik; READY gövdesinin `value` alanında gelir, hiçbir çıktıya yazılmamalı

# uç → (durum, içerik türü, gövde, beklenen iş sonucu, beklenen ayrıştırma kuralı)
HGS2_RESPONSES = {
    "auth-onaylandi": (200, TEXT, b"ONAYLANDI", "ONAYLANDI", "R-TEXT-TOKEN"),
    "auth-reddedildi": (200, TEXT, b"REDDEDILDI", "REDDEDILDI", "R-TEXT-TOKEN"),
    "terminal-ok": (200, TEXT, b"OK", "OK", "R-TEXT-TOKEN"),
    "terminal-hata": (200, TEXT, b"HATA", "HATA", "R-TEXT-TOKEN"),
    "pending-none": (200, TEXT, b"NONE", "NONE", "R-TEXT-TOKEN"),
    "pending-card": (200, TEXT, b"SCAN_CARD", "SCAN_CARD", "R-TEXT-TOKEN"),
    "pending-fp": (200, TEXT, b"SCAN_FP", "SCAN_FP", "R-TEXT-TOKEN"),
    "pending-school-no": (200, TEXT, b"SCAN_SCHOOL_NO", "SCAN_SCHOOL_NO", "R-TEXT-TOKEN"),
    "result-waiting": (200, JSON, b'{"status":"WAITING"}', "WAITING", "R-JSON-STATUS"),
    "result-ready": (200, JSON, json.dumps({"status": "READY", "value": KART}).encode(), "READY", "R-JSON-STATUS"),
    "start-session": (200, JSON, b'{"sessionId":"abc123def456"}', None, "R-JSON-UNRECOGNIZED"),
    "start-bad-type": (400, JSON, b'{"error":"Gecersiz tip: X"}', None, "R-JSON-UNRECOGNIZED"),
    # Spring Boot'un varsayılan hata gövdesi biçimi (HGS2 kaynağında değil, çerçevenin davranışı; doğrulanmadı)
    "spring-error": (400, JSON, b'{"timestamp":"2026-01-01T00:00:00","status":400,"error":"Bad Request"}', None,
                     "R-JSON-UNRECOGNIZED"),
}


def raw(status, outcome, http_ok, scenario="s", run_id="run-n11"):
    return RawResult(run_id=run_id, seq=1, scenario=scenario, iteration=1, warmup=False, method="POST",
                     url="http://127.0.0.1:1/x", started_at="2026-01-01T00:00:00+00:00", offset_ms=0.0,
                     elapsed_ms=1.0, duration_ms=1.0, status_code=status, http_ok=http_ok,
                     business_outcome=outcome, response_bytes=1)


def classify_body(status, content_type, body, expected=None):
    parsed = parse_response(status, content_type, body)
    # http_ok, runner'daki gibi senaryonun durum beklentisinden gelir (boşsa 2xx; Scenario.is_expected_status)
    codes = expected.status_codes if expected is not None and expected.status_codes else ()
    http_ok = status in codes if codes else 200 <= status < 300
    record = record_from_raw_result(raw(status, parsed.business_outcome, http_ok), dataset_kind=DATASET_SYNTHETIC,
                                    expected=expected, parsed=parsed)
    return parsed, classify_record(record)


# --- A. ayrıştırma: HGS2 sözleşmesindeki her biçim ---
@pytest.mark.parametrize("name", sorted(HGS2_RESPONSES))
def test_every_hgs2_response_shape_is_parsed_as_contracted(name):
    status, ctype, body, outcome, rule = HGS2_RESPONSES[name]
    r = parse_response(status, ctype, body)
    assert (r.business_outcome, r.rule_id, r.status_code) == (outcome, rule, status), name


def test_contract_tokens_are_all_recognized():
    assert {o for *_, o, _ in HGS2_RESPONSES.values() if o} <= RECOGNIZED_BUSINESS_OUTCOMES
    assert SENSOR_STATUS_OUTCOMES == {"WAITING", "READY"}


def test_sensor_states_are_not_negative_and_ready_is_not_approval():
    for token in ("WAITING", "READY", "NONE", "SCAN_CARD", "SCAN_FP", "SCAN_SCHOOL_NO", "ONAYLANDI", "OK"):
        assert token not in NEGATIVE_BUSINESS_OUTCOMES
    assert "READY" != "ONAYLANDI" and parse_response(200, JSON, b'{"status":"READY"}').business_outcome == "READY"


@pytest.mark.parametrize(
    "body, warning",
    [
        ({"value": KART}, "business_outcome_not_found"),  # status alanı eksik
        ({"status": "BILINMEYEN"}, "status_field_unrecognized"),
        ({"status": "ONAYLANDI"}, "status_field_unrecognized"),  # status alanında yalnızca sensör durumları tanınır
        ({"status": 200}, "business_outcome_not_found"),  # sayısal status (ör. Spring hata gövdesi)
        ({"data": {"status": "WAITING"}}, "business_outcome_not_found"),  # iç içe aranmaz
    ],
)
def test_json_without_recognized_status_is_unrecognized(body, warning):
    r = parse_response(200, JSON, json.dumps(body).encode())
    assert (r.business_outcome, r.rule_id) == (None, "R-JSON-UNRECOGNIZED") and warning in r.warnings


def test_status_field_ignores_case_and_whitespace_and_business_field_wins():
    assert parse_response(200, JSON, b'{"status":" waiting "}').business_outcome == "WAITING"
    both = parse_response(200, JSON, b'{"status":"WAITING","business_outcome":"REDDEDILDI"}')
    assert (both.business_outcome, both.rule_id) == ("REDDEDILDI", "R-JSON-FIELD")  # Lab sözleşmesi önceliklidir


def test_ready_value_never_reaches_the_summary():
    r = parse_response(200, JSON, json.dumps({"status": "READY", "value": KART}).encode())
    assert KART not in json.dumps(r.to_dict())


@pytest.mark.parametrize(
    "status, ctype, body, rule",
    [
        (200, TEXT, b"BEKLENMEYEN", "R-TEXT-UNRECOGNIZED"),
        (200, TEXT, b"", "R-EMPTY-BODY"),
        (200, JSON, b'{"status": "WAIT', "R-MALFORMED-JSON"),
        (200, TEXT, b"\xff\xfe\xfa", "R-UNDECODABLE"),
        (200, "text/html", b"<p>ONAYLANDI</p>", "R-UNSUPPORTED-TYPE"),
    ],
)
def test_broken_or_unexpected_bodies_yield_no_outcome(status, ctype, body, rule):
    r = parse_response(status, ctype, body)
    assert (r.business_outcome, r.rule_id) == (None, rule)


# --- A/C. sınıflandırma: HTTP sonucu ile iş sonucu ayrıdır; bilinmeyen yanıt PASS olmaz ---
STATUS_ONLY = ExpectedResult(status_codes=(200,))


@pytest.mark.parametrize("name", ["start-session"])
def test_http_200_with_unknown_body_and_status_only_expectation_is_not_pass(name):
    status, ctype, body, _, rule = HGS2_RESPONSES[name]
    _, c = classify_body(status, ctype, body, STATUS_ONLY)
    assert c.classification == "INCONCLUSIVE" and c.rule_ids == ("H-STATUS-OK-UNKNOWN-BODY",)
    assert c.requires_review and c.confidence is None and "business_outcome_unrecognized" in c.warnings


@pytest.mark.parametrize(
    "ctype, body",
    [(TEXT, b"BEKLENMEYEN"), (JSON, b'{"status": "WAIT'), (JSON, b'{"status":"BILINMEYEN"}'), ("text/html", b"<p/>"),
     (TEXT, b"\xff\xfe\xfa")],
)
def test_unknown_or_unparseable_200_bodies_are_inconclusive_with_status_or_response_only(ctype, body):
    for expected in (STATUS_ONLY, ExpectedResult(expected_transport="response")):
        _, c = classify_body(200, ctype, body, expected)
        assert c.classification == "INCONCLUSIVE" and c.rule_ids == ("H-STATUS-OK-UNKNOWN-BODY",)


def test_empty_200_body_with_status_only_expectation_is_not_pass():
    # rules-v3 (N12, F-1): belgelenen her HGS2 200 ucu gövde döndürür; boş 200 durum kodu tuttu diye PASS olmaz.
    _, c = classify_body(200, TEXT, b"", STATUS_ONLY)
    assert (c.classification, c.rule_ids, c.confidence) == ("INCONCLUSIVE", ("H-STATUS-OK-EMPTY-BODY",), None)
    assert "response_body_empty" in c.warnings and c.requires_review


def test_bodyless_204_keeps_status_pass():
    # HGS2 `DELETE /api/sensor/session` → 204, gövde yok (README sözleşme tablosu).
    _, c = classify_body(204, None, b"", ExpectedResult(status_codes=(204,)))
    assert (c.classification, c.rule_ids) == ("PASS", ("H-STATUS-MATCH",))


def test_too_large_200_body_with_status_only_expectation_is_not_pass():
    _, c = classify_body(200, TEXT, b"OK" + b" " * 5000, STATUS_ONLY)
    assert (c.classification, c.rule_ids) == ("INCONCLUSIVE", ("H-STATUS-OK-BODY-NOT-PARSED",))


@pytest.mark.parametrize("name", ["result-waiting", "result-ready", "pending-none", "pending-card"])
def test_sensor_states_with_status_only_expectation_are_not_success(name):
    status, ctype, body, outcome, _ = HGS2_RESPONSES[name]
    _, c = classify_body(status, ctype, body, STATUS_ONLY)
    assert (c.classification, c.rule_ids) == ("INCONCLUSIVE", ("H-STATUS-OK-STATE-BODY",)), name
    assert outcome in c.reason and "business_outcome_state_only" in c.warnings


@pytest.mark.parametrize("name", ["auth-onaylandi", "terminal-ok"])
def test_positive_outcome_with_status_only_expectation_stays_a_limited_pass(name):
    status, ctype, body, _, _ = HGS2_RESPONSES[name]
    _, c = classify_body(status, ctype, body, STATUS_ONLY)
    assert (c.classification, c.rule_ids, c.confidence) == ("PASS", ("H-STATUS-MATCH",), "medium")
    assert "business_outcome_not_checked" in c.warnings


def test_unexpected_5xx_is_application_failure():
    _, c = classify_body(500, JSON, b'{"timestamp":"2026-01-01T00:00:00","status":500,"error":"Internal Server Error"}',
                         STATUS_ONLY)
    assert (c.classification, c.rule_ids) == ("APPLICATION_FAILURE", ("H-STATUS-MISMATCH",))


def test_expected_4xx_with_framework_error_body_is_decided_by_status():
    status, ctype, body, _, _ = HGS2_RESPONSES["spring-error"]
    _, ok = classify_body(status, ctype, body, ExpectedResult(status_codes=(400,)))
    assert (ok.classification, ok.rule_ids) == ("PASS", ("H-STATUS-MATCH",))
    _, bad = classify_body(status, ctype, body, STATUS_ONLY)
    assert (bad.classification, bad.rule_ids) == ("APPLICATION_FAILURE", ("H-STATUS-MISMATCH",))


def test_http_200_rejection_is_not_success():
    _, c = classify_body(200, TEXT, b"REDDEDILDI", ExpectedResult(status_codes=(200,), business_outcomes=("ONAYLANDI",)))
    assert (c.classification, c.rule_ids) == ("APPLICATION_FAILURE", ("H-BUSINESS-MISMATCH",))
    _, unchecked = classify_body(200, TEXT, b"REDDEDILDI", STATUS_ONLY)
    assert (unchecked.classification, unchecked.rule_ids) == ("INCONCLUSIVE", ("H-STATUS-OK-NEGATIVE-BODY",))


def test_approved_and_rejected_are_distinguished():
    approve = ExpectedResult(status_codes=(200,), business_outcomes=("ONAYLANDI",))
    reject = ExpectedResult(status_codes=(200,), business_outcomes=("REDDEDILDI",))
    assert classify_body(200, TEXT, b"ONAYLANDI", approve)[1].classification == "PASS"
    assert classify_body(200, TEXT, b"REDDEDILDI", reject)[1].classification == "PASS"
    assert classify_body(200, TEXT, b"ONAYLANDI", reject)[1].classification == "APPLICATION_FAILURE"


@pytest.mark.parametrize("name", ["result-waiting", "result-ready"])
def test_sensor_result_never_satisfies_an_authentication_expectation(name):
    status, ctype, body, _, _ = HGS2_RESPONSES[name]
    _, c = classify_body(status, ctype, body, ExpectedResult(status_codes=(200,), business_outcomes=("ONAYLANDI",)))
    assert c.classification == "APPLICATION_FAILURE" and c.rule_ids == ("H-BUSINESS-MISMATCH",)


def test_sensor_waiting_is_neither_error_nor_approval_under_a_sensor_expectation():
    sensor = ExpectedResult(status_codes=(200,), business_outcomes=("WAITING", "READY"))
    for name in ("result-waiting", "result-ready"):
        status, ctype, body, _, _ = HGS2_RESPONSES[name]
        _, c = classify_body(status, ctype, body, sensor)
        assert (c.classification, c.rule_ids) == ("PASS", ("H-EXPECTED-MATCH",)), name
    _, no_expectation = classify_body(200, JSON, b'{"status":"WAITING"}')
    assert no_expectation.classification == "INCONCLUSIVE"
    assert "negative_business_outcome_observed" not in no_expectation.warnings


def test_pending_none_matches_its_contracted_meaning():
    _, c = classify_body(200, TEXT, b"NONE", ExpectedResult(status_codes=(200,), business_outcomes=("NONE",)))
    assert (c.classification, c.rule_ids) == ("PASS", ("H-EXPECTED-MATCH",))
    _, scan = classify_body(200, TEXT, b"SCAN_CARD", ExpectedResult(status_codes=(200,), business_outcomes=("NONE",)))
    assert scan.classification == "APPLICATION_FAILURE"


def test_http_error_status_with_business_body_keeps_both_axes():
    parsed, c = classify_body(500, TEXT, b"HATA", ExpectedResult(status_codes=(200,), business_outcomes=("OK",)))
    assert parsed.business_outcome == "HATA" and parsed.status_code == 500
    assert c.rule_ids == ("H-STATUS-AND-BUSINESS-MISMATCH",)


def test_unrecognized_rule_set_is_explicit():
    assert UNRECOGNIZED_BODY_RULES == {"R-TEXT-UNRECOGNIZED", "R-JSON-UNRECOGNIZED", "R-MALFORMED-JSON",
                                       "R-UNDECODABLE", "R-UNSUPPORTED-TYPE"}


def test_classification_output_contains_no_body_values():
    _, c = classify_body(200, JSON, json.dumps({"status": "READY", "value": KART}).encode(), STATUS_ONLY)
    assert KART not in json.dumps(c.to_dict(), ensure_ascii=False)
