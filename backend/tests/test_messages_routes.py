"""End-to-end tests for the messages HTTP routes (Slice 7).

Covers the two endpoints defined in ``docs/API_SPEC.md`` §5:

* ``POST /v1/sessions/{session_id}/messages`` — the answer endpoint.
* ``GET /v1/sessions/{session_id}/messages/{message_id}`` — fetch one
  message for citation hydration.

The happy-path test seeds the minimal catalog (an active index, four
documents, one chunk per product area) through a one-shot async
seed and asserts the full grounded-answer shape. The error-path tests
confirm the standard envelope and status mapping without seeding.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.main import create_app
from app.models import Base, IndexStatus, IndexVersion
from tests.conftest import seed_catalog

DEMO_BEARER = "Bearer local-demo-key"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> Generator[TestClient, None, None]:
    """A TestClient backed by a per-test SQLite file under tmp_path.

    A temp file is shared across connections; ``:memory:`` would give
    every async connection its own database and the route's
    :func:`get_session` would not see rows seeded by the fixture. The
    schema is created up front so the route does not need migrations.
    """
    db_module.reset_engine()
    get_settings.cache_clear()
    db_file = tmp_path / "messages_route.db"
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


@pytest.fixture
def seeded_app(
    in_memory_client: TestClient,
) -> Generator[TestClient, None, None]:
    """Yield the in-memory client after seeding the catalog + index."""
    factory = get_sessionmaker()

    async def _seed() -> None:
        async with factory() as session:
            version = IndexVersion(
                index_version="index_v1",
                status=IndexStatus.active,
                source_version_hash="sha256:index-v1",
                created_at=datetime.now(UTC),
                promoted_at=datetime.now(UTC),
            )
            session.add(version)
            await session.flush()
            await seed_catalog(session)

    asyncio.run(_seed())
    yield in_memory_client


# ---------------------------------------------------------------------------
# POST /v1/sessions/{session_id}/messages
# ---------------------------------------------------------------------------


def test_post_message_returns_200_with_full_shape(seeded_app: TestClient) -> None:
    """The full happy path: session exists, supported question, grounded
    answer, citations, and an audit row."""
    create = seeded_app.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    assert create.status_code == 201
    session_id = create.json()["session_id"]

    response = seeded_app.post(
        f"/v1/sessions/{session_id}/messages",
        json={"message": "How do I configure Claude Code permissions?", "answer_style": "short"},
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 200
    body = response.json()
    # Spec §5 fields.
    assert body["request_id"].startswith("req_")
    assert uuid.UUID(body["message_id"])
    assert isinstance(body["answer"], str) and body["answer"]
    assert body["domain"] == "claude_code"
    assert body["intent"] == "how_to"
    assert body["confidence"] in {"high", "medium", "low"}
    assert body["cache_hit"] is False
    assert body["retrieval_strategy"] == "hybrid_reranked"
    assert body["unsupported"] is False
    assert body["no_answer"] is False
    # Citations are projected from the chunks the seed returned.
    assert isinstance(body["citations"], list)


def test_post_message_returns_unsupported_shape(seeded_app: TestClient) -> None:
    """An off-domain question must come back with the unsupported flag,
    not a transport error (per spec §6)."""
    create = seeded_app.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    response = seeded_app.post(
        f"/v1/sessions/{session_id}/messages",
        json={"message": "What is the recipe for chocolate cake?"},
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["unsupported"] is True
    assert body["no_answer"] is True
    assert body["domain"] == "unsupported"
    assert body["intent"] == "unsupported"
    assert body["confidence"] == "none"
    assert body["citations"] == []


def test_post_message_rejects_bad_answer_style(seeded_app: TestClient) -> None:
    create = seeded_app.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    response = seeded_app.post(
        f"/v1/sessions/{session_id}/messages",
        json={"message": "hi", "answer_style": "essay"},
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "validation_error"
    assert "answer_style" in detail["error"]["message"]


def test_post_message_returns_404_when_session_missing(in_memory_client: TestClient) -> None:
    response = in_memory_client.post(
        f"/v1/sessions/{uuid.uuid4()}/messages",
        json={"message": "hello", "answer_style": "short"},
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "not_found"


def test_post_message_requires_bearer_token(in_memory_client: TestClient) -> None:
    response = in_memory_client.post(
        f"/v1/sessions/{uuid.uuid4()}/messages",
        json={"message": "hello", "answer_style": "short"},
    )
    assert response.status_code == 401


def test_post_message_rejects_wrong_bearer_token(in_memory_client: TestClient) -> None:
    response = in_memory_client.post(
        f"/v1/sessions/{uuid.uuid4()}/messages",
        json={"message": "hello", "answer_style": "short"},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/sessions/{session_id}/messages/{message_id}
# ---------------------------------------------------------------------------


def test_get_message_returns_payload_and_evidence(seeded_app: TestClient) -> None:
    create = seeded_app.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    post = seeded_app.post(
        f"/v1/sessions/{session_id}/messages",
        json={"message": "How do I configure Claude Code permissions?"},
        headers={"Authorization": DEMO_BEARER},
    )
    message_id = post.json()["message_id"]

    response = seeded_app.get(
        f"/v1/sessions/{session_id}/messages/{message_id}",
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message_id"] == message_id
    assert body["session_id"] == session_id
    assert body["role"] == "assistant"
    assert isinstance(body["content"], str)
    # Evidence rows are persisted by the orchestrator.
    assert isinstance(body["evidence"], list)


def test_get_message_returns_404_when_message_missing(seeded_app: TestClient) -> None:
    create = seeded_app.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    response = seeded_app.get(
        f"/v1/sessions/{session_id}/messages/{uuid.uuid4()}",
        headers={"Authorization": DEMO_BEARER},
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "not_found"


def test_get_message_returns_404_when_session_missing(in_memory_client: TestClient) -> None:
    response = in_memory_client.get(
        f"/v1/sessions/{uuid.uuid4()}/messages/{uuid.uuid4()}",
        headers={"Authorization": DEMO_BEARER},
    )
    assert response.status_code == 404


def test_get_message_requires_bearer_token(seeded_app: TestClient) -> None:
    create = seeded_app.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    response = seeded_app.get(f"/v1/sessions/{session_id}/messages/{uuid.uuid4()}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Exception handler
# ---------------------------------------------------------------------------


def test_orchestrator_error_maps_to_500_envelope(
    in_memory_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the orchestrator raises :class:`OrchestratorError` the route
    must return 500 with the standard envelope, not leak the Python
    traceback to the client."""
    from app.answer import orchestrator as orch_module
    from app.api.routes import messages as messages_module

    class _BoomOrchestrator:
        def __init__(self, settings, session, **_kwargs: object) -> None:
            del settings, session

        async def ask(self, **_kwargs: object) -> object:
            raise orch_module.OrchestratorError("LLM provider timed out")

    monkeypatch.setattr(orch_module, "Orchestrator", _BoomOrchestrator)
    monkeypatch.setattr(messages_module, "Orchestrator", _BoomOrchestrator)

    create = in_memory_client.post(
        "/v1/sessions",
        json={"channel": "chat"},
        headers={"Authorization": DEMO_BEARER},
    )
    session_id = create.json()["session_id"]

    response = in_memory_client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"message": "How do I configure Claude Code permissions?"},
        headers={"Authorization": DEMO_BEARER},
    )

    assert response.status_code == 500
    body = response.json()
    # The exception handler returns the envelope at the top level
    # (not nested under ``detail``) so the standard envelope shape is
    # preserved.
    assert body["error"]["code"] == "internal_error"
    assert "unavailable" in body["error"]["message"].lower()
    # The cause is preserved in the details for observability.
    assert body["error"]["details"]["reason"] == "LLM provider timed out"
