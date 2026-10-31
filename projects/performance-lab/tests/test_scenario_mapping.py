"""N10: senaryo eşleme sözleşmesi — dosya doğrulaması, kararlı tanımlayıcı ve kayıt başına çözümleme (ağ yok).

Bütün girdiler sentetiktir.
"""

import json
import random
import socket
from pathlib import Path

import pytest

from hgs2_lab.junit_report import parse_junit_bytes
from hgs2_lab.records import SOURCE_JUNIT_XML, TestRecord
from hgs2_lab.scenario_mapping import (
    MAPPING_VERSION,
    MappingError,
    apply_scenario_mapping,
    load_mapping,
    parse_mapping,
    record_test_key,
    resolve_scenario,
    stable_test_key,
)

FIX = Path(__file__).parent / "fixtures" / "scenario-mapping"
CLS = "com.example.lab.KartTests"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("ağ erişimi denendi")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def entry(mapping_id, name, scenario, *, status="ACTIVE", test_class=CLS, **extra):
    return {"mapping_id": mapping_id, "test_class": test_class, "test_name": name, "scenario_id": scenario,
            "status": status, **extra}


def mapping(*entries, **root):
    return parse_mapping({"scenario_mapping_version": 1, "mappings": list(entries), **root})


def issues_of(data):
    with pytest.raises(MappingError) as info:
        parse_mapping(data)
    return info.value.issues


def case(name="kartPasif", classname=CLS, scenario=None, extra=""):
    attrs = f' name="{name}"' if name is not None else ""
    attrs += f' classname="{classname}"' if classname is not None else ""
    props = "".join(f'<property name="hgs2_lab.scenario_id" value="{s}"/>' for s in
                    ([scenario] if isinstance(scenario, str) else scenario or []))
    body = f"<properties>{props}</properties>" if props else ""
    return f"<testcase{attrs}>{body}{extra}</testcase>"


def records(*cases):
    xml = f'<testsuite name="{CLS}">{"".join(cases)}</testsuite>'.encode()
    return list(parse_junit_bytes(xml, source_file="t.xml", dataset_kind="synthetic").records)


# --- B. eşleme dosyası ---
def test_valid_file_loads_with_summary_and_canonical_order():
    loaded = load_mapping(FIX / "n10-mapping.json")
    summary = loaded.summary()
    assert loaded.mapping_set_id == "lab-esleme-n10" and summary["scenario_mapping_version"] == MAPPING_VERSION
    assert summary["mappings"] == 17 and summary["by_status"] == {"ACTIVE": 16, "DEPRECATED": 1}
    assert summary["source"]["file"] == "n10-mapping.json" and len(summary["source"]["sha256"]) == 64
    assert summary["conflicts"] == {f"com.example.lab.EslemeTests#ikiliEsleme": ["map-ikili-a", "map-ikili-b"]}
    keys = [(e.key, e.mapping_id) for e in loaded.entries]
    assert keys == sorted(keys)


def test_content_hash_ignores_entry_order_and_formatting():
    data = json.loads((FIX / "n10-mapping.json").read_text(encoding="utf-8"))
    first = parse_mapping(data).content_sha256
    random.Random(7).shuffle(data["mappings"])
    assert parse_mapping(data).content_sha256 == first


@pytest.mark.parametrize("content, fragment", [
    (b"", "boş"), (b"   \n", "boş"), (b"{bozuk", "geçerli UTF-8 JSON değil"), (b"\xff\xfe", "geçerli UTF-8 JSON değil"),
])
def test_empty_or_malformed_file_is_rejected(tmp_path, content, fragment):
    path = tmp_path / "esleme.json"
    path.write_bytes(content)
    with pytest.raises(MappingError) as info:
        load_mapping(path)
    assert fragment in str(info.value) and "esleme.json" in str(info.value) and str(tmp_path) not in str(info.value)


def test_missing_file_names_only_the_file(tmp_path):
    with pytest.raises(MappingError) as info:
        load_mapping(tmp_path / "yok.json")
    assert "bulunamadı: yok.json" in str(info.value) and str(tmp_path) not in str(info.value)


@pytest.mark.parametrize("version", [2, 0, "1", True, None])
def test_unsupported_version_is_rejected(version):
    with pytest.raises(MappingError, match="Desteklenmeyen eşleme sürümü"):
        parse_mapping({"scenario_mapping_version": version, "mappings": [entry("m1", "t", "s")]})


@pytest.mark.parametrize("data, fragment", [
    ([], "kök: nesne olmalı"),
    ({"mappings": []}, "eksik zorunlu anahtar(lar) ['scenario_mapping_version']"),
    ({"scenario_mapping_version": 1, "mappings": [], "fazla": 1}, "bilinmeyen anahtar(lar) ['fazla']"),
    ({"scenario_mapping_version": 1, "mappings": []}, "mappings: boş olmayan liste"),
    ({"scenario_mapping_version": 1, "mappings": {}}, "mappings: boş olmayan liste"),
    ({"scenario_mapping_version": 1, "mapping_set_id": "../x", "mappings": [entry("m1", "t", "s")]}, "mapping_set_id"),
])
def test_schema_errors(data, fragment):
    assert any(fragment in issue for issue in issues_of(data))


@pytest.mark.parametrize("override, fragment", [
    ({"test_class": ""}, "mappings[0].test_class"),
    ({"test_name": " kartPasif"}, "mappings[0].test_name"),
    ({"test_name": "a\nb"}, "mappings[0].test_name"),
    ({"test_class": "a#b"}, "'#' içeremez"),
    ({"scenario_id": "geçersiz kimlik"}, "mappings[0].scenario_id"),
    ({"scenario_id": "x" * 65}, "mappings[0].scenario_id"),
    ({"status": "VERIFIED"}, "ACTIVE veya DEPRECATED"),
    ({"mapping_id": "-x"}, "mappings[0].mapping_id"),
    ({"evidence_ref": "C:\\Users\\Sahte\\esleme.md"}, "mutlak yerel yol"),
    ({"evidence_ref": "/home/sahte/esleme.md"}, "mutlak yerel yol"),
    ({"description": ""}, "mappings[0].description"),
    ({"bilinmeyen": 1}, "bilinmeyen anahtar(lar) ['bilinmeyen']"),
])
def test_entry_validation(override, fragment):
    item = {**entry("m1", "kartPasif", "kart-pasif"), **override}
    assert any(fragment in issue for issue in issues_of({"scenario_mapping_version": 1, "mappings": [item]}))


def test_missing_identifier_fields_are_rejected():
    item = entry("m1", "kartPasif", "kart-pasif")
    del item["test_class"], item["scenario_id"]
    issues = issues_of({"scenario_mapping_version": 1, "mappings": [item]})
    assert any("eksik zorunlu anahtar(lar) ['scenario_id', 'test_class']" in i for i in issues)


def test_whole_file_is_rejected_on_single_error_and_reports_all_issues():
    issues = issues_of({"scenario_mapping_version": 1, "mappings": [
        entry("m1", "a", "s-a"), entry("m2", "b", "bad id"), entry("m3", "c", "s-c", status="X")]})
    assert len(issues) == 2 and "mappings[1]" in issues[0] and "mappings[2]" in issues[1]


def test_duplicate_mapping_id_and_duplicate_active_mapping_are_rejected():
    issues = issues_of({"scenario_mapping_version": 1, "mappings": [entry("m1", "a", "s"), entry("m1", "b", "s")]})
    assert any("yinelenen kimlik" in i for i in issues)
    issues = issues_of({"scenario_mapping_version": 1, "mappings": [entry("m1", "a", "s"), entry("m2", "a", "s")]})
    assert any("yinelenen eşleme" in i and "m1" in i for i in issues)


def test_deprecated_duplicate_is_history_not_a_duplicate():
    loaded = mapping(entry("m1", "a", "s", status="DEPRECATED"), entry("m2", "a", "s"))
    assert loaded.conflicts == {}


def test_conflicting_active_mappings_are_reported_not_rejected():
    loaded = mapping(entry("m1", "a", "s-1"), entry("m2", "a", "s-2"), entry("m3", "a", "s-3", status="DEPRECATED"))
    assert loaded.conflicts == {f"{CLS}#a": ["m1", "m2"]}


@pytest.mark.parametrize("name", ["kart?token=FAKE-TOKEN-444", "password=FAKE-PASS-555", "kartNo=KART-SENTETIK-111"])
def test_sensitive_identifier_is_rejected_without_echoing_value(name):
    with pytest.raises(MappingError) as info:
        mapping(entry("m1", name, "s"))
    text = str(info.value)
    assert "hassas değer kalıbı" in text and "FAKE" not in text and "SENTETIK" not in text


def test_free_text_fields_are_masked():
    loaded = mapping(entry("m1", "a", "s", description="not password=FAKE-PASS-555", evidence_ref="REF token=x1234"))
    blob = json.dumps(loaded.to_dict())
    assert "FAKE-PASS-555" not in blob and "x1234" not in blob and "***REDACTED***" in blob


# --- kararlı tanımlayıcı ---
def test_stable_key_matches_parser_test_id():
    [record] = records(case())
    assert record_test_key(record) == (stable_test_key(CLS, "kartPasif"), None) == (f"{CLS}#kartPasif", None)


@pytest.mark.parametrize("name, classname", [("kartPasif", None), (None, CLS)])
def test_missing_class_or_name_has_no_key(name, classname):
    [record] = records(case(name=name, classname=classname))
    assert record_test_key(record) == (None, "identifier_missing")


def test_masked_identifier_is_unstable():
    record = TestRecord(record_id="r-1", source_type=SOURCE_JUNIT_XML, dataset_kind="synthetic", test_outcome="PASS",
                        test_id=f"{CLS}#k password=FAKE-PASS-555", test_name="k password=FAKE-PASS-555")
    assert record_test_key(record) == (None, "identifier_unstable")
    assert resolve_scenario(record, mapping(entry("m1", "x", "s"))).status == "identifier_unstable"


def test_name_containing_hash_is_matched_exactly():
    [record] = records(case(name="a#b"))
    resolution = resolve_scenario(record, mapping(entry("m1", "a#b", "s")))
    assert (resolution.status, resolution.scenario_id) == ("mapping", "s")


# --- A. açık metadata ---
def test_valid_metadata_without_mapping_file():
    [record] = records(case(scenario="kart-pasif"))
    resolution = resolve_scenario(record)
    assert (resolution.status, resolution.outcome, resolution.scenario_id) == ("metadata", "resolved", "kart-pasif")
    assert resolution.sources == ("testcase_property",) and not resolution.requires_review


def test_missing_metadata_without_mapping_file():
    resolution = resolve_scenario(records(case())[0])
    assert (resolution.status, resolution.outcome, resolution.scenario_id) == ("no_source", "not_found", None)
    assert not resolution.requires_review and resolution.sources == ()


def test_invalid_metadata_is_not_replaced_by_mapping():
    [record] = records(case(scenario="geçersiz kimlik!"))
    resolution = resolve_scenario(record, mapping(entry("m1", "kartPasif", "kart-pasif")))
    assert (resolution.status, resolution.outcome, resolution.scenario_id) == ("metadata_invalid", "ambiguous", None)
    assert resolution.requires_review and resolution.mapping_ids == ("m1",)


def test_conflicting_metadata_is_not_replaced_by_mapping():
    [record] = records(case(scenario=["a-1", "a-2"]))
    resolution = resolve_scenario(record, mapping(entry("m1", "kartPasif", "a-1")))
    assert (resolution.status, resolution.outcome, resolution.scenario_id) == ("metadata_conflict", "conflict", None)


def test_repeated_identical_metadata_is_accepted():
    [record] = records(case(scenario=["a-1", "a-1"]))
    assert resolve_scenario(record).scenario_id == "a-1" and "scenario_id_repeated" in record.warnings


# --- C. çakışma ve belirsizlik ---
def test_metadata_and_mapping_agree():
    [record] = records(case(scenario="kart-pasif"))
    resolution = resolve_scenario(record, mapping(entry("m1", "kartPasif", "kart-pasif")))
    assert (resolution.status, resolution.scenario_id) == ("metadata_and_mapping", "kart-pasif")
    assert resolution.sources == ("testcase_property", "mapping_file") and not resolution.requires_review


def test_metadata_and_mapping_disagree_no_id_is_chosen():
    [record] = records(case(scenario="kart-pasif"))
    resolution = resolve_scenario(record, mapping(entry("m1", "kartPasif", "kart-aktif")))
    assert (resolution.status, resolution.outcome, resolution.scenario_id) == \
        ("metadata_mapping_conflict", "conflict", None)
    assert resolution.candidate_scenario_ids == ("kart-aktif", "kart-pasif") and resolution.requires_review


def test_multiple_active_mappings_no_id_is_chosen():
    [record] = records(case())
    resolution = resolve_scenario(record, mapping(entry("m2", "kartPasif", "s-b"), entry("m1", "kartPasif", "s-a")))
    assert (resolution.status, resolution.scenario_id, resolution.mapping_ids) == \
        ("mapping_conflict", None, ("m1", "m2"))
    [record] = records(case(scenario="s-a"))  # metadata adaylardan biriyle aynı olsa bile seçilmez
    assert resolve_scenario(record, mapping(entry("m1", "kartPasif", "s-a"),
                                            entry("m2", "kartPasif", "s-b"))).status == "mapping_conflict"


def test_mapping_not_found_and_deprecated_only():
    [record] = records(case())
    assert resolve_scenario(record, mapping(entry("m1", "baska", "s"))).status == "not_mapped"
    resolution = resolve_scenario(record, mapping(entry("m1", "kartPasif", "s", status="DEPRECATED")))
    assert (resolution.status, resolution.scenario_id, resolution.deprecated_mapping_ids) == \
        ("deprecated_only", None, ("m1",))


def test_deprecated_mapping_does_not_conflict_with_metadata():
    [record] = records(case(scenario="yeni"))
    resolution = resolve_scenario(record, mapping(entry("m1", "kartPasif", "eski", status="DEPRECATED")))
    assert (resolution.status, resolution.scenario_id) == ("metadata", "yeni")


def test_no_identifier_derivation_from_suite_name():
    [record] = records(case(classname=None))
    assert record.suite_name == CLS  # N3 suite adını yazar; eşleme bunu sınıf adı yerine kullanmamalı
    resolution = resolve_scenario(record, mapping(entry("m1", "kartPasif", "s")))
    assert (resolution.status, resolution.outcome, resolution.scenario_id) == ("identifier_missing", "ambiguous", None)


def test_no_derivation_from_names_even_if_they_equal_a_scenario():
    [record] = records(case(name="kart-pasif", classname="kart-pasif"))
    assert resolve_scenario(record, mapping(entry("m1", "baska", "kart-pasif"))).scenario_id is None


# --- kayıtlara uygulama ---
def test_apply_without_mapping_leaves_records_untouched():
    original = records(case(scenario="a"), case(name="b"))
    out, resolutions = apply_scenario_mapping(original, None)
    assert out == original and [r.status for r in resolutions] == ["metadata", "no_source"]


def test_apply_sets_resolved_id_and_marks_conflicts_for_classifier():
    original = records(case(name="a"), case(name="b", scenario="m-b"), case(name="c"))
    out, _ = apply_scenario_mapping(original, mapping(entry("m1", "a", "s-a"), entry("m2", "b", "s-b")))
    assert [r.scenario_id for r in out] == ["s-a", None, None]
    assert "scenario_resolution:mapping" in out[0].warnings
    assert {"scenario_resolution:metadata_mapping_conflict", "scenario_id_conflict"} <= set(out[1].warnings)
    assert "scenario_resolution:not_mapped" in out[2].warnings and "scenario_id_conflict" not in out[2].warnings
    assert [r.test_outcome for r in out] == [r.test_outcome for r in original]


def test_resolution_is_independent_of_mapping_entry_order():
    entries = [entry(f"m{i}", n, s) for i, (n, s) in enumerate([("a", "s-a"), ("b", "s-b1"), ("b", "s-b2"),
                                                                 ("c", "s-c")])]
    recs = records(case(name="a"), case(name="b"), case(name="c", scenario="s-x"), case(name="d"))
    expected = [r.to_dict() for r in apply_scenario_mapping(recs, mapping(*entries))[1]]
    for seed in range(5):
        shuffled = entries[:]
        random.Random(seed).shuffle(shuffled)
        assert [r.to_dict() for r in apply_scenario_mapping(recs, mapping(*shuffled))[1]] == expected
