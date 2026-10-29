"""Gerçek (veya sentetik) test sonucu örnekleri için veri alım sözleşmesi (N9; `ingestion_version: 1`; ağ yok).

Yeni bir kayıt modeli yoktur: her girdi mevcut `TestRecord` sözlüğünü (kayıt şeması 1 veya 2) taşır; alım katmanı
yalnızca kaynak kimliği, kaynak kanıtı ve etiket incelemesi gibi kökeni belgeleyen alanları ekler ve kuralları uygular.

    {"ingestion_version": 1, "batch_id": "hgs2-hata-2026-11", "dataset_kind": "real",
     "entries": [{"source_record_id": "surefire-TEST-x#t1",
                  "source_reference": {"source_file": "TEST-x.xml", "source_sha256": "<64 hex>", "location": "t1"},
                  "test_scope": "kart okutma ret akışı",
                  "label_review": {"status": "REVIEWED", "evidence_ref": "INCELEME-12", "reviewer_role": "qa"},
                  "record": { ...TestRecord sözlüğü... }}]}

Kurallar:

* Paketin `dataset_kind` değeri her kayıtta aynı olmalı; gerçek ve sentetik kayıtlar aynı pakette karışamaz.
* `source_record_id` zorunlu ve paket içinde benzersizdir; aynı kimlik ikinci kez gelirse bağımsız örnek sayılmaz
  (`duplicates`). Aynı `record_id` de iki kez kabul edilmez.
* Kaydın `label` alanı (ör. APPLICATION_FAILURE) ancak `label_review.status = REVIEWED` ve bir `evidence_ref` varsa
  `human_review` etiketi olarak kabul edilir; aksi halde etiket kayıttan çıkarılır ve `proposed_label` olarak
  raporlanır (`label_unreviewed`). Gerçek pakette `synthetic_plan` etiket kaynağı reddedilir.
* Kaynakta olmayan değer uydurulmaz; `source_reference` yoksa kayıt kabul edilir ama `source_reference_missing` uyarısı
  alır ve etiketi doğrulanamaz.
* Tüm metinler `TestRecord` kurulurken N1 maskelemesinden geçer; çıktı ham gövde, log veya rapor içermez.
* Hatalı bir girdi diğerlerini durdurmaz (`rejected`); zarf (envelope) geçersizse hiçbir kayıt kabul edilmez.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .classify import build_classification_document
from .junit_analysis import Expectations, attach_expectations
from .records import (
    DATASET_KINDS,
    DATASET_REAL,
    RecordError,
    TestRecord,
)
from .sanitize import REDACTED, sanitize_text

INGESTION_VERSION = 1
REVIEW_REVIEWED = "REVIEWED"
REVIEW_UNREVIEWED = "UNREVIEWED"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:#-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ENVELOPE_KEYS = {"ingestion_version", "batch_id", "dataset_kind", "entries"}
_ENTRY_KEYS = {"source_record_id", "source_reference", "test_scope", "label_review", "record"}
_REFERENCE_KEYS = {"source_file", "source_sha256", "location"}
_REVIEW_KEYS = {"status", "evidence_ref", "reviewer_role"}
_TEXT_FIELDS = ("test_id", "test_name", "suite_name", "scenario_id", "business_outcome", "exception_type",
                "error_message", "stack_trace")


class IngestionError(ValueError):
    """Zarf geçersiz; hiçbir kayıt kabul edilmedi. Mesaj değer içermez."""


@dataclass
class IngestionResult:
    batch_id: str
    dataset_kind: str
    records: list[TestRecord] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)  # kabul edilen girdilerin köken bilgisi
    rejected: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "entries_received": len(self.records) + len(self.rejected) + len(self.duplicates),
            "accepted": len(self.records),
            "rejected": len(self.rejected),
            "duplicates": len(self.duplicates),
            "labels_accepted": sum(1 for r in self.records if r.label is not None),
            "labels_withheld_unreviewed": sum(1 for e in self.entries if e["proposed_label"] is not None),
            "without_source_reference": sum(1 for e in self.entries if e["source_reference"] is None),
            "without_scenario_id": sum(1 for r in self.records if not r.scenario_id),
            "records_with_masked_text": sum(1 for r in self.records if _masked(r)),
        }


def _masked(record: TestRecord) -> bool:
    return any(REDACTED in (getattr(record, name) or "") for name in _TEXT_FIELDS)


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"en çok {limit} karakterlik boş olmayan metin olmalı")
    return sanitize_text(value)


def _reference(data: Any) -> dict[str, Any] | None:
    if data is None:
        return None
    if not isinstance(data, dict) or set(data) - _REFERENCE_KEYS or "source_file" not in data:
        raise ValueError("source_reference: source_file zorunlu; yalnızca source_file, source_sha256, location")
    name = data["source_file"]
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or len(name) > 255:
        raise ValueError("source_reference.source_file yalnızca dosya adı olmalı (yol değil)")
    sha = data.get("source_sha256")
    if sha is not None and (not isinstance(sha, str) or not _SHA256_RE.match(sha)):
        raise ValueError("source_reference.source_sha256 64 karakterlik küçük harfli onaltılık özet olmalı")
    return {"source_file": sanitize_text(name), "source_sha256": sha, "location": _text(data.get("location"), 200)}


def _review(data: Any) -> dict[str, Any]:
    if data is None:
        return {"status": REVIEW_UNREVIEWED, "evidence_ref": None, "reviewer_role": None}
    if not isinstance(data, dict) or set(data) - _REVIEW_KEYS or data.get("status") not in (REVIEW_REVIEWED,
                                                                                         REVIEW_UNREVIEWED):
        raise ValueError("label_review: status REVIEWED/UNREVIEWED; yalnızca status, evidence_ref, reviewer_role")
    return {"status": data["status"], "evidence_ref": _text(data.get("evidence_ref"), 200),
            "reviewer_role": _text(data.get("reviewer_role"), 100)}


def _entry(raw: Any, dataset_kind: str, index: int) -> tuple[TestRecord, dict[str, Any]]:
    if not isinstance(raw, dict):
        raise ValueError("girdi nesne olmalı")
    unknown, missing = set(raw) - _ENTRY_KEYS, {"source_record_id", "record"} - set(raw)
    if unknown or missing:
        raise ValueError(f"bilinmeyen anahtar(lar) {sorted(unknown)}, eksik zorunlu anahtar(lar) {sorted(missing)}")
    source_id = raw["source_record_id"]
    if not isinstance(source_id, str) or not _ID_RE.match(source_id):
        raise ValueError("source_record_id harf/rakamla başlayan güvenli bir kimlik olmalı (en çok 128)")
    reference = _reference(raw.get("source_reference"))
    review = _review(raw.get("label_review"))
    scope_text = _text(raw.get("test_scope"), 500)
    if not isinstance(raw["record"], Mapping):
        raise ValueError("record bir TestRecord nesnesi olmalı")
    try:
        record = TestRecord.from_dict(raw["record"])  # kayıt şeması 1 ve 2; N1 maskelemesi burada uygulanır
    except (RecordError, TypeError) as exc:
        raise ValueError(f"record geçersiz: {exc}") from None
    if record.dataset_kind != dataset_kind:
        raise ValueError("record.dataset_kind paketin dataset_kind değeriyle aynı olmalı (gerçek/sentetik karışamaz)")
    warnings, proposed = list(record.warnings), None
    if reference is None:
        warnings.append("source_reference_missing")
    if record.label is not None:
        if dataset_kind == DATASET_REAL and record.label_source == "synthetic_plan":
            raise ValueError("Gerçek pakette synthetic_plan etiket kaynağı kullanılamaz")
        verified_label = (review["status"] == REVIEW_REVIEWED and review["evidence_ref"] is not None
                          and reference is not None)
        if record.label_source == "human_review" and not verified_label:
            proposed = record.label
            warnings.append("label_unreviewed")
            record = dataclasses.replace(record, label=None, label_source=None)
    if warnings != list(record.warnings):
        record = dataclasses.replace(record, warnings=tuple(dict.fromkeys(warnings)))
    provenance = {"index": index, "source_record_id": source_id, "record_id": record.record_id,
                  "source_reference": reference, "test_scope": scope_text, "label_review": review,
                  "proposed_label": proposed}
    return record, provenance


def parse_ingestion(data: Any) -> IngestionResult:
    """Zarfı doğrular, girdileri tek tek kabul/ret eder. Hiçbir girdi hatası diğerlerini durdurmaz."""
    if not isinstance(data, dict):
        raise IngestionError("Alım dosyasının kökü nesne olmalı")
    unknown, missing = set(data) - _ENVELOPE_KEYS, _ENVELOPE_KEYS - set(data)
    if unknown or missing:
        raise IngestionError(f"Alım dosyası: bilinmeyen anahtar(lar) {sorted(unknown)}, eksik {sorted(missing)}")
    if data["ingestion_version"] != INGESTION_VERSION or isinstance(data["ingestion_version"], bool):
        raise IngestionError(f"ingestion_version {INGESTION_VERSION} olmalı")
    batch_id = data["batch_id"]
    if not isinstance(batch_id, str) or not _ID_RE.match(batch_id):
        raise IngestionError("batch_id güvenli bir kimlik olmalı")
    if data["dataset_kind"] not in DATASET_KINDS:
        raise IngestionError(f"dataset_kind şunlardan biri olmalı: {', '.join(sorted(DATASET_KINDS))}")
    if not isinstance(data["entries"], list) or not data["entries"]:
        raise IngestionError("entries boş olmayan liste olmalı")
    result = IngestionResult(batch_id=batch_id, dataset_kind=data["dataset_kind"])
    seen_source: dict[str, int] = {}
    seen_record: dict[str, int] = {}
    for index, raw in enumerate(data["entries"]):
        try:
            record, provenance = _entry(raw, result.dataset_kind, index)
        except ValueError as exc:
            source_id = raw.get("source_record_id") if isinstance(raw, dict) else None
            safe_id = source_id if isinstance(source_id, str) and _ID_RE.match(source_id) else None
            result.rejected.append({"index": index, "source_record_id": safe_id, "reason": sanitize_text(str(exc))})
            continue
        source_id = provenance["source_record_id"]
        if source_id in seen_source or record.record_id in seen_record:
            first = seen_source.get(source_id, seen_record.get(record.record_id))
            result.duplicates.append({"index": index, "source_record_id": source_id, "duplicate_of_index": first})
            continue
        seen_source[source_id] = index
        seen_record[record.record_id] = index
        result.records.append(record)
        result.entries.append(provenance)
    return result


def build_ingestion_document(
    result: IngestionResult,
    *,
    expectations: Expectations | None = None,
    expectations_source: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Kabul edilen kayıtları mevcut hatta aktarır: (isteğe bağlı) N7/N8 beklenti eşleştirme → N4 → ortak belge.

    Kayıtta gömülü bir `expected_result` varsa registry onu değiştirmez (`embedded_expected_result_kept`).
    """
    embedded = [r for r in result.records if r.expected_result is not None]
    plain = [r for r in result.records if r.expected_result is None]
    matched, statuses = attach_expectations(plain, expectations)
    if expectations is not None:
        embedded = [dataclasses.replace(r, warnings=(*r.warnings, "embedded_expected_result_kept")) for r in embedded]
    order = {r.record_id: i for i, r in enumerate(result.records)}
    records = sorted([*matched, *embedded], key=lambda r: order[r.record_id])
    summary_extra = {
        "ingestion": {**result.summary(), "batch_id": result.batch_id, "dataset_kind": result.dataset_kind},
        "expectation_matching": {"requested": expectations is not None,
                                 "by_match_status": dict(sorted(statuses.items())),
                                 "embedded_expected_result": len(embedded)},
    }
    kwargs = {"now": now} if now is not None else {}
    return build_classification_document(
        records, sources=[{"source_type": "ingestion", "batch_id": result.batch_id, **(source or {})}],
        summary_extra=summary_extra,
        content_extra={"ingestion_entries": result.entries, "ingestion_rejected": result.rejected,
                       "ingestion_duplicates": result.duplicates, "expectations": expectations_source},
        notes_extra=["Alım paketindeki kayıtlar kaynağın beyan ettiği değerlerdir; Lab bu kayıtları yeniden ölçmez. "
                     "İncelenmemiş etiketler doğrulanmış etiket olarak kabul edilmez (proposed_label)."],
        **kwargs)


