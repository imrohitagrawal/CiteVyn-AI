"""End-to-end tests for ``/health/dependencies``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.main import create_app


def test_dependencies_reports_healthy_when_db_pings(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the real engine (default SQLite) we expect a 200 response."""
    db_module.reset_engine()
    client = TestClient(create_app())

    response = client.get("/health/dependencies")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["dependencies"]["postgres"]["status"] == "healthy"
    assert "latency_ms" in body["dependencies"]["postgres"]
    # Health responses must never leak credentials or DSN fragments.
    raw = response.text.lower()
    assert "password" not in raw
    assert "postgresql+psycopg://" not in raw


def test_dependencies_returns_503_when_db_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfigured URL should produce 503 with no secret material in the body."""
    monkeypatch.setenv("CITEVYN_DATABASE_URL", "sqlite+aiosqlite:///nonexistent_dir/x.db")

    from app.core.config import get_settings

    get_settings.cache_clear()
    db_module.reset_engine()

    # Force the engine to be created against the bad URL.
    from app.core.db import get_engine

    get_engine()

    client = TestClient(create_app())
    try:
        response = client.get("/health/dependencies")
    finally:
        get_settings.cache_clear()
        db_module.reset_engine()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["postgres"]["status"] == "unhealthy"
    raw = response.text.lower()
    assert "password" not in raw
    assert "nonexistent_dir" not in raw
    assert "[redacted" not in raw
