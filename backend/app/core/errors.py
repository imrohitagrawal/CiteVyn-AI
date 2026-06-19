"""Uniform error envelope for the HTTP API.

Every 4xx/5xx response in the app uses the same shape so clients can
parse errors consistently. Unsupported and no-answer answers are NOT
errors — they ride the 200 envelope with ``unsupported: true`` or
``no_answer: true`` flags. Error codes are reserved for transport-level
failures (auth, validation, ingestion, evaluation, rate limits, etc.).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel


class APIErrorCode(StrEnum):
    """Error codes from ``docs/API_SPEC.md`` §15 plus transport helpers."""

    unsupported_domain = "unsupported_domain"
    weak_evidence = "weak_evidence"
    citation_validation_failed = "citation_validation_failed"
    rate_limited = "rate_limited"
    auth_required = "auth_required"
    ingestion_failed = "ingestion_failed"
    evaluation_failed = "evaluation_failed"
    index_unavailable = "index_unavailable"
    cost_limit_reached = "cost_limit_reached"
    # Transport helpers (not in the spec, but needed to keep the envelope
    # uniform across the app).
    validation_error = "validation_error"
    not_found = "not_found"
    internal_error = "internal_error"


# Status code per error code. ``unsupported_domain`` is intentionally
# absent here because unsupported questions are returned with a 200 body
# (per docs/API_SPEC.md §6) rather than as a transport error.
_STATUS_CODE: dict[APIErrorCode, int] = {
    APIErrorCode.auth_required: 401,
    APIErrorCode.validation_error: 422,
    APIErrorCode.not_found: 404,
    APIErrorCode.rate_limited: 429,
    APIErrorCode.weak_evidence: 200,  # surfaced via no_answer flag
    APIErrorCode.citation_validation_failed: 200,  # surfaced via no_answer flag
    APIErrorCode.ingestion_failed: 500,
    APIErrorCode.evaluation_failed: 500,
    APIErrorCode.index_unavailable: 503,
    APIErrorCode.cost_limit_reached: 503,
    APIErrorCode.internal_error: 500,
}


def status_code_for(code: APIErrorCode) -> int:
    return _STATUS_CODE[code]


class ErrorDetail(BaseModel):
    code: APIErrorCode
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    request_id: str
    status: str = "error"
    error: ErrorDetail


def error_response(
    *,
    request_id: str,
    code: APIErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    """Build a :class:`HTTPException` carrying the standard envelope."""
    status = status_code_for(code)
    body = ErrorEnvelope(
        request_id=request_id,
        error=ErrorDetail(code=code, message=message, details=details),
    )
    headers: dict[str, str] = {}
    if code is APIErrorCode.auth_required:
        headers["WWW-Authenticate"] = "Bearer"
    return HTTPException(status_code=status, detail=body.model_dump(mode="json"), headers=headers)
