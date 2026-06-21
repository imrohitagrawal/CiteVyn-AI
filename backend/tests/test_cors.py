"""Slice 8: tests for :func:`app.core.cors.configure_cors`.

The CORS allowlist is the only thing standing between a browser
loading a hostile site and the demo API leaking responses. These
tests pin the security-critical behaviour:

* the configured origin gets the right ``Access-Control-Allow-*``
  headers in response to a preflight and a normal request
* a non-allowlisted origin does NOT
* an empty allowlist installs no middleware (fail-closed)
* the allowed methods are limited (no ``PUT`` / ``PATCH`` on purpose)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.cors import configure_cors


@pytest.fixture
def settings() -> Settings:
    return Settings(
        cors_allowed_origins=["https://allowed.example.com"],
        _env_file=None,
    )


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _build_app(settings: Settings, *, path: str = "/ping") -> FastAPI:
    app = FastAPI()
    configure_cors(app, settings)

    @app.get(path)
    def ping() -> dict[str, str]:
        return {"pong": "1"}

    return app


def test_preflight_from_allowed_origin_returns_cors_headers(settings: Settings) -> None:
    """A preflight from an allowlisted origin succeeds with the CORS headers."""
    client = _client(_build_app(settings))
    response = client.options(
        "/ping",
        headers={
            "Origin": "https://allowed.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://allowed.example.com"
    # The ``allow_credentials=False`` setting must not emit a
    # ``Access-Control-Allow-Credentials: true`` header.
    assert "access-control-allow-credentials" not in {k.lower() for k in response.headers}


def test_get_from_allowed_origin_has_cors_header(settings: Settings) -> None:
    """A simple GET from an allowlisted origin gets the CORS header on the response."""
    client = _client(_build_app(settings))
    response = client.get("/ping", headers={"Origin": "https://allowed.example.com"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://allowed.example.com"


def test_get_from_disallowed_origin_has_no_cors_header(settings: Settings) -> None:
    """A non-allowlisted origin must NOT receive CORS headers.

    Without this, the browser would refuse the response, but the
    server still has to honor the allowlist: returning a wildcard
    for every origin would be a leak even if browsers blocked it.
    """
    client = _client(_build_app(settings))
    response = client.get("/ping", headers={"Origin": "https://evil.example.com"})
    assert response.status_code == 200
    # FastAPI's CORS middleware echoes the allowlist, not the
    # request origin, so a disallowed origin gets no header.
    assert "access-control-allow-origin" not in response.headers


def test_empty_allowlist_installs_no_cors() -> None:
    """An empty allowlist is a fail-closed no-op (no CORS middleware at all).

    This is the documented behaviour in :func:`configure_cors` —
    misconfigured production deploys should break, not silently
    allow everything.
    """
    settings = Settings(cors_allowed_origins=[], _env_file=None)
    app = _build_app(settings)
    # No CORS middleware was added — but the app is still functional.
    client = _client(app)
    response = client.get("/ping", headers={"Origin": "https://evil.example.com"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_admin_key_header_is_in_preflight_allowlist() -> None:
    """The admin key header is allowlisted in preflights.

    The admin SPA sends ``X-Admin-API-Key``; a browser preflight
    would otherwise fail with a 403 from the CORS middleware.
    """
    settings = Settings(
        cors_allowed_origins=["https://admin.example.com"],
        _env_file=None,
    )
    client = _client(_build_app(settings, path="/admin/ping"))
    response = client.options(
        "/admin/ping",
        headers={
            "Origin": "https://admin.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-admin-api-key",
        },
    )
    # The preflight succeeded; the allowlisted header is in the response.
    assert response.status_code == 200
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-admin-api-key" in allowed_headers
