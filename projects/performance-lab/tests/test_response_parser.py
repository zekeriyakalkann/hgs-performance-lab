"""response_parser.py birim testleri: biçimler, kurallar, sınırlar, bozuk girdi ve gizlilik (ağ yok).

Tüm kişisel/gizli değerler sentetiktir.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from hgs2_lab import response_parser
from hgs2_lab.response_parser import (
    MAX_PARSE_BYTES,
    RECOGNIZED_BUSINESS_OUTCOMES,
    STATE_EMPTY,
    STATE_JSON,
    STATE_MALFORMED_JSON,
    STATE_NO_RESPONSE,
    STATE_NOT_CAPTURED,
    STATE_TEXT,
    STATE_TOO_LARGE,
    STATE_UNDECODABLE,
    STATE_UNSUPPORTED,
    ParsedResponse,
    parse_response,
)

KART, OGR, TOKEN = "KART-SENTETIK-111", "OGR-SENTETIK-222", "FAKE-TOKEN-444"
TEXT = "text/plain;charset=UTF-8"
JSON = "application/json"


def p(body, content_type=TEXT, status=200):
    return parse_response(status, content_type, body)


@pytest.mark.parametrize("token", sorted(RECOGNIZED_BUSINESS_OUTCOMES))
def test_plain_text_tokens(token):
    r = p(token.encode())
    assert (r.business_outcome, r.rule_id, r.body_state, r.parseable) == (token, "R-TEXT-TOKEN", STATE_TEXT, True)
    assert r.media_type == "text/plain" and r.status_code == 200 and r.body_bytes == len(token)
    assert r.warnings == ()


@pytest.mark.parametrize("body", [b"  REDDEDILDI\r\n", b"reddedildi", b"\xef\xbb\xbfREDDEDILDI", b"Reddedildi\n"])
def test_text_token_ignores_case_whitespace_and_bom(body):
    assert p(body).business_outcome == "REDDEDILDI"


@pytest.mark.parametrize("body", [b"ISLEM REDDEDILDI", b"REDDEDILDI.", b"OK!", b"synthetic ok", b"hello", b"ONAY"])
def test_unrecognized_text_is_not_matched_by_substring(body):
    r = p(body)
    assert r.business_outcome is None and r.rule_id == "R-TEXT-UNRECOGNIZED" and r.parseable
    assert r.warnings == ("business_outcome_not_recognized",)


def test_json_string_and_top_level_field():
    s = p(b'"REDDEDILDI"', JSON)
    assert (s.business_outcome, s.rule_id, s.body_state) == ("REDDEDILDI", "R-JSON-STRING", STATE_JSON)
    f = p(json.dumps({"business_outcome": "onaylandi", "deviceId": 3}).encode(), "application/json; charset=utf-8")
    assert (f.business_outcome, f.rule_id) == ("ONAYLANDI", "R-JSON-FIELD")
    vendor = p(b'{"business_outcome": "HATA"}', "application/problem+json")
    assert vendor.business_outcome == "HATA"


@pytest.mark.parametrize(
    "body, warning",
    [
        ({"sonuc": "REDDEDILDI"}, "business_outcome_not_found"),  # eşanlamlı alan aranmaz
        ({"data": {"business_outcome": "REDDEDILDI"}}, "business_outcome_not_found"),  # iç içe aranmaz
        ([{"business_outcome": "REDDEDILDI"}], "business_outcome_not_found"),  # liste
        ({"business_outcome": "BILINMEYEN"}, "business_outcome_field_unrecognized"),
        ({"business_outcome": 1}, "business_outcome_field_unrecognized"),
        ("ISLEM REDDEDILDI", "business_outcome_not_found"),
        (None, "business_outcome_not_found"),
    ],
)
def test_json_without_supported_outcome(body, warning):
    r = p(json.dumps(body).encode(), JSON)
    assert r.business_outcome is None and r.rule_id == "R-JSON-UNRECOGNIZED" and r.parseable
    assert warning in r.warnings


@pytest.mark.parametrize("body", [b"{", b'{"business_outcome": "REDD', b"not json", b"[1,]", b"\x00"])
def test_malformed_json_is_a_warning_not_a_failure(body):
    r = p(body, JSON)
    assert (r.business_outcome, r.rule_id, r.body_state, r.parseable) == (
        None, "R-MALFORMED-JSON", STATE_MALFORMED_JSON, False)
    assert r.status_code == 200  # HTTP durumu ayrı korunur
    assert "malformed_json" in r.warnings


def test_empty_body():
    r = p(b"")
    assert (r.body_state, r.rule_id, r.body_bytes, r.business_outcome) == (STATE_EMPTY, "R-EMPTY-BODY", 0, None)
    assert r.warnings == ("empty_body",) and r.media_type == "text/plain"


def test_body_not_captured_and_no_response():
    assert p(None).body_state == STATE_NOT_CAPTURED and p(None).rule_id == "R-BODY-NOT-CAPTURED"
    none = parse_response(None, None, None, response_received=False)
    assert (none.body_state, none.rule_id, none.status_code, none.warnings) == (
        STATE_NO_RESPONSE, "R-NO-RESPONSE", None, ())


@pytest.mark.parametrize("content_type", ["text/html", "application/octet-stream", "image/png", "application/xml"])
def test_unsupported_content_types(content_type):
    r = p(b"REDDEDILDI", content_type)
    assert (r.body_state, r.rule_id, r.business_outcome) == (STATE_UNSUPPORTED, "R-UNSUPPORTED-TYPE", None)
    assert "unsupported_content_type" in r.warnings and r.media_type == content_type


def test_missing_content_type_uses_text_rules_with_warning():
    r = p(b"REDDEDILDI", None)
    assert r.business_outcome == "REDDEDILDI" and r.media_type is None and "content_type_missing" in r.warnings


@pytest.mark.parametrize("content_type", ["garbage", "text/", "text/plain/extra", "x" * 200, 12])
def test_invalid_content_type_header_is_safe(content_type):
    r = p(b"REDDEDILDI", content_type)
    assert r.media_type is None and "content_type_invalid" in r.warnings
    assert r.business_outcome == "REDDEDILDI"  # medya türü bilinmiyorsa düz metin kuralları (uyarıyla)


def test_charsets():
    assert p("ONAYLANDI".encode("latin-1"), "text/plain; Charset=ISO-8859-1").business_outcome == "ONAYLANDI"
    assert p("REDDEDİLDİ".encode("utf-8")).business_outcome is None  # Türkçe İ farklı bir değerdir; uydurulmaz
    assert p("HATA".encode("utf-16"), "text/plain; charset=utf-16").business_outcome == "HATA"
    unknown = p(b"HATA", "text/plain; charset=x-yok")
    assert (unknown.body_state, unknown.rule_id) == (STATE_UNDECODABLE, "R-UNDECODABLE")
    assert "unknown_charset" in unknown.warnings
    bad = p(b"\xff\xfeHATA\xff", "text/plain; charset=utf-8")
    assert bad.body_state == STATE_UNDECODABLE and "body_decode_error" in bad.warnings
    assert p(b"HATA", "text/plain; charset=rot13").body_state == STATE_UNDECODABLE  # metin olmayan codec


def test_size_limit_boundary():
    at_limit = b"REDDEDILDI" + b" " * (MAX_PARSE_BYTES - len(b"REDDEDILDI"))
    assert len(at_limit) == MAX_PARSE_BYTES and p(at_limit).business_outcome == "REDDEDILDI"
    over = at_limit + b" "
    r = p(over)
    assert (r.body_state, r.rule_id, r.business_outcome, r.parseable) == (STATE_TOO_LARGE, "R-TOO-LARGE", None, False)
    assert r.body_bytes == MAX_PARSE_BYTES + 1 and "body_too_large_not_parsed" in r.warnings


def test_size_limit_is_module_constant(monkeypatch):
    monkeypatch.setattr(response_parser, "MAX_PARSE_BYTES", 4)
    assert p(b"HATA").business_outcome == "HATA" and p(b"HATA ").rule_id == "R-TOO-LARGE"


@pytest.mark.parametrize("status, warnings", [(99, {"invalid_status_code"}), (600, {"invalid_status_code"}),
                                              (True, {"invalid_status_code"}), ("200", {"invalid_status_code"}),
                                              (None, {"status_code_missing"})])
def test_invalid_or_missing_status_code_is_reported_and_body_still_parsed(status, warnings):
    r = p(b"HATA", status=status)
    assert r.status_code is None and warnings <= set(r.warnings) and r.business_outcome == "HATA"


@pytest.mark.parametrize("body", ["REDDEDILDI", 123, ["x"], object()])
def test_non_bytes_body_never_raises(body):
    r = p(body)
    assert r.body_state == STATE_NOT_CAPTURED and r.business_outcome is None


def test_random_bytes_never_raise():
    rng = random.Random(20261026)
    for _ in range(500):
        body = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 64)))
        ctype = rng.choice([TEXT, JSON, None, "text/html", "application/json; charset=utf-16"])
        r = p(body, ctype)
        assert r.business_outcome in RECOGNIZED_BUSINESS_OUTCOMES | {None}


def test_summary_never_contains_body_content():
    bodies = [
        (json.dumps({"business_outcome": "REDDEDILDI", "kartNo": KART, "ogrenciNo": OGR}).encode(), JSON),
        (json.dumps({"token": TOKEN, "kartNo": KART}).encode(), JSON),
        (f"kartNo={KART}&ogrenciNo={OGR}".encode(), TEXT),
        (f'{{"kartNo": "{KART}"'.encode(), JSON),
        (f"<p>{KART}</p>".encode(), "text/html"),
        (((KART + " ") * 1000).encode(), TEXT),
    ]
    for body, ctype in bodies:
        text = json.dumps(p(body, ctype).to_dict())
        assert KART not in text and OGR not in text and TOKEN not in text


def test_dict_round_trip_and_validation():
    for r in (p(b"REDDEDILDI"), p(b"{", JSON), p(b""), parse_response(None, None, None, response_received=False),
              p(b"x", "text/plain; charset=x-yok", status=99)):
        assert ParsedResponse.from_dict(r.to_dict()) == r
    good = p(b"HATA").to_dict()
    for key, bad in [("business_outcome", f"kartNo={KART}"), ("rule_id", "R-X"), ("body_state", "x"),
                     ("status_code", 700), ("media_type", "kart/" + KART + "!"), ("warnings", ["Bad Code"]),
                     ("body_bytes", -1), ("parseable", "yes")]:
        with pytest.raises(ValueError) as info:
            ParsedResponse.from_dict({**good, key: bad})
        assert KART not in str(info.value)
    with pytest.raises(ValueError):
        ParsedResponse.from_dict({"rule_id": "R-TEXT-TOKEN"})
    with pytest.raises(ValueError):
        ParsedResponse.from_dict(["x"])


def test_parser_module_does_not_import_network_code():
    root = Path(__file__).resolve().parents[1]
    code = ("import sys; import hgs2_lab.response_parser, hgs2_lab.result_analysis; bad = sorted(m for m in "
            "('requests', 'urllib3', 'socket', 'http.client', 'hgs2_lab.http_transport', 'hgs2_lab.execution', "
            "'hgs2_lab.robust_z', 'hgs2_lab.detection') if m in sys.modules); print(bad)")
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                          check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"
