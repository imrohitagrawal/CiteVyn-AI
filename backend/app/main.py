"""FastAPI application factory.

Wires the request-id middleware, the public + admin routers, and the
uniform error envelope. Every 4xx/5xx response flows through
:mod:`app.core.errors` so the client can parse errors with one shape.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.answer.orchestrator import OrchestratorError
from app.api.routes.health import router as health_router
from app.api.routes.messages import router as messages_router
from app.api.routes.sessions import router as sessions_router
from app.core.errors import (
    APIErrorCode,
    ErrorDetail,
    ErrorEnvelope,
    status_code_for,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware, get_current_request_id


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="CiteVyn AI Backend",
        version="0.1.0",
        description=(
            "Slice 7 backend: HTTP routes for sessions and messages, "
            "wired to the Slice 4–6 answer engine."
        ),
    )
    app.add_middleware(RequestIDMiddleware)
    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(messages_router)

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


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Map a FastAPI request-validation error to 422 with the envelope.

    FastAPI's default 422 shape is not the same as the standard
    envelope; we re-shape it so the client only needs one parser.
    """
    envelope = ErrorEnvelope(
        request_id=_resolve_request_id(request),
        error=ErrorDetail(
            code=APIErrorCode.validation_error,
            message="Request body or parameters failed validation.",
            details={"errors": exc.errors()},
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
    logging.getLogger("citevyn.request").exception(
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
