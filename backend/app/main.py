"""FastAPI application factory.

Wires the request-id middleware, the public + admin routers, and the
uniform error envelope. Every 4xx/5xx response flows through
:mod:`app.core.errors` so the client can parse errors with one shape.

Slice 9a adds a :class:`lifespan` context manager that:

* runs :func:`app.llm.factory.validate_llm_provider` at startup so a
  misconfigured production deploy (``CITEVYN_ENVIRONMENT=production``
  + ``CITEVYN_LLM_PROVIDER=stub``) fails at boot, not on first ask;
* closes the shared :class:`LLMClient` on shutdown so the underlying
  ``httpx.AsyncClient`` connection pool is released cleanly (the
  Slice 8 review finding: per-request construction leaked sockets).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.answer.orchestrator import OrchestratorError
from app.api.routes.admin import router as admin_router
from app.api.routes.health import router as health_router
from app.api.routes.messages import router as messages_router
from app.api.routes.search import router as search_router
from app.api.routes.sessions import router as sessions_router
from app.core.config import get_settings
from app.core.cors import configure_cors
from app.core.errors import (
    APIErrorCode,
    ErrorDetail,
    ErrorEnvelope,
    status_code_for,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware, get_current_request_id
from app.core.redis_client import shutdown_redis_client
from app.llm.factory import shutdown_llm_client, validate_llm_provider

_logger = logging.getLogger("citevyn.request")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Boot/shutdown hooks for the shared :class:`LLMClient` and prod guard.

    The prod guard raises eagerly so a deploy that ships with the
    default stub provider cannot accept traffic. The shutdown hook is
    best-effort: a failure to close the underlying httpx client is
    logged but never raised (we still want the process to exit).
    """
    settings = get_settings()
    validate_llm_provider(settings)
    _logger.info(
        "app_startup",
        extra={
            "environment": settings.environment,
            "llm_provider": settings.llm_provider,
        },
    )
    try:
        yield
    finally:
        _logger.info("app_shutdown")
        await shutdown_llm_client()
        await shutdown_redis_client()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="CiteVyn AI Backend",
        version="0.9.0",
        description=(
            "Slice 9 backend: HTTP routes for sessions, messages, "
            "search, health, and admin; wired to the Slice 4–6 "
            "answer engine, the Slice 8 ingestion worker, and the "
            "Slice 9a production ops substrate (singleton LLM "
            "client, Redis sliding-window rate limit, multi-stage "
            "Docker image, Caddy auto-TLS reverse proxy)."
        ),
        lifespan=_lifespan,
    )
    configure_cors(app, settings)
    app.add_middleware(RequestIDMiddleware)
    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(messages_router)
    app.include_router(search_router)
    app.include_router(admin_router)

    # Exception handlers are defined at module scope (below) so pyright
    # can see them as referenced symbols; the FastAPI decorator binds
    # them to the app instance.
    app.add_exception_handler(OrchestratorError, _orchestrator_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)  # type: ignore[arg-type]
    return app


def _resolve_request_id(request: Request) -> str:
    """Return the request id stamped on :class:`Request` by the middleware."""
    return str(getattr(request.state, "request_id", "") or get_current_request_id() or "")


async def _orchestrator_error_handler(request: Request, exc: OrchestratorError) -> JSONResponse:
    """Map an orchestrator failure to a 500 with the standard envelope.

    The cause string is preserved in ``error.details.reason`` so an
    SRE can correlate the HTTP response with the underlying log
    line without the client having to parse a stack trace.
    """
    envelope = ErrorEnvelope(
        request_id=_resolve_request_id(request),
        error=ErrorDetail(
            code=APIErrorCode.internal_error,
            message=("The answer engine is currently unavailable. Please retry in a few seconds."),
            details={"reason": str(exc)},
        ),
    )
    return JSONResponse(
        status_code=status_code_for(APIErrorCode.internal_error),
        content=envelope.model_dump(mode="json"),
    )


def _redact_input(value: object) -> str:
    """Return a length marker for ``value`` suitable for an error envelope.

    Pure function — no I/O, no logging, deterministic. Lives next
    to :func:`_validation_error_handler` because that's the only
    caller; if a second route ever needs the same scrub, move
    it to :mod:`app.core.errors`.
    """
    if isinstance(value, str):
        return f"<{len(value)} chars redacted>"
    return "<redacted>"


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Map a FastAPI request-validation error to 422 with the envelope.

    FastAPI's default 422 shape is not the same as the standard
    envelope; we re-shape it so the client only needs one parser.

    The Pydantic ``errors()`` payload contains an ``input`` key
    that echoes the offending value. For a chat-style API the
    body may include user-provided text or, in a future slice,
    pasted tokens — we don't want those echoed back through the
    error envelope. :func:`_redact_input` strips the value to a
    length marker so the client can still tell "the body was
    rejected" without seeing the contents.
    """
    redacted_errors: list[dict[str, Any]] = [
        ({**raw, "input": _redact_input(raw["input"])} if "input" in raw else dict(raw))
        for raw in exc.errors()
    ]
    envelope = ErrorEnvelope(
        request_id=_resolve_request_id(request),
        error=ErrorDetail(
            code=APIErrorCode.validation_error,
            message="Request body or parameters failed validation.",
            details={"errors": redacted_errors},
        ),
    )
    return JSONResponse(
        status_code=status_code_for(APIErrorCode.validation_error),
        content=envelope.model_dump(mode="json"),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler so the envelope is always uniform.

    Logs the traceback via the standard logger and returns a 500
    with the standard envelope. Without this handler FastAPI
    would emit its own ``Internal Server Error`` HTML body.
    """
    _logger.exception(
        "unhandled_exception",
        extra={"request_id": _resolve_request_id(request), "path": request.url.path},
    )
    envelope = ErrorEnvelope(
        request_id=_resolve_request_id(request),
        error=ErrorDetail(
            code=APIErrorCode.internal_error,
            message="An unexpected error occurred.",
        ),
    )
    return JSONResponse(
        status_code=status_code_for(APIErrorCode.internal_error),
        content=envelope.model_dump(mode="json"),
    )


app = create_app()
