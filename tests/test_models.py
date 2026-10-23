import pytest
from factories import make_failed_result, make_result

from hgs2_lab.models import ERROR_TYPES, InvalidRunId, RawResult, validate_run_id
from hgs2_lab.transport import TransportConnectionError, TransportError, TransportTimeout


def test_field_order_matches_spec():
    assert RawResult.field_names() == [
        "run_id", "scenario", "iteration", "method", "url", "started_at", "elapsed_ms", "duration_ms",
        "status_code", "http_ok", "business_outcome", "error_type", "error", "response_bytes",
    ]


def test_http_500_is_a_response_not_a_transport_error():
    r = make_result(status_code=500, http_ok=False)
    assert r.has_response and not r.succeeded
    assert r.error_type is None and r.error is None


def test_transport_failure_has_no_http_fields():
    r = make_failed_result()
    assert not r.has_response and not r.succeeded
    assert r.status_code is None and r.duration_ms is None and r.http_ok is None
    assert r.elapsed_ms == 30.0


def test_succeeded_reflects_http_ok():
    assert make_result().succeeded
    assert not make_result(http_ok=False).succeeded


@pytest.mark.parametrize(
    "override",
    [
        {"error_type": "timeout"},  # yanıt var ama hata türü de var
        {"error": "x"},  # error_type olmadan error
        {"http_ok": None},  # yanıt var ama http_ok yok
        {"http_ok": 1},
        {"status_code": 99},
        {"status_code": 600},
        {"status_code": True},
        {"elapsed_ms": -1},
        {"elapsed_ms": float("nan")},
        {"duration_ms": float("inf")},
        {"iteration": 0},
        {"iteration": True},
        {"response_bytes": -1},
        {"scenario": ""},
        {"business_outcome": ""},
    ],
)
def test_inconsistent_response_record_rejected(override):
    with pytest.raises(ValueError):
        make_result(**override)


@pytest.mark.parametrize(
    "override",
    [
        {"error_type": "bogus"},
        {"error_type": None},  # yanıt yok ve hata türü yok
        {"error": None},
        {"status_code": 200},
        {"duration_ms": 1.0},
        {"http_ok": False},
        {"business_outcome": "ok"},
        {"response_bytes": 5},
    ],
)
def test_inconsistent_failure_record_rejected(override):
    with pytest.raises(ValueError):
        make_failed_result(**override)


def test_dict_roundtrip_and_strict_keys():
    r = make_failed_result()
    assert RawResult.from_dict(r.to_dict()) == r
    data = r.to_dict()
    del data["error"]
    with pytest.raises(ValueError, match="eksik"):
        RawResult.from_dict(data)
    with pytest.raises(ValueError, match="fazla"):
        RawResult.from_dict({**r.to_dict(), "success": True})


@pytest.mark.parametrize("run_id", ["r1", "run-2026_01.02", "A", "a" * 64])
def test_valid_run_ids(run_id):
    assert validate_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "run_id",
    ["", "../x", "a/b", "a\\b", ".hidden", "-x", "CON", "nul.txt", "a b", "a" * 65, "abc.", None, 5, "a:b"],
)
def test_invalid_run_ids(run_id):
    with pytest.raises(InvalidRunId):
        validate_run_id(run_id)
    with pytest.raises(InvalidRunId):
        make_result(run_id=run_id)


def test_transport_exceptions_carry_known_error_types():
    for exc in (TransportError, TransportTimeout, TransportConnectionError):
        assert exc.error_type in ERROR_TYPES
    types = {TransportError.error_type, TransportTimeout.error_type, TransportConnectionError.error_type}
    assert len(types) == 3
