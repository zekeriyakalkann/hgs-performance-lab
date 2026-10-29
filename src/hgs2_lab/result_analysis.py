"""Kaydedilmiş bir Lab çalıştırmasının (`run` / `synthetic run`) test sonucu analizi (ağ yok).

Akış: sonuç dosyaları (reader.load_run) + metadata'daki yanıt ayrıştırma özetleri (`response_parsing`) + beklenti
dosyası → `TestRecord` (records.record_from_raw_result) → N4 sınıflandırıcı (classify.py) → JSON belge.

Beklenen sonuç ölçüm kayıtlarında yoktur ve uydurulmaz. Beklenti dosyası iki biçimde olabilir:

* `expectations_version: 2` — beklenti sözleşmesi (expectations.py): sürümlü beklentiler, doğrulama durumu, kapsam ve
  kanıt referansları. Kayıt yalnızca `scenario_id` ile birebir eşleştirilir. Eşleşme yoksa, birden fazla etkin
  beklenti varsa (çelişki) veya yalnızca DEPRECATED beklenti varsa kayda beklenti bağlanmaz ve durum
  `expectation_not_found` / `expectation_conflict` / `expectation_deprecated_only` uyarısıyla bildirilir; başka bir
  kaynağa (ör. senaryonun expected_status listesine) geri düşülmez.
* `expectations_version: 1` — eski biçim (doğrulama durumu ve kanıt yok):

      {"expectations_version": 1,
       "scenarios": {"kart-pasif-cihaz": {"status_codes": [200], "business_outcomes": ["REDDEDILDI"],
                                          "description": "pasif cihazda kart reddedilmeli"}}}

  Bu biçimde ve hiç dosya verilmediğinde, dosyada olmayan senaryolar için senaryonun açıkça yazılmış
  `expected_status` listesi (metadata) kullanılır; o da yoksa `expected_result = null` (→ INCONCLUSIVE).
  Bu beklentilerin doğrulama durumu bilinmez (`provenance.verification_status = null`).

Isınma istekleri sınıflandırılmaz (yalnızca sayılır). Metadata'da `response_parsing` yoksa (bu özellikten önce
yazılmış dosyalar) kayıtlar `response_parsing_unavailable` uyarısı taşır; özet sonuç kaydıyla tutarsızsa kayıt
`invalid` işaretlenir (→ INVALID_TEST_DATA).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ._validate import reject_unknown_keys
from .classify import build_classification_document
from .expectations import MATCH_MATCHED, ExpectationRegistry, ExpectationsError, parse_registry
from .models import DATASET_SYNTHETIC as METADATA_SYNTHETIC
from .reader import RunData
from .records import (
    DATASET_KINDS,
    DATASET_SYNTHETIC,
    DATASET_UNKNOWN,
    EXPECTATION_SOURCE_FILE_V1,
    EXPECTATION_SOURCE_SCENARIO,
    QUALITY_INVALID,
    ExpectationProvenance,
    ExpectedResult,
    RecordError,
    TestRecord,
    record_from_raw_result,
)
from .response_parser import ParsedResponse

EXPECTATIONS_VERSION = 1  # eski biçim; sözleşme biçimi expectations.EXPECTATIONS_VERSION (2)

Expectations = Mapping[str, ExpectedResult] | ExpectationRegistry

__all__ = ["ExpectationsError", "build_run_document", "load_expectations", "parse_expectations", "records_from_run",
           "resolve_dataset_kind"]


def parse_expectations(data: Any) -> dict[str, ExpectedResult]:
    """Eski (sürüm 1) beklenti dosyası: senaryo → beklenti. Doğrulama durumu taşımaz."""
    if not isinstance(data, dict):
        raise ExpectationsError("Beklenti dosyasının kökü nesne olmalı")
    reject_unknown_keys(data, {"expectations_version", "scenarios"}, ExpectationsError, "Beklenti dosyası")
    if data.get("expectations_version") != EXPECTATIONS_VERSION or isinstance(data.get("expectations_version"), bool):
        raise ExpectationsError(f"expectations_version {EXPECTATIONS_VERSION} olmalı")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        raise ExpectationsError("scenarios boş olmayan bir nesne olmalı")
    provenance = ExpectationProvenance(source=EXPECTATION_SOURCE_FILE_V1)
    out: dict[str, ExpectedResult] = {}
    for name, spec in scenarios.items():
        if not isinstance(spec, dict):
            raise ExpectationsError(f"scenarios.{name} nesne olmalı")
        reject_unknown_keys(spec, {"status_codes", "business_outcomes", "description"}, ExpectationsError,
                            f"scenarios.{name}")
        for key in ("status_codes", "business_outcomes"):
            if key in spec and not isinstance(spec[key], list):
                raise ExpectationsError(f"scenarios.{name}.{key} liste olmalı")
        try:
            expected = ExpectedResult(status_codes=tuple(spec.get("status_codes", ())),
                                      business_outcomes=tuple(spec.get("business_outcomes", ())),
                                      description=spec.get("description"), provenance=provenance)
        except RecordError as exc:
            raise ExpectationsError(f"scenarios.{name}: {exc}") from None
        if not expected.is_defined:
            raise ExpectationsError(f"scenarios.{name}: en az bir status_codes veya business_outcomes değeri gerekli")
        out[name] = expected
    return out


def load_expectations(path: str | Path) -> tuple[Expectations, dict[str, Any]]:
    """Beklenti dosyasını okur; sürüme göre eski biçim (dict) ya da sözleşme registry'si döner.

    İkinci değer kaynak bilgisidir: dosya adı (yol değil), SHA-256, sürüm; registry için özet.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ExpectationsError(f"Beklenti dosyası bulunamadı: {path.name}") from None
    except OSError as exc:
        raise ExpectationsError(f"Beklenti dosyası okunamadı: {path.name} ({type(exc).__name__})") from None
    if not raw.strip():
        raise ExpectationsError(f"Beklenti dosyası boş: {path.name}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExpectationsError(f"Beklenti dosyası geçerli UTF-8 JSON değil: {path.name}") from None
    source = {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
    version = data.get("expectations_version") if isinstance(data, dict) else None
    if version == 2 and not isinstance(version, bool):
        registry = parse_registry(data, source=source)
        return registry, {**source, "expectations_version": 2, "registry": registry.summary()}
    return parse_expectations(data), {**source, "expectations_version": EXPECTATIONS_VERSION}


def _scenario_status_expectations(metadata: Mapping[str, Any]) -> dict[str, ExpectedResult]:
    out = {}
    provenance = ExpectationProvenance(source=EXPECTATION_SOURCE_SCENARIO)
    for snapshot in metadata.get("scenarios") or ():
        if not isinstance(snapshot, dict):
            continue
        codes = snapshot.get("expected_status")
        name = snapshot.get("name")
        if isinstance(name, str) and isinstance(codes, list) and codes:
            try:
                out[name] = ExpectedResult(status_codes=tuple(codes), provenance=provenance,
                                           description="senaryonun expected_status listesi (metadata)")
            except RecordError:
                continue
    return out


def _parsing_by_seq(metadata: Mapping[str, Any]) -> dict[int, Any] | None:
    section = metadata.get("response_parsing")
    if not isinstance(section, dict) or not isinstance(section.get("requests"), list):
        return None
    out = {}
    for entry in section["requests"]:
        if isinstance(entry, dict) and isinstance(entry.get("seq"), int):
            out[entry["seq"]] = {k: v for k, v in entry.items() if k != "seq"}
    return out


def resolve_dataset_kind(run: RunData, requested: str | None) -> str:
    """Metadata `synthetic` → synthetic. Ölçüm çalıştırmasında türü çağıran söyler; söylemezse `unknown`."""
    if requested is not None and requested not in DATASET_KINDS:
        raise ValueError(f"dataset_kind şu değerlerden biri olmalı: {', '.join(sorted(DATASET_KINDS))}")
    if run.dataset_kind == METADATA_SYNTHETIC:
        if requested not in (None, DATASET_SYNTHETIC):
            raise ValueError("Sentetik çalıştırma başka bir veri türü olarak işaretlenemez")
        return DATASET_SYNTHETIC
    return requested or DATASET_UNKNOWN


def records_from_run(
    run: RunData,
    *,
    dataset_kind: str,
    expectations: Expectations | None = None,
) -> tuple[list[TestRecord], dict[str, Any]]:
    """Ölçüm isteklerini TestRecord'a dönüştürür. (kayıtlar, özet bilgisi) döner; ısınma istekleri atlanır."""
    registry = expectations if isinstance(expectations, ExpectationRegistry) else None
    legacy = {} if registry is not None else dict(expectations or {})
    from_scenarios = {} if registry is not None else _scenario_status_expectations(run.metadata)
    parsing = _parsing_by_seq(run.metadata)
    source_file = next((f.name for f in run.files if f.role == "json"), None)
    records, warmups = [], 0
    sources = {"expectation_registry": 0, "expectations_file": 0, "scenario_expected_status": 0, "none": 0}
    matches: Counter[str] = Counter()
    for result in run.results:
        if result.warmup:
            warmups += 1
            continue
        match_warnings = []
        if registry is not None:
            match = registry.match(result.scenario)
            matches[match.status] += 1
            expected = match.expected
            if match.status == MATCH_MATCHED:
                sources["expectation_registry"] += 1
            else:
                sources["none"] += 1
                match_warnings.append(match.warning)
        elif result.scenario in legacy:
            expected = legacy[result.scenario]
            sources["expectations_file"] += 1
        elif result.scenario in from_scenarios:
            expected = from_scenarios[result.scenario]
            sources["scenario_expected_status"] += 1
        else:
            expected = None
            sources["none"] += 1
        parsed, extra = None, []
        if result.status_code is not None:
            if parsing is None:
                extra.append("response_parsing_unavailable")
            elif result.seq not in parsing:
                extra.append("response_parsing_missing")
            else:
                try:
                    parsed = ParsedResponse.from_dict(parsing[result.seq])
                except ValueError:
                    extra.append("response_parsing_invalid")
        try:
            record = record_from_raw_result(result, dataset_kind=dataset_kind, expected=expected,
                                            source_file=source_file, parsed=parsed)
        except RecordError:  # özet sonuç kaydıyla tutarsız: kayıt geçersiz sayılır, karar verilmez
            record = record_from_raw_result(result, dataset_kind=dataset_kind, expected=expected,
                                            source_file=source_file)
            record = dataclasses.replace(record, data_quality_status=QUALITY_INVALID,
                                         warnings=(*record.warnings, "response_parsing_inconsistent"))
        if extra or match_warnings:
            record = dataclasses.replace(record, warnings=(*record.warnings, *match_warnings, *extra))
        records.append(record)
    known = {e.scenario_id for e in registry.expectations} if registry is not None else set(legacy)
    unused = sorted(known - {r.scenario for r in run.results})
    info = {"warmup_requests_skipped": warmups, "expected_result_sources": sources,
            "unused_expectations": unused, "response_parsing_available": parsing is not None}
    if registry is not None:
        info["expectation_matches"] = dict(sorted(matches.items()))
    return records, info


def build_run_document(
    run: RunData,
    *,
    dataset_kind: str,
    expectations: Expectations | None = None,
    expectations_source: dict[str, Any] | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    records, info = records_from_run(run, dataset_kind=dataset_kind, expectations=expectations)
    section = run.metadata.get("response_parsing") if isinstance(run.metadata.get("response_parsing"), dict) else {}
    source = {
        "source_type": "lab_result",
        "run_id": run.run_id,
        "partial": run.partial,
        "metadata_dataset_kind": run.dataset_kind,
        "result_files": [f.to_dict() for f in run.files],
        "response_parser": {k: section.get(k) for k in ("parser_version", "max_parse_bytes")} if section else None,
        "expectations": expectations_source,
        **info,
    }
    kwargs = {"now": now} if now is not None else {}
    return build_classification_document(records, sources=[source], **kwargs)
