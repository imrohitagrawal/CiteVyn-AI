"""Unit tests for the uniform error envelope factory."""

from __future__ import annotations

import pytest

from app.core.errors import (
    APIErrorCode,
    ErrorEnvelope,
    error_response,
    status_code_for,
)


def test_status_code_for_auth_required_is_401() -> None:
    assert status_code_for(APIErrorCode.auth_required) == 401


def test_status_code_for_validation_error_is_422() -> None:
    assert status_code_for(APIErrorCode.validation_error) == 422


def test_status_code_for_rate_limited_is_429() -> None:
    assert status_code_for(APIErrorCode.rate_limited) == 429


def test_status_code_for_internal_error_is_500() -> None:
    assert status_code_for(APIErrorCode.internal_error) == 500


def test_error_response_builds_http_exception_with_envelope() -> None:
    exc = error_response(
        request_id="req_abc",
        code=APIErrorCode.auth_required,
        message="nope",
    )

    assert exc.status_code == 401
    assert exc.headers == {"WWW-Authenticate": "Bearer"}
    detail = exc.detail
    assert isinstance(detail, dict)
    assert detail["request_id"] == "req_abc"
    assert detail["status"] == "error"
    assert detail["error"]["code"] == "auth_required"
    assert detail["error"]["message"] == "nope"


def test_error_response_details_round_trip() -> None:
    exc = error_response(
        request_id="req_xyz",
        code=APIErrorCode.validation_error,
        message="bad field",
        details={"field": "message", "reason": "too_long"},
    )

    detail = exc.detail
    assert isinstance(detail, dict)
    err = detail["error"]
    assert err["code"] == "validation_error"
    assert err["details"] == {"field": "message", "reason": "too_long"}


def test_error_envelope_model_validates_against_pydantic() -> None:
    env = ErrorEnvelope(
        request_id="req_1",
        error={"code": APIErrorCode.internal_error, "message": "boom"},
    )

    assert env.status == "error"
    assert env.error.code is APIErrorCode.internal_error


@pytest.mark.parametrize(
    "code,expected",
    [
        (APIErrorCode.auth_required, 401),
        (APIErrorCode.validation_error, 422),
        (APIErrorCode.rate_limited, 429),
        (APIErrorCode.ingestion_failed, 500),
        (APIErrorCode.evaluation_failed, 500),
        (APIErrorCode.index_unavailable, 503),
        (APIErrorCode.cost_limit_reached, 503),
        (APIErrorCode.internal_error, 500),
    ],
)
def test_status_code_mapping_is_stable(code: APIErrorCode, expected: int) -> None:
    assert status_code_for(code) == expected
