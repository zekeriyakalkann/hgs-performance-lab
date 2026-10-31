"""JUnit / Surefire XML test raporu ayrıştırıcısı: her `<testcase>` bir `TestRecord` olur (ağ yok).

Ayrıştırıcı yalnızca raporda yazanı temsil eder; kök neden veya analiz sınıfı belirlemez (bkz. classify.py):

| Rapordaki öğe | `test_outcome` |
|---|---|
| sonuç öğesi yok | PASS (yalnızca `flakyFailure`/`flakyError` varsa PASS + `flaky_rerun_passed` uyarısı) |
| `<failure>` | FAIL |
| `<error>` | ERROR |
| `<skipped>` | SKIPPED |
| birden çok farklı tür (ör. `<failure>` + `<skipped>`) | UNKNOWN, `data_quality_status = contradictory` |

`<failure>`/`<error>` için `type` → `exception_type` (yoksa iz metninin ilk satırından), `message` → `error_message`,
öğe metni → `stack_trace`. Metinler kırpılır ve `TestRecord` kurulurken maskelenir. `time` saniyedir; eksikse
`duration_ms = null` + `duration_missing`, geçersizse `invalid_duration` + `partial`.

Okunmayanlar: `<properties>` (JVM/sistem özellikleri gizli değer içerebilir), `<system-out>`, `<system-err>`
(test sırasında yakalanan log çıktısı). Bu bölümlerin içeriği kayda veya çıktıya alınmaz; yalnızca kaç tane
bulunduğu suite özetinde (`ignored_sections`) bildirilir. Rapor uygulamanın tüm loglarını içermez; ayrı log
dosyaları bu ayrıştırıcının kapsamı dışındadır.

Tek istisna, açık senaryo kimliğidir: **testcase** düzeyindeki `<properties>` içinde adı tam olarak
`hgs2_lab.scenario_id` olan özellik (`<property name="hgs2_lab.scenario_id" value="kart-pasif-cihaz"/>`)
`scenario_id` olarak okunur. Bu ad Lab'in sözleşmesidir, JUnit standardının parçası değildir. pytest 9.1.1
`record_property` bu yapıyı ürettiği yerel olarak doğrulandı; Maven Surefire/JUnit 5 için testcase düzeyinde özellik
üretimi doğrulanmadı. Suite düzeyindeki özellikler ve başka adlı özellikler okunmaz. Kimlik test, sınıf veya suite
adından türetilmez.

Güvenlik: dosya boyutu sınırlıdır; DOCTYPE ve varlık (entity) bildirimi içeren XML ayrıştırılmadan reddedilir
(harici varlık çözümlemesi ve varlık genişletme saldırıları yok); dosya içeriği hiçbir zaman çalıştırılmaz ve
hiçbir dış kaynağa bağlanılmaz. Dosya düzeyindeki her sorun `JUnitReportError` (kod + mesaj) olarak bildirilir;
toplu ayrıştırmada (`parse_junit_reports`) hatalı dosya listelenir, diğer dosyalar işlenmeye devam eder.
"""

from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.parsers import expat

from .records import (
    DATASET_KINDS,
    DATASET_UNKNOWN,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_PASS,
    OUTCOME_SKIPPED,
    OUTCOME_UNKNOWN,
    QUALITY_CONTRADICTORY,
    QUALITY_PARTIAL,
    QUALITY_VALID,
    SCENARIO_ID_RE,
    SOURCE_JUNIT_XML,
    TestRecord,
    make_record_id,
)
from .sanitize import sanitize_text

MAX_REPORT_BYTES = 32 * 1024 * 1024
MAX_MESSAGE_CHARS = 4_000
MAX_TRACE_LINES = 200
MAX_TRACE_CHARS = 32_000

ERROR_NOT_FOUND = "not_found"
ERROR_UNREADABLE = "unreadable"
ERROR_EMPTY = "empty"
ERROR_TOO_LARGE = "too_large"
ERROR_UNSAFE_XML = "unsafe_xml"
ERROR_MALFORMED_XML = "malformed_xml"
ERROR_UNSUPPORTED_FORMAT = "unsupported_format"

_RESULT_KINDS = {"failure": OUTCOME_FAIL, "error": OUTCOME_ERROR, "skipped": OUTCOME_SKIPPED}
_FLAKY_TAGS = frozenset({"flakyFailure", "flakyError"})
_COUNT_ATTRS = ("tests", "failures", "errors", "skipped")
_IGNORED_SECTIONS = ("properties", "system-out", "system-err")
# Lab'in açık senaryo kimliği sözleşmesi: testcase düzeyindeki bu adlı özellik (bkz. modül açıklaması).
SCENARIO_ID_PROPERTY = "hgs2_lab.scenario_id"
_EXCEPTION_LINE_RE = re.compile(
    r"^\s*(?P<type>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*(?:Exception|Error|Throwable|Failure|Failed))(?::|\s*$)"
)
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


class JUnitReportError(Exception):
    """Dosya düzeyinde ayrıştırma hatası. Mesaj dosya içeriğinden alıntı içermez."""

    def __init__(self, code: str, message: str, source_file: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source_file = source_file

    def to_dict(self) -> dict[str, Any]:
        return {"source_file": self.source_file, "code": self.code, "message": self.message}


class _UnsafeXml(Exception):
    pass


@dataclass(frozen=True)
class SuiteSummary:
    """Bir `<testsuite>`: raporun beyan ettiği sayılar ile ayrıştırılan kayıtlardan sayılanlar."""

    name: str | None
    timestamp: str | None
    time_ms: float | None
    declared: dict[str, int | None]
    observed: dict[str, int]
    warnings: tuple[str, ...]
    ignored_sections: dict[str, int]  # içeriği okunmayan bölümlerin sayısı (suite ve testcase düzeyi birlikte)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "timestamp": self.timestamp, "time_ms": self.time_ms,
                "declared": dict(self.declared), "observed": dict(self.observed), "warnings": list(self.warnings),
                "ignored_sections": dict(self.ignored_sections)}


@dataclass(frozen=True)
class JUnitReport:
    source_file: str
    source_sha256: str
    suites: tuple[SuiteSummary, ...]
    records: tuple[TestRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"source_file": self.source_file, "source_sha256": self.source_sha256,
                "suites": [s.to_dict() for s in self.suites], "records": len(self.records)}


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _reject_unsafe(data: bytes, name: str) -> None:
    """DOCTYPE/varlık bildirimlerini ve bozuk XML'i ElementTree'ye vermeden önce yakalar."""

    def unsafe(*_args: Any) -> None:
        raise _UnsafeXml

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = unsafe
    parser.EntityDeclHandler = unsafe
    parser.UnparsedEntityDeclHandler = unsafe
    parser.ExternalEntityRefHandler = unsafe
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(data, True)
    except _UnsafeXml:
        raise JUnitReportError(ERROR_UNSAFE_XML, "DOCTYPE veya varlık (entity) bildirimi içeren XML reddedildi",
                               name) from None
    except expat.ExpatError as exc:
        raise JUnitReportError(ERROR_MALFORMED_XML, f"XML bozuk ({expat.ErrorString(exc.code)}; satır {exc.lineno}, "
                                                    f"sütun {exc.offset})", name) from None


def _seconds_to_ms(text: str | None) -> tuple[float | None, str | None]:
    """(süre ms, uyarı kodu). Eksikse `duration_missing`, geçersizse `invalid_duration`."""
    if text is None or not text.strip():
        return None, "duration_missing"
    if "," in text:  # "1,234" (binlik) ile "0,437" (ondalık virgül) ayırt edilemez: tahmin edilmez
        return None, "invalid_duration"
    try:
        value = float(text.strip())
    except ValueError:
        return None, "invalid_duration"
    if not math.isfinite(value) or value < 0:
        return None, "invalid_duration"
    return round(value * 1000.0, 6), None


def _truncate(text: str | None, limit: int, code: str, warnings: list[str]) -> str | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) > limit:
        warnings.append(code)
        return text[:limit]
    return text


def _trace(text: str | None, warnings: list[str]) -> str | None:
    if text is None or not text.strip():
        return None
    lines = text.strip().splitlines()
    if len(lines) > MAX_TRACE_LINES:
        warnings.append("stack_trace_truncated")
        lines = lines[:MAX_TRACE_LINES]
    joined = "\n".join(line.rstrip() for line in lines)
    if len(joined) > MAX_TRACE_CHARS:
        if "stack_trace_truncated" not in warnings:
            warnings.append("stack_trace_truncated")
        joined = joined[:MAX_TRACE_CHARS]
    return joined


def _scenario_id(case: ET.Element, warnings: list[str]) -> str | None:
    """Testcase düzeyindeki `<properties>` içinde yalnızca `SCENARIO_ID_PROPERTY` adlı özelliği okur.

    Değer `value` özniteliğinden (yoksa öğe metninden) alınır. Başka hiçbir özellik okunmaz. Değer yoksa None;
    geçersizse None + `scenario_id_invalid`; farklı değerler varsa hiçbiri seçilmez: None + `scenario_id_conflict`.
    Test, sınıf veya suite adından kimlik türetilmez.
    """
    values = []
    for group in case:
        if _local(group.tag) != "properties":
            continue
        for prop in group:
            if _local(prop.tag) == "property" and prop.get("name") == SCENARIO_ID_PROPERTY:
                raw = prop.get("value")
                values.append((raw if raw is not None else (prop.text or "")).strip())
    if not values:
        return None
    if len(set(values)) > 1:
        warnings.append("scenario_id_conflict")
        return None
    if not SCENARIO_ID_RE.match(values[0]):
        warnings.append("scenario_id_invalid")
        return None
    if len(values) > 1:
        warnings.append("scenario_id_repeated")
    return values[0]


def _testcase_record(case: ET.Element, *, suite: ET.Element, suite_index: int, case_index: int, source_file: str,
                     source_sha256: str, dataset_kind: str, timestamp: str | None) -> TestRecord:
    warnings: list[str] = []
    quality = QUALITY_VALID
    name = case.get("name") or None
    classname = case.get("classname") or None
    if name is None:
        warnings.append("missing_test_name")
        quality = QUALITY_PARTIAL
    duration_ms, duration_warning = _seconds_to_ms(case.get("time"))
    if duration_warning:
        warnings.append(duration_warning)
        if duration_warning == "invalid_duration":
            quality = QUALITY_PARTIAL

    children = [(_local(child.tag), child) for child in case]
    results = [(tag, child) for tag, child in children if tag in _RESULT_KINDS]
    kinds = sorted({tag for tag, _ in results})
    exception_type = message = trace = None
    if not results:
        outcome = OUTCOME_PASS
        if any(tag in _FLAKY_TAGS for tag, _ in children):
            warnings.append("flaky_rerun_passed")
    elif len(kinds) > 1:
        outcome = OUTCOME_UNKNOWN
        quality = QUALITY_CONTRADICTORY
        warnings.append(f"conflicting_result_elements:{','.join(kinds)}")
    else:
        outcome = _RESULT_KINDS[kinds[0]]
        if len(results) > 1:
            warnings.append(f"multiple_result_elements:{kinds[0]}")
    if results and outcome != OUTCOME_UNKNOWN:
        element = results[0][1]
        message = _truncate(element.get("message"), MAX_MESSAGE_CHARS, "error_message_truncated", warnings)
        trace = _trace(element.text, warnings)
        if outcome in (OUTCOME_FAIL, OUTCOME_ERROR):
            exception_type = (element.get("type") or "").strip() or None
            if exception_type is None and trace:
                match = _EXCEPTION_LINE_RE.match(trace.splitlines()[0])
                if match:
                    exception_type = match.group("type")
                    warnings.append("exception_type_from_trace")
    if any(tag in ("rerunFailure", "rerunError") for tag, _ in children):
        warnings.append("rerun_failed")
    scenario_id = _scenario_id(case, warnings)

    test_id = f"{classname}#{name}" if classname and name else (name or classname)
    return TestRecord(
        record_id=make_record_id(SOURCE_JUNIT_XML, source_sha256, suite_index, case_index),
        source_type=SOURCE_JUNIT_XML,
        dataset_kind=dataset_kind,
        test_outcome=outcome,
        run_id="junit-" + source_sha256[:16],
        source_file=source_file,
        source_sha256=source_sha256,
        test_id=test_id,
        test_name=name,
        suite_name=suite.get("name") or classname,
        scenario_id=scenario_id,
        timestamp=timestamp,
        duration_ms=duration_ms,
        exception_type=exception_type,
        error_message=message,
        stack_trace=trace,
        data_quality_status=quality,
        warnings=tuple(warnings),
    )


def _declared_counts(suite: ET.Element, warnings: list[str]) -> dict[str, int | None]:
    declared: dict[str, int | None] = {}
    for attr in _COUNT_ATTRS:
        raw = suite.get(attr)
        if raw is None:
            declared[attr] = None
            continue
        try:
            value = int(raw.strip())
        except ValueError:
            value = -1
        if value < 0:
            warnings.append(f"invalid_declared_count:{attr}")
            declared[attr] = None
        else:
            declared[attr] = value
    return declared


def _suite_timestamp(suite: ET.Element, warnings: list[str]) -> str | None:
    raw = (suite.get("timestamp") or "").strip()
    if not raw:
        return None
    if not _TIMESTAMP_RE.match(raw):
        warnings.append("invalid_timestamp")
        return None
    return raw


def parse_junit_bytes(data: bytes, *, source_file: str, dataset_kind: str = DATASET_UNKNOWN) -> JUnitReport:
    """Bellekteki rapor baytlarını ayrıştırır. `source_file` yalnızca ad olarak kayda yazılır."""
    if dataset_kind not in DATASET_KINDS:
        raise ValueError(f"dataset_kind şu değerlerden biri olmalı: {', '.join(sorted(DATASET_KINDS))}")
    name = Path(source_file).name
    if len(data) > MAX_REPORT_BYTES:
        raise JUnitReportError(ERROR_TOO_LARGE, f"Rapor {MAX_REPORT_BYTES} bayttan büyük", name)
    if not data.strip():
        raise JUnitReportError(ERROR_EMPTY, "Rapor boş", name)
    _reject_unsafe(data, name)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:  # _reject_unsafe'ten sonra beklenmez; yine de kontrollü bildirilir
        raise JUnitReportError(ERROR_MALFORMED_XML, f"XML bozuk (konum {exc.position})", name) from None
    root_tag = _local(root.tag)
    if root_tag not in ("testsuites", "testsuite"):
        raise JUnitReportError(ERROR_UNSUPPORTED_FORMAT, "Kök öğe <testsuites> veya <testsuite> olmalı", name)

    sha = hashlib.sha256(data).hexdigest()
    suites, records = [], []
    for suite_index, suite in enumerate(el for el in root.iter() if _local(el.tag) == "testsuite"):
        suite_warnings: list[str] = []
        timestamp = _suite_timestamp(suite, suite_warnings)
        declared = _declared_counts(suite, suite_warnings)
        time_ms, time_warning = _seconds_to_ms(suite.get("time"))
        if time_warning == "invalid_duration":
            suite_warnings.append("invalid_suite_time")
        cases = [child for child in suite if _local(child.tag) == "testcase"]
        suite_records = [
            _testcase_record(case, suite=suite, suite_index=suite_index, case_index=case_index, source_file=name,
                             source_sha256=sha, dataset_kind=dataset_kind, timestamp=timestamp)
            for case_index, case in enumerate(cases)
        ]
        observed = {
            "tests": len(suite_records),
            "failures": sum(r.test_outcome == OUTCOME_FAIL for r in suite_records),
            "errors": sum(r.test_outcome == OUTCOME_ERROR for r in suite_records),
            "skipped": sum(r.test_outcome == OUTCOME_SKIPPED for r in suite_records),
        }
        nested = any(_local(child.tag) == "testsuite" for child in suite)
        ignored = {section: sum(_local(el.tag) == section for el in (*suite, *(x for c in cases for x in c)))
                   for section in _IGNORED_SECTIONS}
        for attr in _COUNT_ATTRS:
            # İç içe suite'lerde üst düzey sayılar alt suite'leri de kapsar; yalnızca yaprak suite'ler karşılaştırılır.
            if not nested and declared[attr] is not None and declared[attr] != observed[attr]:
                suite_warnings.append(f"declared_count_mismatch:{attr}")
        suite_name = suite.get("name")
        suites.append(SuiteSummary(name=sanitize_text(suite_name) if suite_name else None, timestamp=timestamp,
                                   time_ms=time_ms, declared=declared, observed=observed,
                                   warnings=tuple(suite_warnings), ignored_sections=ignored))
        records.extend(suite_records)
    if not suites:
        raise JUnitReportError(ERROR_UNSUPPORTED_FORMAT, "Raporda <testsuite> öğesi yok", name)
    return JUnitReport(source_file=name, source_sha256=sha, suites=tuple(suites), records=tuple(records))


def parse_junit_report(path: str | Path, *, dataset_kind: str = DATASET_UNKNOWN) -> JUnitReport:
    """Rapor dosyasını okur ve ayrıştırır. Dosya düzeyindeki sorunlar `JUnitReportError` olarak fırlatılır."""
    path = Path(path)
    name = path.name
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        raise JUnitReportError(ERROR_NOT_FOUND, "Rapor dosyası bulunamadı", name) from None
    except OSError as exc:
        raise JUnitReportError(ERROR_UNREADABLE, f"Rapor dosyası okunamadı ({type(exc).__name__})", name) from None
    if not path.is_file():
        raise JUnitReportError(ERROR_UNREADABLE, "Rapor yolu bir dosya değil", name)
    if size > MAX_REPORT_BYTES:
        raise JUnitReportError(ERROR_TOO_LARGE, f"Rapor {MAX_REPORT_BYTES} bayttan büyük", name)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise JUnitReportError(ERROR_UNREADABLE, f"Rapor dosyası okunamadı ({type(exc).__name__})", name) from None
    return parse_junit_bytes(data, source_file=name, dataset_kind=dataset_kind)


def parse_junit_reports(
    paths: Iterable[str | Path], *, dataset_kind: str = DATASET_UNKNOWN
) -> tuple[list[JUnitReport], list[JUnitReportError]]:
    """Birden çok raporu ayrıştırır; hatalı dosyalar işlemi durdurmaz, hatalar ayrı listede döner."""
    reports: list[JUnitReport] = []
    errors: list[JUnitReportError] = []
    for path in paths:
        try:
            reports.append(parse_junit_report(path, dataset_kind=dataset_kind))
        except JUnitReportError as exc:
            errors.append(exc)
    return reports, errors
