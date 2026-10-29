"""classify.py birim testleri: her sınıf ve kural, beklenen/gözlenen ayrımı, belirsizlik, kanıt ve maskeleme.

Kayıtlar doğrudan sentetik değerlerle kurulur; ağ yok, F5 kullanılmaz.
"""

import json

import pytest

from hgs2_lab.classify import CLASSIFIER_VERSION, classify_record, classify_records
from hgs2_lab.records import (
    CLASS_APPLICATION_FAILURE,
    CLASS_INCONCLUSIVE,
    CLASS_INVALID_TEST_DATA,
    CLASS_PASS,
    CLASS_TEST_INFRASTRUCTURE_FAILURE,
    CLASS_TIMEOUT,
    CLASS_TRANSPORT_FAILURE,
    CLASS_UNKNOWN,
    CLASSES,
    DATASET_FIXTURE,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_SKIPPED,
    OUTCOME_UNKNOWN,
    QUALITY_CONTRADICTORY,
    QUALITY_INVALID,
    QUALITY_PARTIAL,
    SOURCE_JUNIT_XML,
    SOURCE_LAB_RESULT,
    ExpectedResult,
    TestRecord,
)

KART = "KART-SENTETIK-111"
ACCEPT = ExpectedResult(status_codes=(200,), business_outcomes=("ONAYLANDI",), description="geçerli kart kabul")
REJECT = ExpectedResult(status_codes=(200,), business_outcomes=("REDDEDILDI",), description="pasif cihaz reddi")


def http(**overrides):
    values = dict(record_id="r-http", source_type=SOURCE_LAB_RESULT, dataset_kind=DATASET_FIXTURE,
                  test_outcome=OUTCOME_PASS)
    values.update(overrides)
    return TestRecord(**values)


def junit(outcome, **overrides):
    values = dict(record_id="r-junit", source_type=SOURCE_JUNIT_XML, dataset_kind=DATASET_FIXTURE,
                  test_outcome=outcome, test_name="t")
    values.update(overrides)
    return TestRecord(**values)


def fields_of(result):
    return {e.field for e in result.evidence}


# --- HTTP ve iş sonucu ---
def test_http_200_with_expected_success_is_pass():
    c = classify_record(http(status_code=200, business_outcome="ONAYLANDI", expected_result=ACCEPT))
    assert (c.classification, c.rule_ids, c.confidence, c.requires_review) == (
        CLASS_PASS, ("H-EXPECTED-MATCH",), "high", False)
    assert {"status_code", "business_outcome", "expected_result"} <= fields_of(c)


def test_http_200_with_unexpected_rejection_is_application_failure():
    c = classify_record(http(status_code=200, business_outcome="REDDEDILDI", expected_result=ACCEPT))
    assert c.classification == CLASS_APPLICATION_FAILURE and c.rule_ids == ("H-BUSINESS-MISMATCH",)
    mismatch = [e for e in c.evidence if e.source == "rule"]
    assert [(e.field, e.value) for e in mismatch] == [("business_outcome", "REDDEDILDI")]
    assert "ONAYLANDI" in mismatch[0].note
    assert "source_outcome_differs" in c.warnings  # Lab HTTP denetimi PASS dedi; kaynak sonuç korunur


def test_expected_rejection_scenario_is_pass():
    c = classify_record(http(status_code=200, business_outcome="REDDEDILDI", expected_result=REJECT))
    assert c.classification == CLASS_PASS and c.rule_ids == ("H-EXPECTED-MATCH",)


def test_expected_rejection_but_accepted_is_failure():
    c = classify_record(http(status_code=200, business_outcome="ONAYLANDI", expected_result=REJECT))
    assert c.classification == CLASS_APPLICATION_FAILURE


def test_business_outcome_comparison_ignores_case_and_whitespace():
    c = classify_record(http(status_code=200, business_outcome=" reddedildi\n", expected_result=REJECT))
    assert c.classification == CLASS_PASS


@pytest.mark.parametrize("body", ["REDDEDILDI", "HATA", "ONAYLANDI", None])
def test_unknown_expectation_is_never_decisive(body):
    c = classify_record(http(status_code=200, business_outcome=body))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-NO-EXPECTATION",)
    assert c.confidence is None and c.requires_review
    assert "expected_result_unknown" in c.warnings
    if body in ("REDDEDILDI", "HATA"):
        assert "negative_business_outcome_observed" in c.warnings


def test_empty_expected_result_counts_as_unknown():
    c = classify_record(http(status_code=500, expected_result=ExpectedResult()))
    assert c.classification == CLASS_INCONCLUSIVE and "server_error_status_observed" in c.warnings


def test_http_200_without_business_outcome_is_not_business_success():
    """Beklenti iş sonucu içeriyorsa gövde yokken PASS verilmez."""
    c = classify_record(http(status_code=200, expected_result=ACCEPT))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-BUSINESS-MISSING",)
    assert "business_outcome_missing" in c.warnings


def test_status_only_expectation_passes_with_explicit_limitation():
    """Gövde ayrıştırıldı ve olumlu bir iş sonucu taşıyor: yalnızca durum kodu beklentisi PASS (medium) verir."""
    c = classify_record(http(status_code=200, business_outcome="ONAYLANDI", warnings=("response_rule:R-TEXT-TOKEN",),
                             expected_result=ExpectedResult(status_codes=(200,))))
    assert c.classification == CLASS_PASS and c.rule_ids == ("H-STATUS-MATCH",) and c.confidence == "medium"
    assert "business_outcome_not_checked" in c.warnings
    assert any("HTTP 200 iş mantığı başarısını tek başına kanıtlamaz" in text for text in c.limitations)


# --- rules-v3 (N12, F-1): 2xx + yalnızca durum kodu beklentisi, gövde hakkında güvenilir kanıt yok ---
STATUS_ONLY = ExpectedResult(status_codes=(200, 204))


@pytest.mark.parametrize(
    "status, outcome, warnings, rule",
    [
        (200, None, (), "H-STATUS-OK-BODY-UNVERIFIED"),  # ayrıştırma özeti yok (eksik/bozuk metadata, eski dosya)
        (200, None, ("response_parsing_missing",), "H-STATUS-OK-BODY-UNVERIFIED"),
        (200, None, ("response_rule:R-EMPTY-BODY", "response_empty_body"), "H-STATUS-OK-EMPTY-BODY"),
        (200, None, ("response_rule:R-TOO-LARGE",), "H-STATUS-OK-BODY-NOT-PARSED"),
        (200, None, ("response_rule:R-BODY-NOT-CAPTURED",), "H-STATUS-OK-BODY-NOT-PARSED"),
        (200, None, ("response_rule:R-TEXT-UNRECOGNIZED",), "H-STATUS-OK-UNKNOWN-BODY"),
        (200, None, ("response_rule:R-MALFORMED-JSON",), "H-STATUS-OK-UNKNOWN-BODY"),
        (200, "WAITING", ("response_rule:R-JSON-STATUS",), "H-STATUS-OK-STATE-BODY"),
        (200, "READY", ("response_rule:R-JSON-STATUS",), "H-STATUS-OK-STATE-BODY"),
        (200, "NONE", ("response_rule:R-TEXT-TOKEN",), "H-STATUS-OK-STATE-BODY"),
        (200, "SCAN_CARD", ("response_rule:R-TEXT-TOKEN",), "H-STATUS-OK-STATE-BODY"),
    ],
)
def test_status_only_2xx_without_body_evidence_is_inconclusive(status, outcome, warnings, rule):
    for expected in (STATUS_ONLY, ExpectedResult(expected_transport="response")):
        c = classify_record(http(status_code=status, business_outcome=outcome, warnings=warnings,
                                 expected_result=expected))
        assert (c.classification, c.rule_ids, c.confidence) == (CLASS_INCONCLUSIVE, (rule,), None)
        assert c.requires_review and "business_expectation_missing" in c.warnings
        assert any("HTTP 200 iş mantığı başarısını tek başına kanıtlamaz" in text for text in c.limitations)


def test_bodyless_success_status_with_empty_body_keeps_status_only_pass():
    """204/205 gövdesiz yanıt tanımlar (ör. HGS2 `DELETE /api/sensor/session`): boş gövde eksik kanıt değildir."""
    for warnings in (("response_rule:R-EMPTY-BODY",), ()):
        c = classify_record(http(status_code=204, warnings=warnings, expected_result=STATUS_ONLY))
        assert (c.classification, c.rule_ids, c.confidence) == (CLASS_PASS, ("H-STATUS-MATCH",), "medium")


def test_state_outcome_still_passes_under_an_explicit_state_expectation():
    c = classify_record(http(status_code=200, business_outcome="WAITING", warnings=("response_rule:R-JSON-STATUS",),
                             expected_result=ExpectedResult(status_codes=(200,), business_outcomes=("WAITING",))))
    assert (c.classification, c.rule_ids) == (CLASS_PASS, ("H-EXPECTED-MATCH",))
    auth = classify_record(http(status_code=200, business_outcome="READY", warnings=("response_rule:R-JSON-STATUS",),
                                expected_result=ACCEPT))
    assert (auth.classification, auth.rule_ids) == (CLASS_APPLICATION_FAILURE, ("H-BUSINESS-MISMATCH",))


def test_body_rules_do_not_change_expected_non_2xx_decisions():
    for status in (302, 400, 404, 500):
        c = classify_record(http(status_code=status, warnings=("response_rule:R-EMPTY-BODY",),
                                 expected_result=ExpectedResult(status_codes=(status,))))
        assert (c.classification, c.rule_ids) == (CLASS_PASS, ("H-STATUS-MATCH",)), status
    bad = classify_record(http(status_code=503, warnings=("response_rule:R-EMPTY-BODY",), expected_result=STATUS_ONLY))
    assert (bad.classification, bad.rule_ids) == (CLASS_APPLICATION_FAILURE, ("H-STATUS-MISMATCH",))
    assert "gateway_status" in bad.warnings and bad.requires_review


def test_status_only_expectation_with_negative_body_is_inconclusive():
    c = classify_record(http(status_code=200, business_outcome="HATA",
                             expected_result=ExpectedResult(status_codes=(200,))))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-STATUS-OK-NEGATIVE-BODY",)


def test_expected_404_is_pass():
    c = classify_record(http(status_code=404, test_outcome=OUTCOME_PASS,
                             expected_result=ExpectedResult(status_codes=(404,))))
    assert c.classification == CLASS_PASS


@pytest.mark.parametrize("status", [400, 404, 409])
def test_unexpected_4xx_is_application_failure(status):
    c = classify_record(http(status_code=status, test_outcome=OUTCOME_FAIL,
                             expected_result=ExpectedResult(status_codes=(200,))))
    assert c.classification == CLASS_APPLICATION_FAILURE and c.rule_ids == ("H-STATUS-MISMATCH",)
    assert c.confidence == "high" and not c.requires_review


def test_unexpected_500_is_application_failure():
    c = classify_record(http(status_code=500, test_outcome=OUTCOME_FAIL, expected_result=ACCEPT,
                             business_outcome="HATA"))
    assert c.classification == CLASS_APPLICATION_FAILURE and c.rule_ids == ("H-STATUS-AND-BUSINESS-MISMATCH",)


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_5xx_requires_review(status):
    c = classify_record(http(status_code=status, test_outcome=OUTCOME_FAIL,
                             expected_result=ExpectedResult(status_codes=(200,))))
    assert c.classification == CLASS_APPLICATION_FAILURE and c.requires_review
    assert "gateway_status" in c.warnings and c.limitations


def test_unrecognized_business_outcome_lowers_confidence():
    c = classify_record(http(status_code=200, business_outcome="BEKLENMEDIK", expected_result=ACCEPT))
    assert c.classification == CLASS_APPLICATION_FAILURE and c.confidence == "medium" and c.requires_review
    assert "unrecognized_business_outcome" in c.warnings


def test_source_fail_is_never_turned_into_pass():
    c = classify_record(http(status_code=200, business_outcome="ONAYLANDI", expected_result=ACCEPT,
                             test_outcome=OUTCOME_FAIL))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-CONFLICT-SOURCE-OUTCOME",)
    assert c.requires_review


def test_timeout_is_not_called_application_failure():
    c = classify_record(http(transport_error="timeout", test_outcome=OUTCOME_ERROR, error_message="ReadTimeout"))
    assert c.classification == CLASS_TIMEOUT and c.rule_ids == ("H-TIMEOUT",)
    assert any("kök nedeni" in text for text in c.limitations)
    assert "veritabanı" not in c.reason.lower()  # kök neden uydurulmaz


@pytest.mark.parametrize("error", ["connection_error", "transport_error"])
def test_transport_errors(error):
    c = classify_record(http(transport_error=error, test_outcome=OUTCOME_ERROR))
    assert c.classification == CLASS_TRANSPORT_FAILURE and c.rule_ids == ("H-TRANSPORT",)
    assert any("kanıtlamaz" in text for text in c.limitations)


def test_conflicting_transport_and_status_is_inconclusive():
    c = classify_record(http(transport_error="timeout", status_code=200, expected_result=ACCEPT))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-CONFLICT-TRANSPORT-STATUS",)


def test_no_observation_is_inconclusive():
    c = classify_record(http(expected_result=ACCEPT))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("H-NO-OBSERVATION",)


# --- JUnit / Surefire ---
def test_junit_pass_keeps_scope_limitation():
    c = classify_record(junit(OUTCOME_PASS))
    assert c.classification == CLASS_PASS and c.rule_ids == ("J-PASS",)
    assert any("genel olarak hatasız" in text for text in c.limitations)


def test_junit_flaky_pass_carries_warning():
    c = classify_record(junit(OUTCOME_PASS, warnings=("flaky_rerun_passed",)))
    assert c.classification == CLASS_PASS and "flaky_rerun_passed" in c.warnings


def test_junit_skipped_is_not_pass():
    c = classify_record(junit(OUTCOME_SKIPPED))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("J-SKIPPED",) and c.confidence is None
    assert "test_not_executed" in c.warnings


def test_junit_assertion_failure_is_application_failure_with_caveat():
    c = classify_record(junit(OUTCOME_FAIL, exception_type="org.opentest4j.AssertionFailedError",
                              error_message="expected: <ONAYLANDI> but was: <REDDEDILDI>"))
    assert c.classification == CLASS_APPLICATION_FAILURE and c.rule_ids == ("J-ASSERTION",)
    assert c.confidence == "medium"  # assertion başarısızlığı uygulama kusurunun kesin kanıtı değil
    assert any("dışlanamaz" in text for text in c.limitations)
    assert {"test_outcome", "exception_type", "error_message"} <= fields_of(c)


def test_junit_error_with_assertion_type_is_application_failure():
    c = classify_record(junit(OUTCOME_ERROR, exception_type="java.lang.AssertionError"))
    assert c.classification == CLASS_APPLICATION_FAILURE


def test_junit_context_load_failure_is_infrastructure():
    trace = ("java.lang.IllegalStateException: Failed to load ApplicationContext\n"
             "Caused by: org.springframework.beans.factory.BeanCreationException: x\n"
             "Caused by: java.net.ConnectException: Connection refused")
    c = classify_record(junit(OUTCOME_ERROR, exception_type="java.lang.IllegalStateException",
                              error_message="Failed to load ApplicationContext", stack_trace=trace))
    assert c.classification == CLASS_TEST_INFRASTRUCTURE_FAILURE and c.rule_ids == ("J-INFRA",)
    assert c.requires_review and c.confidence == "medium"
    chain = next(e for e in c.evidence if e.field == "exception_chain")
    assert chain.value == ["IllegalStateException", "BeanCreationException", "ConnectException"]


@pytest.mark.parametrize("exc", ["java.lang.NoClassDefFoundError", "com.zaxxer.hikari.pool.HikariPool$PoolInitializationException"])
def test_junit_known_infrastructure_types(exc):
    assert classify_record(junit(OUTCOME_ERROR, exception_type=exc)).classification == CLASS_TEST_INFRASTRUCTURE_FAILURE


def test_junit_timeout_by_type_and_by_message():
    by_type = classify_record(junit(OUTCOME_ERROR, exception_type="java.net.SocketTimeoutException"))
    assert by_type.classification == CLASS_TIMEOUT and by_type.confidence == "high"
    by_message = classify_record(junit(OUTCOME_FAIL, exception_type="org.opentest4j.AssertionFailedError",
                                       error_message="execution timed out after 100 ms"))
    assert by_message.classification == CLASS_TIMEOUT and by_message.rule_ids == ("J-TIMEOUT-MESSAGE",)
    assert by_message.confidence == "low" and by_message.requires_review


def test_junit_timeout_in_cause_chain():
    trace = "java.lang.RuntimeException: x\nCaused by: java.util.concurrent.TimeoutException: y"
    c = classify_record(junit(OUTCOME_ERROR, exception_type="java.lang.RuntimeException", stack_trace=trace))
    assert c.classification == CLASS_TIMEOUT


def test_junit_transport_exception():
    c = classify_record(junit(OUTCOME_ERROR, exception_type="org.springframework.web.client.ResourceAccessException"))
    assert c.classification == CLASS_TRANSPORT_FAILURE and c.requires_review


def test_junit_unrecognized_exception_is_unknown():
    c = classify_record(junit(OUTCOME_ERROR, exception_type="java.lang.NullPointerException"))
    assert c.classification == CLASS_UNKNOWN and c.rule_ids == ("J-ERROR-UNRECOGNIZED",)
    assert c.confidence is None and c.requires_review


def test_junit_error_without_type_is_inconclusive():
    c = classify_record(junit(OUTCOME_ERROR))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("J-ERROR-NO-TYPE",)


def test_junit_unknown_outcome_is_unknown():
    assert classify_record(junit(OUTCOME_UNKNOWN)).classification == CLASS_UNKNOWN


# --- veri kalitesi ---
def test_invalid_data_quality_wins():
    c = classify_record(junit(OUTCOME_PASS, data_quality_status=QUALITY_INVALID))
    assert c.classification == CLASS_INVALID_TEST_DATA and c.rule_ids == ("DQ-INVALID",)


def test_contradictory_source_is_inconclusive():
    c = classify_record(junit(OUTCOME_UNKNOWN, data_quality_status=QUALITY_CONTRADICTORY,
                              warnings=("conflicting_result_elements:failure,skipped",)))
    assert c.classification == CLASS_INCONCLUSIVE and c.rule_ids == ("DQ-CONTRADICTORY",) and c.requires_review


def test_partial_quality_does_not_block_classification():
    c = classify_record(junit(OUTCOME_PASS, data_quality_status=QUALITY_PARTIAL, warnings=("invalid_duration",)))
    assert c.classification == CLASS_PASS


# --- genel sözleşme ---
def test_every_class_is_reachable():
    records = [
        http(status_code=200, business_outcome="ONAYLANDI", expected_result=ACCEPT),
        http(status_code=200, business_outcome="REDDEDILDI", expected_result=ACCEPT),
        http(transport_error="connection_error"),
        http(transport_error="timeout"),
        junit(OUTCOME_ERROR, exception_type="org.springframework.beans.factory.BeanCreationException"),
        junit(OUTCOME_PASS, data_quality_status=QUALITY_INVALID),
        http(status_code=200),
        junit(OUTCOME_ERROR, exception_type="java.lang.NullPointerException"),
    ]
    assert sorted(c.analysis.classification for c in classify_records(records)) == sorted(CLASSES)


def test_classification_never_changes_source_outcome_and_records_version():
    records = [junit(OUTCOME_SKIPPED), http(status_code=200, business_outcome="REDDEDILDI", expected_result=ACCEPT)]
    for before, after in zip(records, classify_records(records)):
        assert after.test_outcome == before.test_outcome and before.analysis is None
        assert after.analysis.classifier_version == CLASSIFIER_VERSION
        assert after.analysis.reason and after.analysis.rule_ids


def test_inconclusive_and_unknown_never_carry_confidence():
    records = [http(status_code=200), junit(OUTCOME_SKIPPED), junit(OUTCOME_ERROR, exception_type="x.YException")]
    for r in classify_records(records):
        assert r.analysis.classification in (CLASS_INCONCLUSIVE, CLASS_UNKNOWN) and r.analysis.confidence is None


def test_evidence_and_reason_never_contain_raw_sensitive_values():
    records = [
        http(status_code=200, business_outcome="REDDEDILDI", expected_result=ACCEPT, test_name=f"kartNo={KART}"),
        http(transport_error="timeout", error_message=f"ReadTimeout /api/auth/kart-okut?kartNo={KART}"),
        junit(OUTCOME_FAIL, exception_type="java.lang.AssertionError",
              error_message=f'govde {{"kartNo": "{KART}", "parmakIzi": "PARMAK-SENTETIK-333"}}'),
        junit(OUTCOME_ERROR, exception_type="java.lang.IllegalStateException",
              error_message="Failed to load ApplicationContext",
              stack_trace=f"Caused by: java.net.ConnectException: jdbc:postgresql://h/db?password={KART}"),
    ]
    text = json.dumps([r.to_dict() for r in classify_records(records)], ensure_ascii=False)
    assert KART not in text and "PARMAK-SENTETIK-333" not in text


def test_classifier_does_not_use_duration():
    """Gecikme (F5'in ekseni) sınıfı değiştirmez."""
    fast = classify_record(http(status_code=200, business_outcome="ONAYLANDI", expected_result=ACCEPT, duration_ms=1.0))
    slow = classify_record(http(status_code=200, business_outcome="ONAYLANDI", expected_result=ACCEPT,
                                duration_ms=90_000.0))
    assert fast == slow
