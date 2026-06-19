from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.errors import APIErrorCode, error_response
from app.core.middleware import get_current_request_id

bearer_scheme = HTTPBearer(auto_error=False)


def require_demo_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Validate the bearer token and return the demo user id.

    Auth failures raise the standard envelope via
    :func:`app.core.errors.error_response` so the client can parse
    one shape for every 401 (instead of FastAPI's default
    ``{"detail": "..."}`` body).
    """
    request_id = str(getattr(request.state, "request_id", "") or get_current_request_id() or "")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise error_response(
            request_id=request_id,
            code=APIErrorCode.auth_required,
            message="Missing bearer token.",
        )

    if credentials.credentials != settings.demo_api_key:
        raise error_response(
            request_id=request_id,
            code=APIErrorCode.auth_required,
            message="Invalid bearer token.",
        )

    return "demo_user"
