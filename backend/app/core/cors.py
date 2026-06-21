"""CORS configuration for the FastAPI app.

The MVP allows only the approved frontend origin
(``docs/SECURITY_MODEL.md §11``); the allowlist is sourced from
:class:`Settings.cors_allowed_origins` and must be overridden in
production. Wildcards are explicitly forbidden: a wildcard would let
any origin read the response, which is a cross-origin data-leak risk
for a demo that returns assistant answers and citations.

The helper is intentionally a function (not a module-level singleton)
so tests can call :func:`configure_cors` with their own
:class:`Settings` and so the wiring is one line in :func:`create_app`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings


def configure_cors(app: FastAPI, settings: Settings) -> None:
    """Install :class:`CORSMiddleware` on ``app`` for ``settings.cors_allowed_origins``.

    Methods are restricted to the ones the public API actually uses;
    credentials are disabled because the demo auth is a bearer token
    in the ``Authorization`` header (cookies are not used). The
    ``X-Admin-API-Key`` header is in the allow list so the admin
    preflight works in the browser.
    """
    if not settings.cors_allowed_origins:
        # Fail closed rather than falling back to "*". A misconfigured
        # production deploy that empties the allowlist gets no CORS
        # headers at all instead of an insecure wildcard.
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "X-Admin-API-Key",
            settings.request_id_header,
            "Content-Type",
        ],
        # Cached preflight response — 10 minutes is the FastAPI
        # default and matches what most frontends expect.
        max_age=600,
    )


__all__ = ["configure_cors"]
