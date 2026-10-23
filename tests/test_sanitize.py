"""sanitize.py testleri. Tüm gizli değerler sahtedir."""

import pytest

from hgs2_lab.sanitize import REDACTED, is_sensitive_key, sanitize_text, sanitize_url, sensitive_values

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
