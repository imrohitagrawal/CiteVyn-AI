"""Route tests for ``app/api/routes/search.py`` (Slice 8 step 3).

Tests exercise:

* ``POST /v1/search/exact`` — auth, validation, response shape,
  active-sentinel resolution, product-area scoping.
* ``GET /health/index`` — placeholder (``status="pre_index"``)
  when no index row exists, real rows when seeded.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as db_module
from app.main import create_app
from tests.conftest import seed_catalog

# ---------------------------------------------------------------------------
# Shared fixture: an app whose get_session is bound to a seeded test session
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_seeded_session(session: AsyncSession):
    """Build a FastAPI app whose ``get_session`` returns the seeded session.

    The ``session`` fixture (in conftest.py) is a per-test
    in-memory SQLite engine with the schema already migrated.
    We override the dependency on each test so the route
    reads the same data the test sees.
    """
    app = create_app()

    async def _override():
        yield session

    app.dependency_overrides[db_module.get_session] = _override
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /v1/search/exact
# ---------------------------------------------------------------------------


API_KEY = "local-demo-key"


def test_search_exact_requires_api_key(app_with_seeded_session) -> None:
    """No bearer → 401."""
    with TestClient(app_with_seeded_session) as client:
        response = client.post(
            "/v1/search/exact",
            json={"term": "--model", "product_area": "codex"},
        )
        assert response.status_code == 401


def test_search_exact_rejects_missing_fields(app_with_seeded_session) -> None:
    """FastAPI's 422 envelope when required fields are missing."""
    with TestClient(app_with_seeded_session) as client:
        response = client.post(
            "/v1/search/exact",
            json={},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert "request_id" in body


def test_search_exact_returns_hit_with_score_one(app_with_seeded_session, session) -> None:
    """A known term in the active index returns one hit with score=1.0."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))

    with TestClient(app_with_seeded_session) as client:
        response = client.post(
            "/v1/search/exact",
            json={"term": "--model", "product_area": "codex"},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "--model"
        assert body["product_area"] == "codex"
        assert body["index_version"] == "active"
        assert body["total"] == 1
        hit = body["hits"][0]
        assert hit["term_text"] == "--model"
        assert hit["term_type"] == "flag"
        assert hit["product_area"] == "codex"
        assert hit["score"] == 1.0
        assert hit["index_version"] == "active"
        assert body["request_id"].startswith("req_")


def test_search_exact_returns_empty_for_unknown_term(app_with_seeded_session, session) -> None:
    """An unknown term returns ``total=0`` and an empty list, not 404."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))

    with TestClient(app_with_seeded_session) as client:
        response = client.post(
            "/v1/search/exact",
            json={"term": "--never-seen", "product_area": "codex"},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["hits"] == []


def test_search_exact_scopes_by_product_area(app_with_seeded_session, session) -> None:
    """The same term in two product areas is a different answer."""
    import asyncio
    from datetime import UTC, datetime

    from app.models.chunks import Chunk
    from app.models.documents import Document
    from app.models.enums import DocumentStatus, IndexStatus, TermType
    from app.models.exact_terms import ExactTerm
    from app.models.index_versions import IndexVersion

    async def _setup() -> None:
        # Drop the seed; rebuild with two product areas containing
        # the same term so we can prove the route scopes them.
        await seed_catalog(session)
        from sqlalchemy import select

        active = (
            await session.execute(
                select(IndexVersion).where(IndexVersion.status == IndexStatus.active)
            )
        ).scalar_one()
        now = datetime.now(UTC)
        doc = Document(
            index_version=active.index_version,
            source_name="claude_api",
            product_area="claude_api",
            source_url="https://example.com/claude-api-extra",
            title="Claude API extras",
            content_checksum="cafe" * 16,
            last_fetched_at=now,
            status=DocumentStatus.active,
        )
        session.add(doc)
        await session.flush()
        chunk = Chunk(
            document_id=doc.document_id,
            product_area="claude_api",
            section_path="flags",
            heading="flags",
            parent_heading=None,
            chunk_text="The --model flag selects the model.",
            context_summary="--model in claude_api.",
            chunk_order=0,
            content_checksum="cafe_chunk_0",
            exact_terms=[],
        )
        session.add(chunk)
        await session.flush()
        session.add(
            ExactTerm(
                term_text="--model",
                term_type=TermType.flag,
                product_area="claude_api",
                document_id=doc.document_id,
                chunk_id=chunk.chunk_id,
            )
        )
        await session.commit()

    asyncio.get_event_loop().run_until_complete(_setup())

    with TestClient(app_with_seeded_session) as client:
        codex = client.post(
            "/v1/search/exact",
            json={"term": "--model", "product_area": "codex"},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        claude = client.post(
            "/v1/search/exact",
            json={"term": "--model", "product_area": "claude_api"},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert codex.status_code == 200
        assert claude.status_code == 200
        assert codex.json()["hits"][0]["product_area"] == "codex"
        assert claude.json()["hits"][0]["product_area"] == "claude_api"
        assert codex.json()["hits"][0]["chunk_id"] != claude.json()["hits"][0]["chunk_id"]


def test_search_exact_clamps_limit_to_max_results(app_with_seeded_session, session) -> None:
    """The route's request validation caps ``limit`` to :data:`MAX_RESULTS`."""
    import asyncio
    from datetime import UTC, datetime

    from app.models.chunks import Chunk
    from app.models.documents import Document
    from app.models.enums import DocumentStatus, IndexStatus, TermType
    from app.models.exact_terms import ExactTerm
    from app.models.index_versions import IndexVersion

    async def _setup() -> None:
        await seed_catalog(session)
        from sqlalchemy import select

        active = (
            await session.execute(
                select(IndexVersion).where(IndexVersion.status == IndexStatus.active)
            )
        ).scalar_one()
        now = datetime.now(UTC)
        for i in range(30):
            doc = Document(
                index_version=active.index_version,
                source_name=f"src_{i}",
                product_area="codex",
                source_url=f"https://example.com/{i}",
                title=f"src {i}",
                content_checksum=f"chk_{i}" + "0" * 60,
                last_fetched_at=now,
                status=DocumentStatus.active,
            )
            session.add(doc)
            await session.flush()
            chunk = Chunk(
                document_id=doc.document_id,
                product_area="codex",
                section_path=f"h{i}",
                heading=f"h{i}",
                parent_heading=None,
                chunk_text="x" * 10,
                context_summary="x" * 10,
                chunk_order=0,
                content_checksum=f"chk_codex_chunk_{i}",
                exact_terms=[],
            )
            session.add(chunk)
            await session.flush()
            session.add(
                ExactTerm(
                    term_text="--model",
                    term_type=TermType.flag,
                    product_area="codex",
                    document_id=doc.document_id,
                    chunk_id=chunk.chunk_id,
                )
            )
        await session.commit()

    asyncio.get_event_loop().run_until_complete(_setup())

    with TestClient(app_with_seeded_session) as client:
        # 1000 is over the route's le=MAX_RESULTS → 422.
        bad = client.post(
            "/v1/search/exact",
            json={"term": "--model", "product_area": "codex", "limit": 1000},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert bad.status_code == 422

        # But a limit at the cap returns MAX_RESULTS rows.
        ok = client.post(
            "/v1/search/exact",
            json={"term": "--model", "product_area": "codex", "limit": 25},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert ok.status_code == 200
        body = ok.json()
        from app.services.exact_lookup import MAX_RESULTS

        assert body["total"] == MAX_RESULTS


def test_search_exact_passes_through_term_type_filter(app_with_seeded_session, session) -> None:
    """``term_type`` filter is forwarded to the service."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))

    with TestClient(app_with_seeded_session) as client:
        wrong = client.post(
            "/v1/search/exact",
            json={
                "term": "--model",
                "product_area": "codex",
                "term_type": "command",  # wrong type → no hit
            },
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert wrong.status_code == 200
        assert wrong.json()["total"] == 0


def test_search_exact_422_for_invalid_term_type(app_with_seeded_session, session) -> None:
    """An unknown ``term_type`` value is rejected by the schema."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))

    with TestClient(app_with_seeded_session) as client:
        response = client.post(
            "/v1/search/exact",
            json={
                "term": "--model",
                "product_area": "codex",
                "term_type": "not_a_real_type",
            },
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# /health/index
# ---------------------------------------------------------------------------


def test_health_index_pre_index_when_no_rows(app_with_seeded_session) -> None:
    """An empty catalog returns ``status=pre_index`` and null index rows."""
    with TestClient(app_with_seeded_session) as client:
        response = client.get("/health/index")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pre_index"
        assert body["active_index"] is None
        assert body["previous_good_index"] is None
        assert body["request_id"].startswith("req_")


def test_health_index_ready_when_active_present(app_with_seeded_session, session) -> None:
    """A seeded catalog with an active row reports ``status=ready``."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))

    with TestClient(app_with_seeded_session) as client:
        response = client.get("/health/index")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["active_index"]["index_version"] == "v1"
        assert body["active_index"]["promoted_at"] is not None
        assert body["previous_good_index"] is None


def test_search_exact_422_redacts_user_input(app_with_seeded_session) -> None:
    """The 422 envelope must not echo back user-provided input.

    Pydantic's default ``errors()`` includes an ``input`` key
    with the offending value verbatim. We strip that to
    ``<N chars redacted>`` (string) or ``<redacted>`` (other) so
    a chat payload (or, in a future slice, a pasted token) is
    never round-tripped through the error response.

    We use ``term_type="bogus"`` (not in the
    :class:`TermType` enum) to force a validation error after
    Pydantic has captured the offending input.
    """
    sensitive = "user-pasted-secret-value-that-must-not-leak"
    with TestClient(app_with_seeded_session) as client:
        response = client.post(
            "/v1/search/exact",
            json={"term": sensitive, "product_area": "codex", "term_type": "bogus"},
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        assert response.status_code == 422
        body_str = response.text
        assert sensitive not in body_str, f"422 envelope leaked the offending input: {body_str}"
        # The redactor's marker is in the body.
        assert "redacted" in body_str
