"""records.py (TestRecord) birim testleri: doğrulama, JSON gidiş-dönüş, maskeleme sınırı, kaynak/analiz ayrımı.

Tüm kişisel ve gizli değerler sentetiktir.
"""

import json
import math

import pytest

from factories import make_failed_result, make_result
from hgs2_lab.records import (
    CLASS_APPLICATION_FAILURE,
    CLASS_INCONCLUSIVE,
    DATASET_FIXTURE,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    QUALITY_PARTIAL,
    SOURCE_JUNIT_XML,
    SOURCE_LAB_RESULT,
    Classification,
    Evidence,
    ExpectedResult,
    RecordError,
    TestRecord,
    make_record_id,
    record_from_raw_result,
)
from hgs2_lab.sanitize import REDACTED

KART, OGR, PARMAK, TOKEN = "KART-SENTETIK-111", "OGR-SENTETIK-222", "PARMAK-SENTETIK-333", "FAKE-TOKEN-444"


def record(**overrides):
    values = dict(record_id="r-test-1", source_type=SOURCE_JUNIT_XML, dataset_kind=DATASET_FIXTURE,
                  test_outcome=OUTCOME_PASS)
    values.update(overrides)
    return TestRecord(**values)


def analysis(**overrides):
    values = dict(classification=CLASS_APPLICATION_FAILURE, rule_ids=("H-BUSINESS-MISMATCH",),
                  reason="Gözlenen yanıt beklentiyi karşılamadı.",
                  evidence=(Evidence("business_outcome", "REDDEDILDI"),), confidence="high")
    values.update(overrides)
    return Classification(**values)


def full_record():
    return record(
        source_type=SOURCE_LAB_RESULT, test_outcome=OUTCOME_FAIL, run_id="run-1", source_file="run-1.csv",
        source_sha256="a" * 64, test_id="run-1#5", test_name="kart#1", suite_name="suite", scenario_id="kart",
        timestamp="2026-10-26T10:00:00+00:00",
        expected_result=ExpectedResult(status_codes=(200,), business_outcomes=("ONAYLANDI",), description="geçerli kart"),
        status_code=200, business_outcome="REDDEDILDI", duration_ms=12.5, exception_type=None,
        error_message=None, stack_trace=None, label="none", label_source="synthetic_plan",
        data_quality_status=QUALITY_PARTIAL, warnings=("duration_missing",), analysis=analysis(),
    )


def test_minimal_record_has_explicit_unknowns():
    r = record()
    data = r.to_dict()
    assert data["expected_result"] is None and data["status_code"] is None and data["duration_ms"] is None
    assert data["analysis"] is None and data["label"] is None and data["warnings"] == []
    assert data["data_quality_status"] == "valid"


def test_json_round_trip_preserves_every_field():
    r = full_record()
    again = TestRecord.from_json(r.to_json())
    assert again == r
    assert again.to_dict() == r.to_dict()
    assert json.loads(r.to_json())["analysis"]["classification"] == CLASS_APPLICATION_FAILURE


def test_from_dict_accepts_missing_optional_fields_and_rejects_unknown_or_missing_required():
    assert TestRecord.from_dict({"record_id": "r-1", "source_type": "junit_xml", "dataset_kind": "fixture",
                                 "test_outcome": "PASS"}) == record(record_id="r-1")
    with pytest.raises(RecordError, match="bilinmeyen"):
        TestRecord.from_dict({**record().to_dict(), "gizli_alan": 1})
    with pytest.raises(RecordError, match="eksik"):
        TestRecord.from_dict({"record_id": "r-1", "source_type": "junit_xml", "dataset_kind": "fixture"})


@pytest.mark.parametrize("bad", ['{"a":', "[]", "null"])
def test_from_json_rejects_malformed_or_non_object(bad):
    with pytest.raises(RecordError):
        TestRecord.from_json(bad)


@pytest.mark.parametrize("duration", [-1, -0.001, math.inf, math.nan, "12", True])
def test_invalid_duration_is_rejected(duration):
    with pytest.raises(RecordError, match="duration_ms"):
        record(duration_ms=duration)


def test_zero_and_integer_durations_are_valid():
    assert record(duration_ms=0).duration_ms == 0.0
    assert isinstance(record(duration_ms=3).duration_ms, float)


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"record_id": "../x"}, "record_id"),
        ({"source_type": "csv"}, "source_type"),
        ({"dataset_kind": "gercek"}, "dataset_kind"),
        ({"test_outcome": "OK"}, "test_outcome"),
        ({"data_quality_status": "iyi"}, "data_quality_status"),
        ({"status_code": 99}, "status_code"),
        ({"status_code": True}, "status_code"),
        ({"transport_error": "dns"}, "transport_error"),
        ({"source_file": "C:\\Users\\x\\rapor.xml"}, "source_file"),
        ({"source_sha256": "ABC"}, "source_sha256"),
        ({"label": "none"}, "label"),
        ({"label": "none", "label_source": "model"}, "label_source"),
        ({"warnings": "tek"}, "warnings"),
        ({"warnings": ("Boşluklu Kod",)}, "warnings"),
        ({"test_name": ""}, "test_name"),
        ({"expected_result": {"status_codes": [200]}}, "expected_result"),
        ({"analysis": "PASS"}, "analysis"),
    ],
)
def test_validation_errors(overrides, match):
    with pytest.raises(RecordError, match=match):
        record(**overrides)


def test_validation_errors_do_not_echo_field_values():
    with pytest.raises(RecordError) as info:
        record(test_outcome=f"kartNo={KART}")
    assert KART not in str(info.value)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"status_codes": (99,)}, "status_codes"),
        ({"status_codes": "200"}, "status_codes"),
        ({"business_outcomes": ("",)}, "business_outcomes"),
        ({"business_outcomes": "ONAYLANDI"}, "business_outcomes"),
    ],
)
def test_expected_result_validation(kwargs, match):
    with pytest.raises(RecordError, match=match):
        ExpectedResult(**kwargs)


def test_expected_result_definedness():
    assert not ExpectedResult().is_defined
    assert ExpectedResult(status_codes=(404,)).is_defined
    assert ExpectedResult(business_outcomes=("REDDEDILDI",)).is_defined


def test_classification_validation():
    with pytest.raises(RecordError, match="classification"):
        analysis(classification="FAILED")
    with pytest.raises(RecordError, match="rule_ids"):
        analysis(rule_ids=())
    with pytest.raises(RecordError, match="confidence"):
        analysis(confidence="0.97")
    with pytest.raises(RecordError, match="confidence null"):
        analysis(classification=CLASS_INCONCLUSIVE, confidence="high")
    with pytest.raises(RecordError, match="evidence"):
        analysis(evidence=({"field": "x"},))
    with pytest.raises(RecordError, match="evidence.value"):
        Evidence("x", object())


def test_masking_boundary_applies_to_text_fields_expected_and_evidence():
    r = record(
        test_name=f"kartOkut[kartNo={KART}]",
        error_message=f'govde {{"ogrenciNo": "{OGR}", "parmakIzi": "{PARMAK}"}}',
        stack_trace=f"java.lang.AssertionError\n\tAuthorization: Bearer {TOKEN}",
        expected_result=ExpectedResult(description=f"ogrenciNo={OGR} reddedilmeli", business_outcomes=("REDDEDILDI",)),
        analysis=analysis(evidence=(Evidence("request", {"kartNo": KART, "deviceId": 3}),
                                    Evidence("error_message", f"parmakIzi={PARMAK}", note=f"kartNo={KART}")),
                          reason=f"kartNo={KART} reddedildi"),
    )
    serialized = r.to_json()
    for secret in (KART, OGR, PARMAK, TOKEN):
        assert secret not in serialized
    assert r.analysis.evidence[0].value == {"kartNo": REDACTED, "deviceId": 3}
    assert TestRecord.from_json(serialized) == r  # maskeleme idempotent: gidiş-dönüş değişmez


def test_with_analysis_keeps_source_outcome():
    r = record(test_outcome=OUTCOME_PASS)
    analysed = r.with_analysis(analysis())
    assert analysed.test_outcome == OUTCOME_PASS  # kaynak sonucu değişmez
    assert analysed.analysis.classification == CLASS_APPLICATION_FAILURE
    assert r.analysis is None  # orijinal kayıt değişmez


def test_make_record_id_is_deterministic_and_valid():
    assert make_record_id("a", 1) == make_record_id("a", 1) != make_record_id("a", 2)
    record(record_id=make_record_id("x"))


def test_record_from_raw_result_maps_http_and_transport_planes():
    ok = record_from_raw_result(make_result(), dataset_kind=DATASET_FIXTURE,
                                expected=ExpectedResult(status_codes=(200,)))
    assert ok.source_type == SOURCE_LAB_RESULT and ok.test_outcome == OUTCOME_PASS
    assert ok.status_code == 200 and ok.transport_error is None and ok.expected_result.status_codes == (200,)
    failed = record_from_raw_result(make_failed_result(), dataset_kind=DATASET_FIXTURE)
    assert failed.test_outcome == OUTCOME_ERROR and failed.transport_error is not None and failed.status_code is None
    assert failed.expected_result is None  # RawResult beklenen sonucu taşımaz; uydurulmaz
    not_ok = record_from_raw_result(make_result(status_code=500, http_ok=False), dataset_kind=DATASET_FIXTURE)
    assert not_ok.test_outcome == OUTCOME_FAIL


def test_record_from_raw_result_masks_url_derived_error_text():
    raw = make_failed_result(error=f"ReadTimeout: /api/auth/kart-okut?kartNo={KART}")
    r = record_from_raw_result(raw, dataset_kind=DATASET_FIXTURE)
    assert KART not in r.to_json()
