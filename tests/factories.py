"""Testler için ortak yardımcılar (ağ erişimi yok)."""

from hgs2_lab.models import RawResult


def make_result(**overrides) -> RawResult:
    """HTTP yanıtı alınmış (varsayılan: 200) bir kayıt."""
    base = dict(
        run_id="r1",
        seq=1,
        scenario="s",
        iteration=1,
        warmup=False,
        method="GET",
        url="http://h/p",
        started_at="2026-01-01T00:00:00+00:00",
        offset_ms=0.0,
        elapsed_ms=12.5,
        duration_ms=12.0,
        status_code=200,
        http_ok=True,
        response_bytes=10,
    )
    base.update(overrides)
    return RawResult(**base)


def make_failed_result(**overrides) -> RawResult:
    """HTTP yanıtı alınamamış (varsayılan: timeout) bir kayıt."""
    base = dict(
        run_id="r1",
        seq=2,
        scenario="s",
        iteration=2,
        warmup=False,
        method="GET",
        url="http://h/p",
        started_at="2026-01-01T00:00:01+00:00",
        offset_ms=12.5,
        elapsed_ms=30.0,
        duration_ms=None,
        status_code=None,
        http_ok=None,
        error_type="timeout",
        error="TransportTimeout: zaman aşımı",
    )
    base.update(overrides)
    return RawResult(**base)
