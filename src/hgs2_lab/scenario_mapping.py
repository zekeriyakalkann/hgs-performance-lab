"""Senaryo eşleme sözleşmesi (`scenario_mapping_version: 1`) ve kayıt başına senaryo kimliği çözümlemesi (N10; ağ yok).

Bir test kaydının senaryo kimliği iki açık kaynaktan gelebilir:

1. **Testcase metadata'sı** (N3): testcase düzeyindeki `hgs2_lab.scenario_id` özelliği (`junit_report.py`).
2. **Eşleme dosyası** (bu modül): kararlı test tanımlayıcısını (`<classname>#<name>`) senaryo kimliğine bağlayan,
   sürümlü ve denetlenebilir kayıtlar.

Dosya biçimi (JSON; bilinmeyen anahtarlar her düzeyde reddedilir):

    {"scenario_mapping_version": 1,
     "mapping_set_id": "lab-n10",                          # isteğe bağlı
     "mappings": [{"mapping_id": "map-kart-pasif", "test_class": "com.example.lab.KartTests",
                   "test_name": "kartPasifCihaz", "scenario_id": "kart-pasif-cihaz", "status": "ACTIVE",
                   "evidence_ref": "N10-ESLEME-01", "description": "..."}]}

Kararlı tanımlayıcı: raporun testcase `classname` ve `name` öznitelikleri, rapordaki yazımıyla birebir. İkisi de
olmayan kayıt eşlenmez (`identifier_missing`); maskelenmiş tanımlayıcı güvenilir sayılmaz (`identifier_unstable`).
Test, sınıf, suite veya uç adından kimlik türetilmez; benzerlik, önek veya joker eşleştirmesi yapılmaz.

Çözümleme (`resolve_scenario`), hiçbir kaynağa öncelik vermez:

| Durum (`status`) | Sonuç (`outcome`) | Kimlik |
|---|---|---|
| `metadata` / `mapping` / `metadata_and_mapping` (aynı kimlik) | resolved | o kimlik |
| `no_source` (eşleme dosyası verilmedi, metadata yok) / `not_mapped` / `deprecated_only` | not_found | yok |
| `identifier_missing` / `identifier_unstable` / `metadata_invalid` | ambiguous | yok |
| `metadata_conflict` / `metadata_mapping_conflict` / `mapping_conflict` | conflict | yok |

Belirsiz ve çelişkili durumlar incelemeye düşer (`requires_review`); adaylardan hiçbiri seçilmez.

Dosya doğrulaması N7 registry'si gibi bütünseldir: tek bir hata bile varsa dosya bütünüyle reddedilir
(`MappingError`, tüm bulgularla); kısmen yüklenmiş eşleme ile analiz yapılmaz. Aynı tanımlayıcı için farklı
senaryolara giden birden fazla ACTIVE kayıt dosyayı geçersiz kılmaz, `conflicts` altında raporlanır ve o test için
çözümleme `mapping_conflict` döner. Aynı tanımlayıcı → aynı senaryo için ikinci ACTIVE kayıt (yinelenen eşleme)
dosyayı geçersiz kılar. Hata mesajları alan yolunu ve dosya adını içerir; alan değeri içermez.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .records import SCENARIO_ID_RE, TestRecord
from .sanitize import REDACTED, sanitize_text

MAPPING_VERSION = 1
MAX_MAPPING_BYTES = 4 * 1024 * 1024

MAPPING_ACTIVE = "ACTIVE"
MAPPING_DEPRECATED = "DEPRECATED"
MAPPING_STATUSES = frozenset({MAPPING_ACTIVE, MAPPING_DEPRECATED})

SOURCE_PROPERTY = "testcase_property"
SOURCE_MAPPING = "mapping_file"

RES_METADATA = "metadata"
RES_MAPPING = "mapping"
RES_AGREE = "metadata_and_mapping"
RES_NO_SOURCE = "no_source"
RES_NOT_MAPPED = "not_mapped"
RES_DEPRECATED_ONLY = "deprecated_only"
RES_IDENTIFIER_MISSING = "identifier_missing"
RES_IDENTIFIER_UNSTABLE = "identifier_unstable"
RES_METADATA_INVALID = "metadata_invalid"
RES_METADATA_CONFLICT = "metadata_conflict"
RES_METADATA_MAPPING_CONFLICT = "metadata_mapping_conflict"
RES_MAPPING_CONFLICT = "mapping_conflict"

OUTCOME_RESOLVED = "resolved"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_AMBIGUOUS = "ambiguous"
OUTCOME_CONFLICT = "conflict"
RESOLUTION_OUTCOMES = {
    RES_METADATA: OUTCOME_RESOLVED, RES_MAPPING: OUTCOME_RESOLVED, RES_AGREE: OUTCOME_RESOLVED,
    RES_NO_SOURCE: OUTCOME_NOT_FOUND, RES_NOT_MAPPED: OUTCOME_NOT_FOUND, RES_DEPRECATED_ONLY: OUTCOME_NOT_FOUND,
    RES_IDENTIFIER_MISSING: OUTCOME_AMBIGUOUS, RES_IDENTIFIER_UNSTABLE: OUTCOME_AMBIGUOUS,
    RES_METADATA_INVALID: OUTCOME_AMBIGUOUS,
    RES_METADATA_CONFLICT: OUTCOME_CONFLICT, RES_METADATA_MAPPING_CONFLICT: OUTCOME_CONFLICT,
    RES_MAPPING_CONFLICT: OUTCOME_CONFLICT,
}
RESOLUTION_STATUSES = tuple(RESOLUTION_OUTCOMES)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Yerel mutlak yollar (kullanıcı adı sızdırır) kanıt referansı olarak kabul edilmez (expectations.py ile aynı kural).
_LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|root|var|tmp)/)|^~[\\/]")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_IDENTIFIER, _MAX_REF, _MAX_DESCRIPTION = 500, 300, 500
_ROOT_KEYS = {"scenario_mapping_version", "mapping_set_id", "mappings"}
_ENTRY_KEYS = {"mapping_id", "test_class", "test_name", "scenario_id", "status", "evidence_ref", "description"}


class MappingError(ValueError):
    """Eşleme dosyası okunamadı veya geçersiz. `issues` tüm bulguları (alan yolu + açıklama) taşır; değer içermez."""

    def __init__(self, message: str, issues: Sequence[str] = ()) -> None:
        self.issues = tuple(issues) or (message,)
        super().__init__(message if not issues else f"{message}: " + "; ".join(self.issues))


def stable_test_key(test_class: str, test_name: str) -> str:
    """Kararlı test tanımlayıcısı: N3 ayrıştırıcısının `test_id` biçimiyle aynı (`<classname>#<name>`)."""
    return f"{test_class}#{test_name}"


@dataclass(frozen=True)
class MappingEntry:
    mapping_id: str
    test_class: str
    test_name: str
    scenario_id: str
    status: str
    evidence_ref: str | None = None
    description: str | None = None

    @property
    def key(self) -> str:
        return stable_test_key(self.test_class, self.test_name)

    @property
    def is_active(self) -> bool:
        return self.status == MAPPING_ACTIVE

    def to_dict(self) -> dict[str, Any]:
        return {"mapping_id": self.mapping_id, "test_class": self.test_class, "test_name": self.test_name,
                "scenario_id": self.scenario_id, "status": self.status, "evidence_ref": self.evidence_ref,
                "description": self.description}


@dataclass(frozen=True)
class ScenarioMapping:
    entries: tuple[MappingEntry, ...]  # (tanımlayıcı, mapping_id) sırasıyla
    mapping_set_id: str | None = None
    source: Mapping[str, Any] | None = None  # dosya adı + SHA-256 (yol değil)

    def candidates(self, key: str) -> list[MappingEntry]:
        return [e for e in self.entries if e.key == key]

    @property
    def conflicts(self) -> dict[str, list[str]]:
        """tanımlayıcı → farklı senaryolara giden ACTIVE eşleme kimlikleri."""
        by_key: dict[str, list[MappingEntry]] = {}
        for entry in self.entries:
            if entry.is_active:
                by_key.setdefault(entry.key, []).append(entry)
        return {k: [e.mapping_id for e in v] for k, v in by_key.items() if len({e.scenario_id for e in v}) > 1}

    def to_dict(self) -> dict[str, Any]:
        return {"scenario_mapping_version": MAPPING_VERSION, "mapping_set_id": self.mapping_set_id,
                "mappings": [e.to_dict() for e in self.entries]}

    @property
    def content_sha256(self) -> str:
        """Kanonik içerik özeti: dosyadaki kayıt sırası ve biçimlendirme özeti değiştirmez."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def summary(self) -> dict[str, Any]:
        return {"mapping_set_id": self.mapping_set_id, "scenario_mapping_version": MAPPING_VERSION,
                "content_sha256": self.content_sha256, "source": dict(self.source) if self.source else None,
                "mappings": len(self.entries),
                "by_status": {s: sum(e.status == s for e in self.entries) for s in sorted(MAPPING_STATUSES)},
                "tests": len({e.key for e in self.entries}),
                "scenarios": len({e.scenario_id for e in self.entries if e.is_active}),
                "conflicts": self.conflicts}


def _check_keys(data: Any, allowed: set[str], required: set[str], where: str, issues: list[str]) -> bool:
    if not isinstance(data, dict):
        issues.append(f"{where}: nesne olmalı")
        return False
    unknown = sorted(str(k) for k in data if k not in allowed)
    missing = sorted(required - set(data))
    if unknown:
        issues.append(f"{where}: bilinmeyen anahtar(lar) {unknown}")
    if missing:
        issues.append(f"{where}: eksik zorunlu anahtar(lar) {missing}")
    return not unknown and not missing


def _identifier(value: Any, where: str, issues: list[str], *, allow_hash: bool) -> None:
    """Test sınıfı/adı rapordaki yazımla birebir karşılaştırılır; bu yüzden düzeltilmez, yalnızca denetlenir."""
    if not isinstance(value, str) or not value or len(value) > _MAX_IDENTIFIER or value != value.strip() \
            or _CONTROL_RE.search(value):
        issues.append(f"{where}: baş/son boşluksuz, kontrol karakteri içermeyen, en çok {_MAX_IDENTIFIER} karakterlik "
                      "metin olmalı (rapordaki yazımla birebir)")
    elif not allow_hash and "#" in value:
        issues.append(f"{where}: '#' içeremez (tanımlayıcı ayracı)")
    elif sanitize_text(value) != value:  # maskelenecek bir kalıp: hassas değer taşıyabilir, çıktıya yazılamaz
        issues.append(f"{where}: hassas değer kalıbı içeriyor (ör. anahtar=değer); tanımlayıcı olarak kullanılamaz")


def _text(value: Any, where: str, limit: int, issues: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        issues.append(f"{where}: boş olmayan, en çok {limit} karakterlik metin olmalı")
        return None
    return sanitize_text(value)


def _parse_entry(item: Any, where: str, issues: list[str]) -> MappingEntry | None:
    if not _check_keys(item, _ENTRY_KEYS, {"mapping_id", "test_class", "test_name", "scenario_id", "status"}, where,
                       issues):
        return None
    before = len(issues)
    if not isinstance(item["mapping_id"], str) or not _ID_RE.match(item["mapping_id"]):
        issues.append(f"{where}.mapping_id: harf/rakamla başlayan, yalnızca harf, rakam, '.', '_', '-' içeren kimlik "
                      "olmalı (en çok 64)")
    _identifier(item["test_class"], f"{where}.test_class", issues, allow_hash=False)
    _identifier(item["test_name"], f"{where}.test_name", issues, allow_hash=True)
    if not isinstance(item["scenario_id"], str) or not SCENARIO_ID_RE.match(item["scenario_id"]):
        issues.append(f"{where}.scenario_id: harf/rakamla başlayan, yalnızca harf, rakam, '.', '_', '-' içeren kimlik "
                      "olmalı (en çok 64; `hgs2_lab.scenario_id` ile aynı biçim)")
    if item["status"] not in MAPPING_STATUSES:
        issues.append(f"{where}.status: ACTIVE veya DEPRECATED olmalı")
    ref = _text(item.get("evidence_ref"), f"{where}.evidence_ref", _MAX_REF, issues)
    if isinstance(item.get("evidence_ref"), str) and _LOCAL_PATH_RE.match(item["evidence_ref"].strip()):
        issues.append(f"{where}.evidence_ref: mutlak yerel yol kullanılamaz (göreli kaynak tanımlayıcısı verin)")
    description = _text(item.get("description"), f"{where}.description", _MAX_DESCRIPTION, issues)
    if len(issues) > before:
        return None
    return MappingEntry(mapping_id=item["mapping_id"], test_class=item["test_class"], test_name=item["test_name"],
                        scenario_id=item["scenario_id"], status=item["status"], evidence_ref=ref,
                        description=description)


def parse_mapping(data: Any, *, source: Mapping[str, Any] | None = None) -> ScenarioMapping:
    """Sözleşmeyi doğrular. Tek bir hata bile varsa tüm dosya reddedilir (MappingError, tüm bulgularla)."""
    issues: list[str] = []
    if not _check_keys(data, _ROOT_KEYS, {"scenario_mapping_version", "mappings"}, "kök", issues):
        raise MappingError("Eşleme dosyası geçersiz", issues)
    version = data["scenario_mapping_version"]
    if isinstance(version, bool) or version != MAPPING_VERSION:
        raise MappingError(f"Desteklenmeyen eşleme sürümü: scenario_mapping_version {MAPPING_VERSION} olmalı")
    set_id = data.get("mapping_set_id")
    if set_id is not None and (not isinstance(set_id, str) or not _ID_RE.match(set_id)):
        issues.append("mapping_set_id: harf/rakamla başlayan güvenli bir kimlik olmalı (en çok 64)")
    raw = data["mappings"]
    if not isinstance(raw, list) or not raw:
        issues.append("mappings: boş olmayan liste olmalı")
        raw = []
    entries: list[MappingEntry] = []
    seen_ids: set[str] = set()
    active_pairs: dict[tuple[str, str], str] = {}
    for n, item in enumerate(raw):
        entry = _parse_entry(item, f"mappings[{n}]", issues)
        if entry is None:
            continue
        if entry.mapping_id in seen_ids:
            issues.append(f"mappings[{n}].mapping_id: yinelenen kimlik")
        seen_ids.add(entry.mapping_id)
        if entry.is_active:
            pair = (entry.key, entry.scenario_id)
            if pair in active_pairs:
                issues.append(f"mappings[{n}]: yinelenen eşleme (aynı test ve senaryo için ikinci ACTIVE kayıt; ilk "
                              f"kayıt {active_pairs[pair]})")
            active_pairs.setdefault(pair, entry.mapping_id)
        entries.append(entry)
    if issues:
        raise MappingError("Eşleme dosyası geçersiz", issues)
    ordered = tuple(sorted(entries, key=lambda e: (e.key, e.mapping_id)))
    return ScenarioMapping(entries=ordered, mapping_set_id=set_id, source=source)


def load_mapping(path: str | Path) -> ScenarioMapping:
    """Dosyayı yalnızca okur. Hata mesajları dosyanın yalnızca adını içerir."""
    path = Path(path)
    try:
        size = path.stat().st_size
        if size > MAX_MAPPING_BYTES:
            raise MappingError(f"Eşleme dosyası {MAX_MAPPING_BYTES} bayttan büyük: {path.name}")
        raw = path.read_bytes()
    except FileNotFoundError:
        raise MappingError(f"Eşleme dosyası bulunamadı: {path.name}") from None
    except OSError as exc:
        raise MappingError(f"Eşleme dosyası okunamadı: {path.name} ({type(exc).__name__})") from None
    if not raw.strip():
        raise MappingError(f"Eşleme dosyası boş: {path.name}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        where = f" (satır {exc.lineno}, sütun {exc.colno})" if isinstance(exc, json.JSONDecodeError) else ""
        raise MappingError(f"Eşleme dosyası geçerli UTF-8 JSON değil: {path.name}{where}") from None
    return parse_mapping(data, source={"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()})


def mapping_source(mapping: ScenarioMapping) -> dict[str, Any]:
    """Analiz belgesine yazılan kaynak bilgisi (dosya adı, SHA-256, özet); yol içermez."""
    return {**(dict(mapping.source) if mapping.source else {}), "scenario_mapping_version": MAPPING_VERSION,
            "mapping": mapping.summary()}


@dataclass(frozen=True)
class ScenarioResolution:
    """Bir kaydın senaryo kimliğinin hangi kaynaktan, nasıl belirlendiği (ya da neden belirlenemediği)."""

    status: str
    scenario_id: str | None  # yalnızca outcome == resolved iken dolu
    test_key: str | None  # kayıttan okunan kararlı tanımlayıcı (yoksa / güvenilmezse None)
    metadata_scenario_id: str | None  # N3'ün okuduğu geçerli testcase özelliği
    mapping_ids: tuple[str, ...] = ()  # bu tanımlayıcıya ait ACTIVE eşleme kayıtları
    deprecated_mapping_ids: tuple[str, ...] = ()
    candidate_scenario_ids: tuple[str, ...] = ()  # tüm kaynaklardan gelen farklı kimlikler (sıralı)
    mapping_requested: bool = False

    @property
    def outcome(self) -> str:
        return RESOLUTION_OUTCOMES[self.status]

    @property
    def sources(self) -> tuple[str, ...]:
        return {RES_METADATA: (SOURCE_PROPERTY,), RES_MAPPING: (SOURCE_MAPPING,),
                RES_AGREE: (SOURCE_PROPERTY, SOURCE_MAPPING)}.get(self.status, ())

    @property
    def requires_review(self) -> bool:
        return self.outcome in (OUTCOME_AMBIGUOUS, OUTCOME_CONFLICT)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "outcome": self.outcome, "scenario_id": self.scenario_id,
                "sources": list(self.sources), "test_key": self.test_key,
                "metadata_scenario_id": self.metadata_scenario_id, "mapping_ids": list(self.mapping_ids),
                "deprecated_mapping_ids": list(self.deprecated_mapping_ids),
                "candidate_scenario_ids": list(self.candidate_scenario_ids),
                "mapping_requested": self.mapping_requested, "requires_review": self.requires_review}


def record_test_key(record: TestRecord) -> tuple[str | None, str | None]:
    """(kararlı tanımlayıcı, sorun durumu). Tanımlayıcı yalnızca hem `classname` hem `name` raporda varsa vardır.

    N3, ikisi de varsa `test_id = "<classname>#<name>"` yazar; yalnızca biri varsa `test_id` o değerdir. Maskeleme
    tanımlayıcıyı değiştirmişse rapordaki gerçek ad bilinemez: güvenilir sayılmaz.
    """
    name, test_id = record.test_name, record.test_id
    if not name or not test_id or test_id == name or not test_id.endswith("#" + name):
        return None, RES_IDENTIFIER_MISSING
    if REDACTED in test_id:
        return None, RES_IDENTIFIER_UNSTABLE
    return test_id, None


def resolve_scenario(record: TestRecord, mapping: ScenarioMapping | None = None) -> ScenarioResolution:
    """Kaydın senaryo kimliğini metadata ve (verildiyse) eşleme dosyasından çözer. Hiçbir kaynağa öncelik verilmez."""
    metadata = record.scenario_id
    if "scenario_id_conflict" in record.warnings:
        metadata_problem = RES_METADATA_CONFLICT
    elif "scenario_id_invalid" in record.warnings:
        metadata_problem = RES_METADATA_INVALID
    else:
        metadata_problem = None
    key, key_problem = record_test_key(record)
    active: list[MappingEntry] = []
    deprecated: list[MappingEntry] = []
    if mapping is not None and key is not None:
        for entry in mapping.candidates(key):
            (active if entry.is_active else deprecated).append(entry)
    mapped = sorted({e.scenario_id for e in active})

    if metadata_problem is not None:
        status = metadata_problem
    elif len(mapped) > 1:
        status = RES_MAPPING_CONFLICT
    elif metadata and mapped:
        status = RES_AGREE if mapped == [metadata] else RES_METADATA_MAPPING_CONFLICT
    elif metadata:
        status = RES_METADATA
    elif mapped:
        status = RES_MAPPING
    elif mapping is None:
        status = RES_NO_SOURCE
    elif key is None:
        status = key_problem
    elif deprecated:
        status = RES_DEPRECATED_ONLY
    else:
        status = RES_NOT_MAPPED
    scenario = metadata if status in (RES_METADATA, RES_AGREE) else (mapped[0] if status == RES_MAPPING else None)
    return ScenarioResolution(
        status=status, scenario_id=scenario, test_key=key, metadata_scenario_id=metadata,
        mapping_ids=tuple(sorted(e.mapping_id for e in active)),
        deprecated_mapping_ids=tuple(sorted(e.mapping_id for e in deprecated)),
        candidate_scenario_ids=tuple(sorted({*mapped, *([metadata] if metadata else [])})),
        mapping_requested=mapping is not None)


def apply_scenario_mapping(
    records: Iterable[TestRecord], mapping: ScenarioMapping | None
) -> tuple[list[TestRecord], list[ScenarioResolution]]:
    """Kayıtların senaryo kimliğini çözer. Eşleme dosyası yoksa kayıtlar değişmez (N8 davranışı aynen korunur).

    Eşleme dosyası varsa her kayda `scenario_resolution:<durum>` uyarısı eklenir ve `scenario_id` çözümlenen kimlik
    olur (çözümlenemediyse None). Çelişkide N4'ün mevcut sözleşmesi gereği `scenario_id_conflict` de eklenir; böylece
    beklenti eşleştirmesi istendiğinde sınıflandırıcı kaydı incelemeye düşürür. Kaynak test sonucu değişmez.
    """
    out: list[TestRecord] = []
    resolutions: list[ScenarioResolution] = []
    for record in records:
        resolution = resolve_scenario(record, mapping)
        resolutions.append(resolution)
        if mapping is not None:
            warnings = [*record.warnings, f"scenario_resolution:{resolution.status}"]
            if resolution.outcome == OUTCOME_CONFLICT:
                warnings.append("scenario_id_conflict")
            record = dataclasses.replace(record, scenario_id=resolution.scenario_id,
                                         warnings=tuple(dict.fromkeys(warnings)))
        out.append(record)
    return out, resolutions
