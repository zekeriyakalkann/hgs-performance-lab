"""junit_report.py birim testleri: sentetik JUnit/Surefire fikstürleri (tests/fixtures/junit), güvenli XML işleme.

Gerçek HGS2 raporu kullanılmaz; fikstürlerdeki tüm hassas değerler sentetiktir.
"""

import json
from pathlib import Path

import pytest

from hgs2_lab import junit_report
from hgs2_lab.junit_report import (
    ERROR_EMPTY,
    ERROR_MALFORMED_XML,
    ERROR_NOT_FOUND,
    ERROR_TOO_LARGE,
    ERROR_UNREADABLE,
    ERROR_UNSAFE_XML,
    ERROR_UNSUPPORTED_FORMAT,
    JUnitReportError,
    parse_junit_bytes,
    parse_junit_report,
    parse_junit_reports,
)
from hgs2_lab.records import (
    DATASET_FIXTURE,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_SKIPPED,
    OUTCOME_UNKNOWN,
    QUALITY_CONTRADICTORY,
    QUALITY_PARTIAL,
    QUALITY_VALID,
    SOURCE_JUNIT_XML,
)

FIXTURES = Path(__file__).parent / "fixtures" / "junit"
SYNTHETIC_SECRETS = ("KART-SENTETIK-111", "OGR-SENTETIK-222", "PARMAK-SENTETIK-333", "FAKE-TOKEN-444",
                     "FAKE-PASS-555", "FAKE-COOKIE-666", "FAKE-DB-PASS-777", "FAKE-PROP-PASS-999",
                     "FAKE-SYSOUT-LINE", "FAKE-SYSERR-LINE", "FakeUser")


def parse(name):
    return parse_junit_report(FIXTURES / name, dataset_kind=DATASET_FIXTURE)


def by_name(report):
    return {r.test_name: r for r in report.records}


def test_all_pass_report():
    report = parse("all-pass.xml")
    assert report.source_file == "all-pass.xml" and len(report.source_sha256) == 64
    assert [r.test_outcome for r in report.records] == [OUTCOME_PASS, OUTCOME_PASS]
    first = report.records[0]
    assert first.source_type == SOURCE_JUNIT_XML and first.dataset_kind == DATASET_FIXTURE
    assert first.test_id == "com.example.lab.AuthFlowTests#kartOkutOnaylanir"
    assert first.suite_name == "com.example.lab.AuthFlowTests"
    assert first.duration_ms == 437.0 and report.records[1].duration_ms == 13.0
    assert first.timestamp == "2026-10-26T10:00:00"
    assert first.exception_type is None and first.error_message is None and first.stack_trace is None
    assert first.data_quality_status == QUALITY_VALID and first.warnings == ()
    suite = report.suites[0]
    assert suite.declared == {"tests": 2, "failures": 0, "errors": 0, "skipped": 0} == suite.observed
    assert suite.time_ms == 1250.0 and suite.warnings == ()


def test_properties_and_system_output_are_counted_but_never_read():
    report = parse("all-pass.xml")
    assert report.suites[0].ignored_sections == {"properties": 1, "system-out": 1, "system-err": 1}
    serialized = json.dumps([r.to_dict() for r in report.records] + [report.to_dict()], ensure_ascii=False)
    for secret in ("FAKE-PROP-PASS-999", "FakeUser", "FAKE-SYSOUT-LINE", "FAKE-SYSERR-LINE"):
        assert secret not in serialized


def test_assertion_failure_keeps_type_message_and_trace():
    r = parse("failure.xml").records[0]
    assert r.test_outcome == OUTCOME_FAIL
    assert r.exception_type == "org.opentest4j.AssertionFailedError"
    assert r.error_message == "expected: <ONAYLANDI> but was: <REDDEDILDI>"
    assert r.stack_trace.splitlines()[0].startswith("org.opentest4j.AssertionFailedError")
    assert "AuthFlowTests.java:42" in r.stack_trace
    assert r.duration_ms == 120.0


def test_error_keeps_cause_chain_and_masks_connection_string():
    r = parse("error-context.xml").records[0]
    assert r.test_outcome == OUTCOME_ERROR and r.exception_type == "java.lang.IllegalStateException"
    assert "Caused by: org.springframework.beans.factory.BeanCreationException" in r.stack_trace
    assert "Caused by: java.net.ConnectException" in r.stack_trace
    assert "FAKE-DB-PASS-777" not in r.to_json()


def test_skipped_is_not_pass():
    r = parse("skipped.xml").records[0]
    assert r.test_outcome == OUTCOME_SKIPPED and r.error_message == "Donanım gerektirir; devre dışı"
    assert r.exception_type is None


def test_multiple_suites_and_empty_suite():
    report = parse("multi-suite.xml")
    assert [s.name for s in report.suites] == ["com.example.lab.UserTests", "com.example.lab.LogTests",
                                              "com.example.lab.EmptyTests"]
    assert [s.observed["tests"] for s in report.suites] == [2, 2, 0]
    records = by_name(report)
    assert records["listele"].test_outcome == OUTCOME_PASS
    assert records["uzakServisYavas"].exception_type == "java.net.SocketTimeoutException"
    assert records["uzakServisYavas"].duration_ms == 5002.0
    assert records["logOku"].test_outcome == OUTCOME_ERROR and records["logOku"].exception_type is None
    assert records["logOku"].error_message is None and records["logOku"].stack_trace is None
    assert len({r.record_id for r in report.records}) == 4  # benzersiz kimlik


def test_empty_suite_yields_no_records():
    report = parse("empty-suite.xml")
    assert report.records == () and report.suites[0].observed == {"tests": 0, "failures": 0, "errors": 0,
                                                                  "skipped": 0}


def test_missing_optional_fields_are_null_not_invented():
    records = parse("optional-missing.xml").records
    no_time, no_name, no_class = records
    assert no_time.duration_ms is None and "duration_missing" in no_time.warnings
    assert no_time.data_quality_status == QUALITY_VALID  # eksik isteğe bağlı alan kaliteyi bozmaz
    assert no_name.test_name is None and "missing_test_name" in no_name.warnings
    assert no_name.data_quality_status == QUALITY_PARTIAL
    assert no_class.test_id == "sinifAdiYok" and no_class.suite_name is None and no_class.timestamp is None
    assert no_class.exception_type == "java.lang.AssertionError"  # izin ilk satırından
    assert "exception_type_from_trace" in no_class.warnings
    assert no_class.error_message is None  # message özniteliği yok; uydurulmaz


def test_conflicting_and_invalid_values_are_flagged():
    report = parse("conflicting.xml")
    records = by_name(report)
    conflict = records["hemFailureHemSkipped"]
    assert conflict.test_outcome == OUTCOME_UNKNOWN and conflict.data_quality_status == QUALITY_CONTRADICTORY
    assert "conflicting_result_elements:failure,skipped" in conflict.warnings
    for name in ("negatifSure", "virgulluSure", "sayiOlmayanSure"):
        assert records[name].duration_ms is None and "invalid_duration" in records[name].warnings
        assert records[name].data_quality_status == QUALITY_PARTIAL
    assert records["ikiFailure"].test_outcome == OUTCOME_FAIL and records["ikiFailure"].error_message == "ilk"
    assert "multiple_result_elements:failure" in records["ikiFailure"].warnings
    assert records["tekrarlaGecti"].test_outcome == OUTCOME_PASS
    assert "flaky_rerun_passed" in records["tekrarlaGecti"].warnings
    suite = report.suites[0]
    assert suite.timestamp is None and suite.time_ms is None
    assert set(suite.warnings) == {"invalid_timestamp", "invalid_declared_count:failures", "invalid_suite_time",
                                   "declared_count_mismatch:tests"}


def test_sensitive_values_are_masked_in_records():
    report = parse("sensitive.xml")
    serialized = json.dumps([r.to_dict() for r in report.records], ensure_ascii=False)
    for secret in SYNTHETIC_SECRETS:
        assert secret not in serialized
    first = report.records[0]
    assert first.test_outcome == OUTCOME_FAIL and "REDDEDILDI" in first.error_message  # anlam korunur
    assert "SensitiveTests.java:30" in first.stack_trace


@pytest.mark.parametrize(
    "name, code",
    [
        ("empty.xml", ERROR_EMPTY),
        ("malformed.xml", ERROR_MALFORMED_XML),
        ("xxe.xml", ERROR_UNSAFE_XML),
        ("not-junit.xml", ERROR_UNSUPPORTED_FORMAT),
        ("yok.xml", ERROR_NOT_FOUND),
    ],
)
def test_file_level_errors(name, code):
    with pytest.raises(JUnitReportError) as info:
        parse(name)
    assert info.value.code == code and info.value.source_file == name
    assert str(FIXTURES) not in info.value.message  # yerel yol mesaja yazılmaz


def test_directory_path_is_rejected(tmp_path):
    with pytest.raises(JUnitReportError) as info:
        parse_junit_report(tmp_path)
    assert info.value.code == ERROR_UNREADABLE


@pytest.mark.parametrize(
    "data",
    [
        b'<?xml version="1.0"?><!DOCTYPE t [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><testsuite name="&b;"/>',
        b'<?xml version="1.0"?><!DOCTYPE testsuite SYSTEM "http://example.invalid/x.dtd"><testsuite/>',
        b'<?xml version="1.0"?><!DOCTYPE t [<!ENTITY % p SYSTEM "file:///etc/passwd"> %p;]><testsuite/>',
    ],
)
def test_entity_expansion_and_external_dtd_are_rejected(data):
    with pytest.raises(JUnitReportError) as info:
        parse_junit_bytes(data, source_file="x.xml")
    assert info.value.code == ERROR_UNSAFE_XML


def test_malformed_error_does_not_quote_content():
    with pytest.raises(JUnitReportError) as info:
        parse_junit_bytes(b"<testsuite><testcase name='kartNo=KART-SENTETIK-111'>", source_file="x.xml")
    assert info.value.code == ERROR_MALFORMED_XML and "KART-SENTETIK-111" not in info.value.message


def test_size_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(junit_report, "MAX_REPORT_BYTES", 100)
    path = tmp_path / "big.xml"
    path.write_bytes(b"<testsuite>" + b" " * 200 + b"</testsuite>")
    with pytest.raises(JUnitReportError) as info:
        parse_junit_report(path)
    assert info.value.code == ERROR_TOO_LARGE
    with pytest.raises(JUnitReportError):
        parse_junit_bytes(path.read_bytes(), source_file="big.xml")


def test_long_message_and_trace_are_truncated_with_warning():
    message = "x" * (junit_report.MAX_MESSAGE_CHARS + 50)
    trace = "\n".join(f"\tat a.B.c(B.java:{i})" for i in range(junit_report.MAX_TRACE_LINES + 20))
    data = (f'<testsuite name="s"><testcase name="t" time="0.1"><failure message="{message}" '
            f'type="java.lang.AssertionError">{trace}</failure></testcase></testsuite>').encode()
    r = parse_junit_bytes(data, source_file="long.xml").records[0]
    assert len(r.error_message) == junit_report.MAX_MESSAGE_CHARS
    assert len(r.stack_trace.splitlines()) == junit_report.MAX_TRACE_LINES
    assert {"error_message_truncated", "stack_trace_truncated"} <= set(r.warnings)


def test_large_but_reasonable_report():
    cases = "".join(
        f'<testcase name="t{i}" classname="c.Large" time="0.001">'
        + ('<failure message="m" type="java.lang.AssertionError">trace</failure>' if i % 10 == 0 else "")
        + "</testcase>"
        for i in range(5000)
    )
    data = f'<testsuite name="c.Large" tests="5000" failures="500">{cases}</testsuite>'.encode()
    report = parse_junit_bytes(data, source_file="large.xml")
    assert len(report.records) == 5000
    assert report.suites[0].observed["failures"] == 500 and report.suites[0].warnings == ()


def test_namespaced_and_utf16_reports():
    data = ('<?xml version="1.0" encoding="UTF-16"?><testsuite xmlns="urn:x" name="çğü"><testcase name="ışık" '
            'time="0.5"/></testsuite>').encode("utf-16")
    report = parse_junit_bytes(data, source_file="u16.xml")
    assert report.records[0].test_name == "ışık" and report.records[0].duration_ms == 500.0


def test_parse_is_deterministic():
    assert parse("multi-suite.xml") == parse("multi-suite.xml")


def test_batch_parsing_continues_after_bad_files():
    names = ["all-pass.xml", "malformed.xml", "yok.xml", "failure.xml", "xxe.xml"]
    reports, errors = parse_junit_reports([FIXTURES / n for n in names], dataset_kind=DATASET_FIXTURE)
    assert [r.source_file for r in reports] == ["all-pass.xml", "failure.xml"]
    assert [(e.source_file, e.code) for e in errors] == [("malformed.xml", ERROR_MALFORMED_XML),
                                                        ("yok.xml", ERROR_NOT_FOUND),
                                                        ("xxe.xml", ERROR_UNSAFE_XML)]


def test_invalid_dataset_kind_is_rejected():
    with pytest.raises(ValueError, match="dataset_kind"):
        parse_junit_bytes(b"<testsuite/>", source_file="x.xml", dataset_kind="gercek")
