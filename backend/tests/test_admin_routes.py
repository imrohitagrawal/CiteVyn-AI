"""Route tests for ``app/api/routes/admin.py`` (Slice 8 step 5).

Tests cover:

* the admin-key gate (``X-Admin-API-Key``) on every endpoint
* the read surface (list / detail) for index versions,
  evaluations, ingestion jobs
* the promote write path (idempotent on already-active, audit
  row written on a real promotion, 404 on missing target)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as db_module
from app.main import create_app
from app.models.enums import (
    EvaluationStatus,
    IndexStatus,
    JobStage,
    JobStatus,
)
from app.models.evaluation import EvaluationRun
from app.models.index_versions import IndexVersion
from app.models.ingestion_jobs import IngestionJob
from tests.conftest import seed_catalog

ADMIN_KEY = "local-admin-key"
ADMIN_HEADER = "X-Admin-API-Key"


# ---------------------------------------------------------------------------
# Fixture: app with the per-test session injected
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_app(session: AsyncSession):
    """Build a FastAPI app whose ``get_session`` is the per-test session."""
    app = create_app()

    async def _override():
        yield session

    app.dependency_overrides[db_module.get_session] = _override
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def _admin_headers() -> dict[str, str]:
    return {ADMIN_HEADER: ADMIN_KEY}


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/admin/index_versions"),
        ("GET", "/v1/admin/index_versions/v1"),
        ("POST", "/v1/admin/index_versions/v1/promote"),
        ("GET", "/v1/admin/evaluations"),
        ("GET", "/v1/admin/ingestion_jobs"),
    ],
)
def test_admin_routes_reject_missing_admin_key(admin_app, method, path) -> None:
    """Every admin route returns 401 without ``X-Admin-API-Key``."""
    with TestClient(admin_app) as client:
        response = client.request(method, path)
    assert response.status_code == 401, (
        f"{method} {path} returned {response.status_code}, expected 401"
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/admin/index_versions"),
        ("GET", "/v1/admin/index_versions/v1"),
        ("POST", "/v1/admin/index_versions/v1/promote"),
        ("GET", "/v1/admin/evaluations"),
        ("GET", "/v1/admin/ingestion_jobs"),
    ],
)
def test_admin_routes_reject_bad_admin_key(admin_app, method, path) -> None:
    """Wrong key returns 401, not 403 (timing-safe comparison)."""
    with TestClient(admin_app) as client:
        response = client.request(method, path, headers={ADMIN_HEADER: "wrong"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /v1/admin/index_versions
# ---------------------------------------------------------------------------


def test_list_index_versions_empty(admin_app, session) -> None:
    """No rows → empty list, ``total=0``."""
    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/index_versions", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["versions"] == []


def test_list_index_versions_with_seed(admin_app, session) -> None:
    """The seed inserts one active version — list returns it."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/index_versions", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["versions"][0]["index_version"] == "v1"
    assert body["versions"][0]["status"] == "active"


def test_list_index_versions_filters_by_status(admin_app, session) -> None:
    """``?status=candidate`` returns only candidates."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    session.add(
        IndexVersion(
            index_version="v2",
            status=IndexStatus.candidate,
            source_version_hash="sha256:v2",
            created_at=datetime.now(UTC),
            promoted_at=None,
        )
    )
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.get(
            "/v1/admin/index_versions?status=candidate",
            headers=_admin_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["versions"][0]["index_version"] == "v2"


def test_get_index_version_returns_detail(admin_app, session) -> None:
    """Detail endpoint returns version + document_count."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/index_versions/v1", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["version"]["index_version"] == "v1"
    assert body["document_count"] >= 1


def test_get_index_version_404(admin_app, session) -> None:
    """Missing version returns 404 with the standard envelope."""
    with TestClient(admin_app) as client:
        response = client.get(
            "/v1/admin/index_versions/does-not-exist",
            headers=_admin_headers(),
        )
    assert response.status_code == 404
    body = response.json()
    # FastAPI wraps HTTPException bodies in ``{"detail": ...}``.
    assert body["detail"]["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# /v1/admin/index_versions/{version}/promote
# ---------------------------------------------------------------------------


def test_promote_index_version_demotes_current(admin_app, session) -> None:
    """Promotion moves current active to previous_good."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    session.add(
        IndexVersion(
            index_version="v2",
            status=IndexStatus.candidate,
            source_version_hash="sha256:v2",
            created_at=datetime.now(UTC),
            promoted_at=None,
        )
    )
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.post(
            "/v1/admin/index_versions/v2/promote",
            headers=_admin_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["index_version"] == "v2"
    assert body["status"] == "active"
    assert body["already_active"] is False

    # Current state: v1 is previous_good, v2 is active.
    with TestClient(admin_app) as client:
        list_response = client.get("/v1/admin/index_versions", headers=_admin_headers())
    rows = {r["index_version"]: r["status"] for r in list_response.json()["versions"]}
    assert rows["v1"] == "previous_good"
    assert rows["v2"] == "active"


def test_promote_index_version_idempotent(admin_app, session) -> None:
    """Promoting the already-active version returns ``already_active=True``."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    with TestClient(admin_app) as client:
        response = client.post(
            "/v1/admin/index_versions/v1/promote",
            headers=_admin_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["already_active"] is True
    assert body["status"] == "active"


def test_promote_index_version_404(admin_app, session) -> None:
    """Promoting a missing version returns 404."""
    with TestClient(admin_app) as client:
        response = client.post(
            "/v1/admin/index_versions/does-not-exist/promote",
            headers=_admin_headers(),
        )
    assert response.status_code == 404


def test_promote_index_version_writes_audit_event(admin_app, session) -> None:
    """A successful promotion appends a ``promote_index`` audit row."""
    import asyncio

    from app.models.audit_events import AuditEvent
    from app.models.enums import AuditAction

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    session.add(
        IndexVersion(
            index_version="v3",
            status=IndexStatus.candidate,
            source_version_hash="sha256:v3",
            created_at=datetime.now(UTC),
            promoted_at=None,
        )
    )
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.post(
            "/v1/admin/index_versions/v3/promote",
            headers=_admin_headers(),
        )
    assert response.status_code == 200

    rows = (
        (
            asyncio.get_event_loop().run_until_complete(
                session.execute(
                    select(AuditEvent).where(AuditEvent.action == AuditAction.promote_index)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].resource_id == "v3"


# ---------------------------------------------------------------------------
# /v1/admin/evaluations
# ---------------------------------------------------------------------------


def test_list_evaluations_empty(admin_app) -> None:
    """No runs → empty list, ``total=0``."""
    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/evaluations", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["runs"] == []


def test_list_evaluations_with_runs(admin_app, session) -> None:
    """Seeded runs surface in the list with flattened summary."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    now = datetime.now(UTC)
    session.add(
        EvaluationRun(
            suite_name="golden_v1",
            index_version="v1",
            started_at=now,
            completed_at=now,
            status=EvaluationStatus.passed,
            metrics={"cases_total": 15, "cases_passed": 15, "cases_failed": 0},
            failure_summary={},
        )
    )
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/evaluations", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    run = body["runs"][0]
    assert run["suite_name"] == "golden_v1"
    assert run["status"] == "passed"
    assert run["summary"]["cases_total"] == 15


def test_list_evaluations_filters_by_index_version(admin_app, session) -> None:
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    now = datetime.now(UTC)
    session.add_all(
        [
            EvaluationRun(
                suite_name="golden_v1",
                index_version="v1",
                started_at=now,
                completed_at=now,
                status=EvaluationStatus.passed,
                metrics={},
                failure_summary={},
            ),
            EvaluationRun(
                suite_name="golden_v1",
                index_version="v2",
                started_at=now,
                completed_at=now,
                status=EvaluationStatus.failed,
                metrics={},
                failure_summary={},
            ),
        ]
    )
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/evaluations?index_version=v2", headers=_admin_headers())
    body = response.json()
    assert body["total"] == 1
    assert body["runs"][0]["index_version"] == "v2"


def test_get_evaluation_detail(admin_app, session) -> None:
    """Detail endpoint returns metrics + failure_summary."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(seed_catalog(session))
    now = datetime.now(UTC)
    run = EvaluationRun(
        suite_name="golden_v1",
        index_version="v1",
        started_at=now,
        completed_at=now,
        status=EvaluationStatus.failed,
        metrics={"cases_total": 15, "cases_passed": 12, "cases_failed": 3},
        failure_summary={"case_id_3": "wrong answer"},
    )
    session.add(run)
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.get(f"/v1/admin/evaluations/{run.run_id}", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["metrics"]["cases_passed"] == 12
    assert body["run"]["failure_summary"]["case_id_3"] == "wrong answer"


def test_get_evaluation_404(admin_app) -> None:
    with TestClient(admin_app) as client:
        response = client.get(f"/v1/admin/evaluations/{uuid.uuid4()}", headers=_admin_headers())
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /v1/admin/ingestion_jobs
# ---------------------------------------------------------------------------


def test_list_ingestion_jobs_empty(admin_app) -> None:
    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/ingestion_jobs", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["jobs"] == []


def test_list_ingestion_jobs_with_seed(admin_app, session) -> None:
    """A seeded job appears in the list."""
    import asyncio

    now = datetime.now(UTC)
    session.add(
        IngestionJob(
            source_name="claude_api",
            status=JobStatus.completed,
            stage=JobStage.indexing,
            started_at=now,
            completed_at=now,
            error_type=None,
            error_message=None,
            retryable=False,
        )
    )
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.get("/v1/admin/ingestion_jobs", headers=_admin_headers())
    body = response.json()
    assert body["total"] == 1
    job = body["jobs"][0]
    assert job["source_name"] == "claude_api"
    assert job["status"] == "completed"


def test_list_ingestion_jobs_filters_compose(admin_app, session) -> None:
    """``status`` and ``source_name`` filters compose with AND."""
    import asyncio

    now = datetime.now(UTC)
    session.add_all(
        [
            IngestionJob(
                source_name="claude_api",
                status=JobStatus.completed,
                stage=JobStage.indexing,
                started_at=now,
                completed_at=now,
                retryable=False,
            ),
            IngestionJob(
                source_name="codex",
                status=JobStatus.failed,
                stage=JobStage.fetching,
                started_at=now,
                completed_at=now,
                error_type="NetworkError",
                error_message="connect timeout",
                retryable=True,
            ),
        ]
    )
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.get(
            "/v1/admin/ingestion_jobs?status=failed&source_name=codex",
            headers=_admin_headers(),
        )
    body = response.json()
    assert body["total"] == 1
    job = body["jobs"][0]
    assert job["source_name"] == "codex"
    assert job["status"] == "failed"
    assert job["retryable"] is True


def test_get_ingestion_job_detail(admin_app, session) -> None:
    import asyncio

    now = datetime.now(UTC)
    job = IngestionJob(
        source_name="codex",
        status=JobStatus.failed,
        stage=JobStage.fetching,
        started_at=now,
        completed_at=now,
        error_type="NetworkError",
        error_message="connect timeout",
        retryable=True,
    )
    session.add(job)
    asyncio.get_event_loop().run_until_complete(session.commit())

    with TestClient(admin_app) as client:
        response = client.get(f"/v1/admin/ingestion_jobs/{job.job_id}", headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["job"]["error_type"] == "NetworkError"


def test_get_ingestion_job_404(admin_app) -> None:
    with TestClient(admin_app) as client:
        response = client.get(f"/v1/admin/ingestion_jobs/{uuid.uuid4()}", headers=_admin_headers())
    assert response.status_code == 404
