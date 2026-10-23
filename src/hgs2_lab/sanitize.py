"""Hassas değerlerin sonuçlara ve metadata'ya sızmasını önleyen maskeleme yardımcıları.

* Anahtar adı hassas görünen (büyük/küçük harf duyarsız) değerler maskelenir:
  token, access_token, api_key, apikey, password, passwd, secret, authorization, ...
* URL'lerde yalnızca hassas sorgu parametrelerinin DEĞERİ değişir; path, diğer
  parametreler ve kodlamaları bayt bayt korunur.
* Serbest metinde (ör. requests hata mesajları) `anahtar=değer` kalıpları,
  URL'deki kullanıcı bilgisi parolası ve çağıranın bildirdiği bilinen gizli
  değerler maskelenir.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from urllib.parse import unquote_plus

REDACTED = "***REDACTED***"

SENSITIVE_KEY_RE = re.compile(
    r"(auth|bearer|cookie|token|secret|passw|pwd|api[-_]?key|access[-_]?key|private[-_]?key"
    r"|credential|session|signature|^key$|^sig$)",
    re.IGNORECASE,
)
# Bu uzunluktan kısa "gizli" değerler metinde birebir aranmaz (ör. "1" her yeri maskelerdi).
_MIN_LITERAL_SECRET_LEN = 4

_KEY_VALUE_RE = re.compile(r"(?P<key>[A-Za-z0-9_.~%+\-]+)=(?P<value>[^&\s#'\"<>)]*)")
_USERINFO_PASSWORD_RE = re.compile(r"(?P<prefix>://[^/\s:@]+:)[^@\s/]+@")


def is_sensitive_key(name: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(name))


def _query_pairs(query: str) -> list[tuple[str, str, str]]:
    """(ham anahtar, '=' ya da '', ham değer) üçlüleri; sıra ve kodlama korunur."""
    return [piece.partition("=") for piece in query.split("&")]


def _sanitize_query(query: str) -> str:
    pieces = []
    for key, eq, value in _query_pairs(query):
        if eq and value and is_sensitive_key(unquote_plus(key)):
            value = REDACTED
        pieces.append(f"{key}{eq}{value}")
    return "&".join(pieces)


def sanitize_url(url: str) -> str:
    """Mutlak ya da göreli URL'deki hassas sorgu değerlerini ve kullanıcı bilgisi parolasını maskeler."""
    url = _USERINFO_PASSWORD_RE.sub(rf"\g<prefix>{REDACTED}@", url)
    base, question, rest = url.partition("?")
    if not question:
        return url
    query, hash_, fragment = rest.partition("#")
    return f"{base}?{_sanitize_query(query)}{hash_}{fragment}"


def sensitive_values(headers: Mapping[str, str], url: str) -> list[str]:
    """Bir istekte geçen, metinlerde birebir maskelenmesi gereken gizli değerler."""
    found: set[str] = set()
    for name, value in headers.items():
        if is_sensitive_key(name):
            found.add(value)
            scheme, space, credential = value.partition(" ")  # "Bearer <değer>" biçimi
            if space:
                found.add(credential)
    _, question, rest = url.partition("?")
    if question:
        for key, eq, value in _query_pairs(rest.partition("#")[0]):
            if eq and value and is_sensitive_key(unquote_plus(key)):
                found.update({value, unquote_plus(value)})
    return sorted((v for v in found if len(v) >= _MIN_LITERAL_SECRET_LEN), key=len, reverse=True)


def _mask_key_value(match: re.Match[str]) -> str:
    key, value = match.group("key"), match.group("value")
    if value and is_sensitive_key(unquote_plus(key)):
        return f"{key}={REDACTED}"
    return match.group(0)


def sanitize_text(text: str, secrets: Iterable[str] = ()) -> str:
    """Serbest metindeki bilinen gizli değerleri, hassas anahtar=değer kalıplarını ve URL parolalarını maskeler."""
    for secret in sorted(set(secrets), key=len, reverse=True):
        if len(secret) >= _MIN_LITERAL_SECRET_LEN:
            text = text.replace(secret, REDACTED)
    text = _USERINFO_PASSWORD_RE.sub(rf"\g<prefix>{REDACTED}@", text)
    return _KEY_VALUE_RE.sub(_mask_key_value, text)
