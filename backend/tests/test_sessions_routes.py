"""End-to-end tests for the session HTTP routes (Slice 7).

Covers the three public endpoints defined in
``docs/API_SPEC.md`` §4–§5:

* ``POST /v1/sessions`` — create a chat session.
* ``GET /v1/sessions/{session_id}`` — fetch a session and its messages.
* ``DELETE /v1/sessions/{session_id}`` — close a session.

Every test runs against an in-memory SQLite engine so the suite is
hermetic. The route layer depends on the request-scoped
:func:`app.core.db.get_session` dependency, which is resolved at
request time against the app's cached engine; the
``in_memory_client`` fixture below resets the engine + settings cache
around each test so the route picks up the in-memory database.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.config import get_settings
from app.main import create_app
from app.models import Base

DEMO_BEARER = "Bearer local-demo-key"


@pytest.fixture
def in_memory_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> Generator[TestClient, None, None]:
    """A TestClient backed by a per-test SQLite file under tmp_path.

    ``:memory:`` SQLite gives every connection its own database, so the
    route's :func:`get_session` and the seed routine in this fixture
    would not see each other's rows. A temp file is shared across
    connections and auto-removed by pytest at teardown. The schema is
    created up front via :func:`Base.metadata.create_all` so the route
    does not need to know about migrations.
    """
    db_module.reset_engine()
    get_settings.cache_clear()
    db_file = tmp_path / "sessions_route.db"
    monkeypatch.setenv("CITEVYN_DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    get_settings.cache_clear()
    engine = db_module.get_engine()

    async def _init_schema() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init_schema())
    try:
        client = TestClient(create_app())
        yield client
    finally:
        get_settings.cache_clear()
        db_module.reset_engine()
        monkeypatch.delenv("CITEVYN_DATABASE_URL", raising=False)


# ---------------------------------------------------------------------------
# POST /v1/sessions
# ---------------------------------------------------------------------------


def test_create_session_returns_201_and_persists(in_memory_client: TestClient) -> None:
    response = in_memory_client.post(
        "/v1/sessions",
        json={"user_id": "demo_user", "channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["request_id"].startswith("req_")
    # session_id is a valid UUID string
    uuid.UUID(body["session_id"])
    assert body["expires_at"].endswith("Z") or "+" in body["expires_at"]
    # Location header points at the new resource.
    assert response.headers["Location"] == f"/v1/sessions/{body['session_id']}"


def test_create_session_rejects_non_chat_channel(in_memory_client: TestClient) -> None:
    response = in_memory_client.post(
        "/v1/sessions",
        json={"user_id": "demo_user", "channel": "voice"},
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "validation_error"


def test_create_session_requires_bearer_token(in_memory_client: TestClient) -> None:
    response = in_memory_client.post("/v1/sessions", json={"channel": "chat"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "auth_required"


def test_create_session_rejects_wrong_bearer_token(in_memory_client: TestClient) -> None:
    response = in_memory_client.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": "Bearer wrong-key"},
    )

    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "auth_required"


# ---------------------------------------------------------------------------
# GET /v1/sessions/{session_id}
# ---------------------------------------------------------------------------


def test_get_session_returns_metadata_and_messages(in_memory_client: TestClient) -> None:
    create = in_memory_client.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    response = in_memory_client.get(
        f"/v1/sessions/{session_id}",
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["user_id"] == "demo_user"
    assert body["channel"] == "chat"
    assert body["messages"] == []  # no messages yet
    assert body["request_id"].startswith("req_")


def test_get_session_returns_404_when_missing(in_memory_client: TestClient) -> None:
    response = in_memory_client.get(
        f"/v1/sessions/{uuid.uuid4()}",
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "not_found"


def test_get_session_rejects_invalid_uuid(in_memory_client: TestClient) -> None:
    response = in_memory_client.get(
        "/v1/sessions/not-a-uuid",
        headers={"Authorization": DEMO_BEARER},
    )

    # FastAPI returns 422 for path validation failures; the envelope
    # still carries the standard error shape.
    assert response.status_code == 422


def test_get_session_requires_bearer_token(in_memory_client: TestClient) -> None:
    response = in_memory_client.get(f"/v1/sessions/{uuid.uuid4()}")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /v1/sessions/{session_id}
# ---------------------------------------------------------------------------


def test_delete_session_returns_204_and_expires(in_memory_client: TestClient) -> None:
    create = in_memory_client.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    response = in_memory_client.delete(
        f"/v1/sessions/{session_id}",
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 204
    assert response.content == b""

    # The session row still exists, but expires_at is in the past.
    get = in_memory_client.get(
        f"/v1/sessions/{session_id}",
        headers={"Authorization": DEMO_BEARER},
    )
    assert get.status_code == 200
    body = get.json()
    assert body["session_id"] == session_id
    # expires_at is now <= created_at (we set it to the current
    # timestamp on close).
    assert body["expires_at"] <= body["created_at"] or body["expires_at"] <= _now_iso()


def test_delete_session_returns_404_when_missing(in_memory_client: TestClient) -> None:
    response = in_memory_client.delete(
        f"/v1/sessions/{uuid.uuid4()}",
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "not_found"


def test_delete_session_requires_bearer_token(in_memory_client: TestClient) -> None:
    response = in_memory_client.delete(f"/v1/sessions/{uuid.uuid4()}")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Request id propagation
# ---------------------------------------------------------------------------


def test_request_id_round_trips_on_sessions_routes(in_memory_client: TestClient) -> None:
    response = in_memory_client.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={
            "Authorization": DEMO_BEARER,
            "X-Request-ID": "req_sessions_test",
        },
    )

    assert response.headers["X-Request-ID"] == "req_sessions_test"
    assert response.json()["request_id"] == "req_sessions_test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
