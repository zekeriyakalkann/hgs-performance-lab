"""sanitize.py testleri. Tüm gizli ve kişisel değerler sahtedir/sentetiktir."""

import json

import pytest

from hgs2_lab.sanitize import (
    REDACTED,
    is_sensitive_key,
    sanitize_data,
    sanitize_form,
    sanitize_json_text,
    sanitize_text,
    sanitize_url,
    sensitive_values,
)

FAKE = "FAKE-SECRET-123"


@pytest.mark.parametrize(
    "key",
    ["token", "access_token", "api_key", "apikey", "API-KEY", "password", "passwd", "secret",
     "authorization", "Authorization", "TOKEN", "client_secret", "refresh_token", "pwd", "key", "sig",
     "signature", "x-auth-token", "session_id"],
)
def test_sensitive_keys_case_insensitive(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", ["page", "size", "q", "sort", "id", "keyword", "user", "lang", "timeout"])
def test_non_sensitive_keys(key):
    assert not is_sensitive_key(key)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://h/x", "http://h/x"),
        ("http://h/x?page=2&size=10", "http://h/x?page=2&size=10"),
        (f"http://h/x?token={FAKE}", f"http://h/x?token={REDACTED}"),
        (f"http://h/x?page=2&API_KEY={FAKE}&q=a%20b", f"http://h/x?page=2&API_KEY={REDACTED}&q=a%20b"),
        (f"/x?Password={FAKE}&access_token={FAKE}#frag", f"/x?Password={REDACTED}&access_token={REDACTED}#frag"),
        (f"/x?%74oken={FAKE}", f"/x?%74oken={REDACTED}"),  # kodlanmış anahtar adı
        ("/x?token=", "/x?token="),  # boş değer olduğu gibi kalır
        ("/x?token&page=1", "/x?token&page=1"),  # değersiz anahtar olduğu gibi kalır
        ("/x?a=1&a=2&b", "/x?a=1&a=2&b"),  # sıra, tekrar ve kodlama korunur
        (f"http://user:{FAKE}@h/x", f"http://user:{REDACTED}@h/x"),
    ],
)
def test_sanitize_url(url, expected):
    assert sanitize_url(url) == expected


def test_sanitize_url_is_idempotent():
    once = sanitize_url(f"/x?token={FAKE}&page=1")
    assert sanitize_url(once) == once


def test_sanitize_text_masks_requests_style_error_messages():
    message = (
        f"HTTPConnectionPool(host='127.0.0.1', port=8080): Max retries exceeded with url: "
        f"/x?page=1&apikey={FAKE} (Caused by NewConnectionError('...'))"
    )
    cleaned = sanitize_text(message)
    assert FAKE not in cleaned
    assert f"apikey={REDACTED}" in cleaned
    assert "host='127.0.0.1', port=8080" in cleaned and "page=1" in cleaned  # hassas olmayanlar korunur


def test_sanitize_text_masks_known_literal_secrets_and_userinfo():
    message = f"failed: header Bearer {FAKE} for http://u:{FAKE}2@h/x read timeout=1.0"
    cleaned = sanitize_text(message, [FAKE, f"{FAKE}2"])
    assert FAKE not in cleaned
    assert "read timeout=1.0" in cleaned


def test_sanitize_text_ignores_too_short_literal_secrets():
    assert sanitize_text("abc 1 def", ["1"]) == "abc 1 def"


def test_sensitive_values_from_headers_and_query():
    values = sensitive_values(
        {"Authorization": f"Bearer {FAKE}", "X-Api-Key": f"{FAKE}K", "Accept": "application/json"},
        f"http://h/x?page=2&token={FAKE}T&secret=a%2Fb%2Fc%2Fd",
    )
    assert f"Bearer {FAKE}" in values and FAKE in values
    assert f"{FAKE}K" in values and f"{FAKE}T" in values
    assert "a%2Fb%2Fc%2Fd" in values and "a/b/c/d" in values  # ham ve çözülmüş biçim
    assert "application/json" not in values and "2" not in values
    assert values == sorted(values, key=len, reverse=True)  # uzun değerler önce maskelenir


# --- N1: HGS2 kişisel parametreleri, bağlantı dizeleri ve yapılandırılmış veri (tüm değerler sentetik) ---
KART, OGR, PARMAK = "KART-SENTETIK-111", "OGR-SENTETIK-222", "PARMAK-SENTETIK-333"
SYNTHETIC_SECRETS = (KART, OGR, PARMAK, FAKE)


def assert_no_secret(text):
    leaked = [s for s in SYNTHETIC_SECRETS if s in text]
    assert not leaked, "maskelenmemiş sentetik değer kaldı"


@pytest.mark.parametrize(
    "key",
    ["kartNo", "KARTNO", "kartno", "kart_no", "Kart-No", "kartNumarasi", "cardNumber", "card_no",
     "ogrenciNo", "OGRENCINO", "ogrenci_no", "öğrenciNo", "ÖĞRENCİNO", "studentId", "student_number",
     "parmakIzi", "PARMAKIZI", "parmak_izi", "parmakIziId", "fingerprint", "fingerPrintTemplate", "biometricData",
     "biyometri", "tcKimlikNo", "tckn", "kimlikNo", "national_id",
     "connectionString", "connection_str", "dsn", "jdbcUrl", "spring.datasource.url", "DATABASE_URL",
     "set-cookie", "Cookie", "refresh_token", "X-Api-Key"],
)
def test_personal_and_connection_keys_are_sensitive(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize(
    "key",
    ["deviceId", "kartTipi", "ogrenciSayisi", "parmakSayisi", "kimlikDogrulama", "cardinality", "classname",
     "studentCount", "durum", "girisYontemi", "sonuc", "aciklama", "url", "message"],
)
def test_lookalike_keys_are_not_sensitive(key):
    assert not is_sensitive_key(key)


@pytest.mark.parametrize(
    "url, expected",
    [
        (f"/api/auth/kart-okut?kartNo={KART}&deviceId=3", f"/api/auth/kart-okut?kartNo={REDACTED}&deviceId=3"),
        (f"/api/auth/numara-okut?OGRENCINO={OGR}&deviceId=3", f"/api/auth/numara-okut?OGRENCINO={REDACTED}&deviceId=3"),
        (f"/x?parmakIzi={PARMAK}&parmakIzi={PARMAK}", f"/x?parmakIzi={REDACTED}&parmakIzi={REDACTED}"),  # tekrar
        (f"/x?%C3%B6%C4%9FrenciNo={OGR}", f"/x?%C3%B6%C4%9FrenciNo={REDACTED}"),  # kodlanmış Türkçe anahtar
        (f"/x?kart%4Eo={KART}", f"/x?kart%4Eo={REDACTED}"),  # kodlanmış anahtar
        ("/x?kartNo=&deviceId=3", "/x?kartNo=&deviceId=3"),  # boş değer
        ("/x?kartTipi=MIFARE", "/x?kartTipi=MIFARE"),  # benzer ama hassas olmayan
    ],
)
def test_sanitize_url_masks_hgs2_personal_parameters(url, expected):
    assert sanitize_url(url) == expected


# N11: HGS2 TerminalEnrollmentController parametreleri (eskiNo/yeniNo öğrenci numarası, slot parmak izi slotu)
@pytest.mark.parametrize("key", ["eskiNo", "yeniNo", "ESKINO", "yeni_no", "eskiNumara", "slot", "SLOT", "fpSlot",
                                 "fp_slot", "slotId", "slot_no"])
def test_hgs2_terminal_keys_are_sensitive(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", ["timeslot", "slots", "slotCount", "eskiNot", "yenilik", "noSlot", "deviceSlotType"])
def test_hgs2_terminal_lookalike_keys_are_not_sensitive(key):
    assert not is_sensitive_key(key)


def test_sanitize_url_masks_hgs2_terminal_parameters():
    url = f"/api/terminal/ogrenci-no-degistir?deviceId=1&eskiNo={OGR}&yeniNo={OGR}2"
    assert sanitize_url(url) == f"/api/terminal/ogrenci-no-degistir?deviceId=1&eskiNo={REDACTED}&yeniNo={REDACTED}"
    url = f"/api/terminal/parmak-kaydet?deviceId=1&ogrenciNo={OGR}&slot=17"
    assert sanitize_url(url) == f"/api/terminal/parmak-kaydet?deviceId=1&ogrenciNo={REDACTED}&slot={REDACTED}"
    assert sanitize_text(f"hata: eskiNo={OGR} slot=17") == f"hata: eskiNo={REDACTED} slot={REDACTED}"


def test_sanitize_form_masks_values_and_keeps_encoding():
    body = f"kartNo={KART}&deviceId=3&KARTNO={KART}&parmak_izi={PARMAK}&q=a+b&ogrenciNo=O%C4%9E-{OGR}"
    cleaned = sanitize_form(body)
    assert_no_secret(cleaned)
    assert cleaned == (f"kartNo={REDACTED}&deviceId=3&KARTNO={REDACTED}&parmak_izi={REDACTED}&q=a+b"
                       f"&ogrenciNo={REDACTED}")


def test_sanitize_data_masks_nested_objects_and_lists_without_mutating_input():
    data = {
        "kullanici": {"kartNo": KART, "OgrenciNo": OGR, "ad": "Deneme", "deviceId": 3},
        "kayitlar": [{"parmakIzi": [PARMAK, PARMAK]}, {"parmakIzi": {"slot": 7, "sablon": PARMAK}}],
        "not": f"gonderilen kartNo={KART}",
        "bos": {"kartNo": None, "ogrenciNo": ""},
        "sayilar": [1, 2.5, True, None],
    }
    original = json.loads(json.dumps(data))
    cleaned = sanitize_data(data)
    assert data == original  # girdi değişmez
    assert_no_secret(json.dumps(cleaned, ensure_ascii=False))
    assert cleaned["kullanici"] == {"kartNo": REDACTED, "OgrenciNo": REDACTED, "ad": "Deneme", "deviceId": 3}
    assert cleaned["kayitlar"] == [{"parmakIzi": REDACTED}, {"parmakIzi": REDACTED}]  # değer bütünüyle
    assert cleaned["not"] == f"gonderilen kartNo={REDACTED}"
    assert cleaned["bos"] == {"kartNo": None, "ogrenciNo": ""}  # gizlenecek değer yok
    assert cleaned["sayilar"] == [1, 2.5, True, None]


@pytest.mark.parametrize("bad", [b"kartNo=1", object(), {1, 2}, {1: "x"}])
def test_sanitize_data_rejects_unsupported_types_without_echoing_value(bad):
    with pytest.raises(TypeError) as info:
        sanitize_data({"a": bad})
    assert "kartNo=1" not in str(info.value)


@pytest.mark.parametrize("func", [sanitize_text, sanitize_url, sanitize_form, sanitize_json_text])
def test_text_functions_reject_non_text_without_echoing_value(func):
    with pytest.raises(TypeError) as info:
        func(12345678901)
    assert "12345678901" not in str(info.value)


def test_sanitize_json_text_uses_structure_and_falls_back_on_malformed_json():
    text = json.dumps({"ogrenci": {"ogrenciNo": OGR, "liste": [{"kartNo": KART}]}, "durum": "REDDEDILDI"})
    cleaned = sanitize_json_text(text)
    assert_no_secret(cleaned)
    assert json.loads(cleaned) == {"ogrenci": {"ogrenciNo": REDACTED, "liste": [{"kartNo": REDACTED}]},
                                   "durum": "REDDEDILDI"}
    broken = f'{{"kartNo": "{KART}", "parmakIzi": {PARMAK}, '  # bozuk JSON: metin kurallarına düşer
    assert_no_secret(sanitize_json_text(broken))
    assert sanitize_json_text("") == ""


@pytest.mark.parametrize(
    "line",
    [
        f"2026-10-26T10:00:00.000+03:00  INFO 1 --- [hgs] [main] c.e.AuthController : kartNo={KART} deviceId=3",
        f'istek govdesi {{"kartNo": "{KART}", "ogrenciNo": "{OGR}"}}',
        f"istek govdesi {{'parmakIzi': '{PARMAK}'}}",  # Python repr biçimi
        f"OgrenciNo: {OGR} kayitli degil",
        f"parmakIzi: {PARMAK}",
        f"User{{kartNo={KART}, ogrenciNo={OGR}}}",  # Java toString
        f"kartNo=\"{KART} 2\" ogrenciNo='{OGR} 3'",  # tırnaklı ve boşluklu değer
        f"Authorization: Bearer {FAKE}",
        f"Cookie: JSESSIONID={FAKE}",
        f"Set-Cookie: SESSION={FAKE}; Path=/",
        f"jdbc:postgresql://db.example.invalid:5432/hgs?user=fake&password={FAKE}",
        f"postgresql://fake:{FAKE}@db.example.invalid/hgs",
        f"spring.datasource.password={FAKE}",
    ],
)
def test_sanitize_text_masks_log_lines_bodies_headers_and_connection_strings(line):
    cleaned = sanitize_text(line)
    assert_no_secret(cleaned)
    assert REDACTED in cleaned
    assert sanitize_text(cleaned) == cleaned  # idempotent


def test_sanitize_text_keeps_exception_class_names_and_line_numbers():
    trace = ("org.springframework.security.authentication.BadCredentialsException: Bad credentials\n"
             "\tat com.example.TokenService.check(TokenService.java:45)\n"
             "Caused by: java.net.ConnectException: Connection refused")
    assert sanitize_text(trace) == trace


def test_sanitize_text_masks_secrets_inside_stack_trace():
    trace = (f"java.lang.IllegalArgumentException: gecersiz kartNo={KART}\n"
             f"\tat com.example.UserService.kaydet(UserService.java:12)\n"
             f"Caused by: java.sql.SQLException: jdbc:postgresql://h/db?password={FAKE}")
    cleaned = sanitize_text(trace)
    assert_no_secret(cleaned)
    assert "UserService.java:12" in cleaned and "java.lang.IllegalArgumentException" in cleaned


def test_metadata_snapshot_masks_hgs2_body_fields():
    from hgs2_lab.metadata import scenario_snapshot
    from hgs2_lab.scenarios import Scenario

    scenario = Scenario(name="kart", method="POST", path=f"/api/auth/kart-okut?kartNo={KART}&deviceId=3",
                        body={"kartNo": KART, "cihaz": {"deviceId": 3, "parmakIzi": PARMAK}})
    snapshot = scenario_snapshot(scenario)
    assert_no_secret(json.dumps(snapshot, ensure_ascii=False))
    assert snapshot["body"]["cihaz"] == {"deviceId": 3, "parmakIzi": REDACTED}
