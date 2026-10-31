"""Taşıyıcı sözleşmesi: runner'ın ağ katmanından beklediği arayüz ve istisnalar.

Gerçek taşıyıcı `http_transport.RequestsTransport`'tur (requests tabanlı).
Her taşıyıcı, kendi kütüphanesinin hatalarını aşağıdaki istisnalara
çevirmelidir; başka istisnalar runner tarafından yutulmaz (programlama hatası
sayılır).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .models import ERROR_CONNECTION, ERROR_TIMEOUT, ERROR_TRANSPORT
from .scenarios import Scenario


class TransportError(Exception):
    """HTTP yanıtı alınamadı (sınıflandırılamayan taşıma hatası)."""

    error_type = ERROR_TRANSPORT


class TransportTimeout(TransportError):
    """İstek zaman aşımına uğradı."""

    error_type = ERROR_TIMEOUT


class TransportConnectionError(TransportError):
    """Sunucuyla bağlantı kurulamadı veya kesildi."""

    error_type = ERROR_CONNECTION


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    size_bytes: int | None = None
    # Taşıyıcının kendi ölçtüğü HTTP süresi (ör. requests'in response.elapsed).
    # Verilmezse runner, ölçtüğü elapsed_ms değerini kullanır.
    duration_ms: float | None = None
    # Ham yanıt gövdesi (çözülmüş, bkz. README). Runner yalnızca iş sonucunu ayrıştırmak için okur
    # (response_parser.py); gövdenin kendisi hiçbir kayda yazılmaz.
    body: bytes | None = field(default=None, repr=False)
    # Yanıtın Content-Type başlığı (yoksa None); yalnızca gövde ayrıştırmada kullanılır.
    content_type: str | None = None


class Transport(Protocol):
    def send(self, scenario: Scenario, url: str, timeout_seconds: float) -> TransportResponse:
        """İsteği gönderir. HTTP yanıtı alınırsa (500 dahil) TransportResponse döndürür.

        Yanıt alınamazsa TransportTimeout / TransportConnectionError / TransportError fırlatır.
        """
        ...
