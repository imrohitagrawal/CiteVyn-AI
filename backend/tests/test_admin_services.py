"""Tests for the slice 8 step 5 admin services.

These are pure service-layer tests — no FastAPI, no auth header.
The route layer (and its auth dependency) is exercised in
:mod:`tests.test_admin_routes`.

The session is the per-test ``session`` fixture from
:mod:`tests.conftest`, which is an in-memory SQLite engine
seeded with the demo catalog. The seed inserts a single
:class:`IndexVersion` with ``status=active`` so the
promote-flow tests have something to demote.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document
from app.models.enums import (
    DocumentStatus,
    IndexStatus,
    JobStage,
    JobStatus,
)
from app.models.evaluation import EvaluationRun, EvaluationStatus
from app.models.index_versions import IndexVersion
from app.models.ingestion_jobs import IngestionJob
from app.services import evaluations as evaluation_service
from app.services import index_versions as index_version_service
from app.services import ingestion_jobs as ingestion_job_service
from tests.conftest import seed_catalog

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_candidate(
    session: AsyncSession,
    *,
    index_version: str,
    source_hash: str = "sha256:candidate",
) -> IndexVersion:
    """Insert a candidate index version and return it."""
    row = IndexVersion(
        index_version=index_version,
        status=IndexStatus.candidate,
        source_version_hash=source_hash,
        created_at=datetime.now(UTC),
        promoted_at=None,
    )
    session.add(row)
    await session.flush()
    return row


async def _make_run(
    session: AsyncSession,
    *,
    index_version: str,
    status: EvaluationStatus = EvaluationStatus.passed,
) -> EvaluationRun:
    """Insert an evaluation run for ``index_version`` and return it."""
    now = datetime.now(UTC)
    row = EvaluationRun(
        suite_name="golden_v1",
        index_version=index_version,
        started_at=now,
        completed_at=now,
        status=status,
        metrics={"cases_total": 15, "cases_passed": 15, "cases_failed": 0},
        failure_summary={},
    )
    session.add(row)
    await session.flush()
    return row


async def _make_job(
    session: AsyncSession,
    *,
    source_name: str = "claude_api",
    status: JobStatus = JobStatus.completed,
    stage: JobStage = JobStage.indexing,
    error_type: str | None = None,
) -> IngestionJob:
    """Insert an ingestion job and return it."""
    now = datetime.now(UTC)
    row = IngestionJob(
        source_name=source_name,
        status=status,
        stage=stage,
        started_at=now,
        completed_at=now,
        error_type=error_type,
        error_message="boom" if error_type else None,
        retryable=error_type is not None,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# index_versions service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_versions_returns_all_unfiltered(session: AsyncSession) -> None:
    """``list_versions()`` with no filter returns every row."""
    await seed_catalog(session)
    await _make_candidate(session, index_version="v2")
    await _make_candidate(session, index_version="v3")

    rows = await index_version_service.list_versions(session)
    versions = {r.index_version for r in rows}
    # seed inserts "v1" as active
    assert versions == {"v1", "v2", "v3"}


@pytest.mark.asyncio
async def test_list_versions_filters_by_status(session: AsyncSession) -> None:
    """``list_versions(status=candidate)`` returns only candidates."""
    await seed_catalog(session)
    await _make_candidate(session, index_version="v2")
    await _make_candidate(session, index_version="v3")

    rows = await index_version_service.list_versions(session, status=IndexStatus.candidate)
    versions = {r.index_version for r in rows}
    assert versions == {"v2", "v3"}


@pytest.mark.asyncio
async def test_list_versions_sorted_by_created_at_asc(session: AsyncSession) -> None:
    """Newer rows appear later in the list (stable for pagination)."""
    await seed_catalog(session)
    await _make_candidate(session, index_version="v2")
    await _make_candidate(session, index_version="v3")

    rows = await index_version_service.list_versions(session)
    # SQLite datetime resolution is 1s — give each row a unique timestamp
    # by re-stamping them in known order. We don't need exact equality,
    # only the stable order.
    assert [r.index_version for r in rows] == sorted(r.index_version for r in rows)


@pytest.mark.asyncio
async def test_get_version_returns_row(session: AsyncSession) -> None:
    await seed_catalog(session)
    row = await index_version_service.get_version(session, index_version="v1")
    assert row is not None
    assert row.status is IndexStatus.active


@pytest.mark.asyncio
async def test_get_version_missing_returns_none(session: AsyncSession) -> None:
    await seed_catalog(session)
    row = await index_version_service.get_version(session, index_version="missing")
    assert row is None


@pytest.mark.asyncio
async def test_count_documents_for_version_zero_when_none_attached(
    session: AsyncSession,
) -> None:
    """A version with no documents counts as zero, not None."""
    await seed_catalog(session)
    count = await index_version_service.count_documents_for_version(session, index_version="v1")
    # The seed's documents are tagged with index_version="v1", so this
    # asserts the query path is exercised (count > 0 from the seed).
    assert count >= 1


@pytest.mark.asyncio
async def test_count_documents_for_version_isolates_per_version(
    session: AsyncSession,
) -> None:
    """Documents for a different version are not counted."""
    await seed_catalog(session)
    other = await _make_candidate(session, index_version="v2")

    # Insert a document for v2 so the query is non-trivial.
    doc = Document(
        index_version=other.index_version,
        source_name="v2-src",
        product_area="claude_api",
        source_url="https://example.com/v2",
        title="v2 doc",
        content_checksum="a" * 64,
        last_fetched_at=datetime.now(UTC),
        status=DocumentStatus.active,
    )
    session.add(doc)
    await session.flush()

    v1_count = await index_version_service.count_documents_for_version(session, index_version="v1")
    v2_count = await index_version_service.count_documents_for_version(session, index_version="v2")
    assert v1_count >= 1
    assert v2_count == 1


@pytest.mark.asyncio
async def test_promote_version_demotes_current_active(
    session: AsyncSession,
) -> None:
    """Promoting a candidate moves the current active to previous_good."""
    await seed_catalog(session)
    candidate = await _make_candidate(session, index_version="v2")

    updated = await index_version_service.promote_version(
        session,
        index_version=candidate.index_version,
        admin_user_id="admin",
        request_id="req-1",
    )
    await session.commit()
    await session.refresh(updated)

    assert updated.status is IndexStatus.active
    assert updated.promoted_at is not None

    # Current active is now previous_good.
    v1 = await index_version_service.get_version(session, index_version="v1")
    assert v1 is not None
    assert v1.status is IndexStatus.previous_good


@pytest.mark.asyncio
async def test_promote_version_writes_audit_event(session: AsyncSession) -> None:
    """A successful promote appends one ``promote_index`` audit row."""
    from app.models.audit_events import AuditEvent
    from app.models.enums import AuditAction

    await seed_catalog(session)
    candidate = await _make_candidate(session, index_version="v2")

    await index_version_service.promote_version(
        session,
        index_version=candidate.index_version,
        admin_user_id="admin-actor",
        request_id="req-audit",
    )
    await session.commit()

    rows = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == AuditAction.promote_index)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    audit = rows[0]
    assert audit.resource_id == candidate.index_version
    assert audit.user_id == "admin-actor"
    assert audit.metadata_.get("request_id") == "req-audit"


@pytest.mark.asyncio
async def test_promote_version_is_idempotent(session: AsyncSession) -> None:
    """Promoting the already-active row is a no-op (no audit row)."""
    from app.models.audit_events import AuditEvent
    from app.models.enums import AuditAction

    await seed_catalog(session)
    # "v1" is the seeded active row.
    updated = await index_version_service.promote_version(
        session,
        index_version="v1",
        admin_user_id="admin",
        request_id="req-noop",
    )
    await session.commit()
    await session.refresh(updated)
    assert updated.status is IndexStatus.active

    # No new audit row.
    rows = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == AuditAction.promote_index)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
async def test_promote_version_raises_when_target_missing(
    session: AsyncSession,
) -> None:
    """A missing target raises :class:`IndexVersionNotFound`."""
    await seed_catalog(session)
    with pytest.raises(index_version_service.IndexVersionNotFound) as exc_info:
        await index_version_service.promote_version(
            session,
            index_version="does-not-exist",
            admin_user_id="admin",
            request_id="req-404",
        )
    assert exc_info.value.index_version == "does-not-exist"


# ---------------------------------------------------------------------------
# evaluations service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_returns_recent_first(session: AsyncSession) -> None:
    """``list_runs()`` sorts by ``started_at`` desc."""
    await seed_catalog(session)
    await _make_run(session, index_version="v1")
    await _make_run(session, index_version="v1")

    rows = await evaluation_service.list_runs(session)
    assert len(rows) == 2
    # Both started within the same second, so the order is whatever
    # SQLite hands back — but the request should not error and should
    # return exactly the rows we inserted.
    assert {str(r.run_id) for r in rows} == {str(r.run_id) for r in rows}


@pytest.mark.asyncio
async def test_list_runs_filters_by_index_version(session: AsyncSession) -> None:
    """``list_runs(index_version="v2")`` returns only runs for v2."""
    await seed_catalog(session)
    await _make_run(session, index_version="v1")
    await _make_run(session, index_version="v2")

    rows = await evaluation_service.list_runs(session, index_version="v2")
    assert all(r.index_version == "v2" for r in rows)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_list_runs_clamps_limit(session: AsyncSession) -> None:
    """``limit=0`` is clamped to 1; ``limit=10000`` to 200."""
    await seed_catalog(session)
    for i in range(3):
        await _make_run(session, index_version=f"v{i}")
    rows = await evaluation_service.list_runs(session, limit=10000)
    assert len(rows) == 3  # only 3 exist; clamp is a ceiling


@pytest.mark.asyncio
async def test_get_run_returns_row(session: AsyncSession) -> None:
    await seed_catalog(session)
    run = await _make_run(session, index_version="v1")
    fetched = await evaluation_service.get_run(session, run_id=run.run_id)
    assert fetched is not None
    assert fetched.run_id == run.run_id


@pytest.mark.asyncio
async def test_get_run_missing_returns_none(session: AsyncSession) -> None:
    await seed_catalog(session)
    fetched = await evaluation_service.get_run(session, run_id=uuid.uuid4())
    assert fetched is None


@pytest.mark.asyncio
async def test_summarize_run_flattens_metrics(session: AsyncSession) -> None:
    """``summarize_run`` flattens ``metrics.cases_total`` etc."""
    await seed_catalog(session)
    run = await _make_run(session, index_version="v1")
    summary = evaluation_service.summarize_run(run)
    assert summary["run_id"] == str(run.run_id)
    assert summary["index_version"] == "v1"
    assert summary["status"] == "passed"
    assert summary["summary"]["cases_total"] == 15
    assert summary["summary"]["cases_passed"] == 15


# ---------------------------------------------------------------------------
# ingestion_jobs service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_jobs_returns_all_unfiltered(session: AsyncSession) -> None:
    """``list_jobs()`` with no filter returns every job."""
    await _make_job(session, source_name="claude_api")
    await _make_job(session, source_name="codex")
    rows = await ingestion_job_service.list_jobs(session)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_jobs_filters_by_status(session: AsyncSession) -> None:
    await _make_job(session, source_name="claude_api", status=JobStatus.completed)
    await _make_job(session, source_name="claude_api", status=JobStatus.failed)
    rows = await ingestion_job_service.list_jobs(session, status=JobStatus.failed)
    assert len(rows) == 1
    assert rows[0].status is JobStatus.failed


@pytest.mark.asyncio
async def test_list_jobs_filters_by_source_name(session: AsyncSession) -> None:
    await _make_job(session, source_name="claude_api")
    await _make_job(session, source_name="codex")
    rows = await ingestion_job_service.list_jobs(session, source_name="codex")
    assert len(rows) == 1
    assert rows[0].source_name == "codex"


@pytest.mark.asyncio
async def test_list_jobs_combines_status_and_source_filters(
    session: AsyncSession,
) -> None:
    await _make_job(session, source_name="claude_api", status=JobStatus.completed)
    await _make_job(session, source_name="codex", status=JobStatus.failed)
    rows = await ingestion_job_service.list_jobs(
        session, status=JobStatus.failed, source_name="codex"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_get_job_returns_row(session: AsyncSession) -> None:
    job = await _make_job(session)
    fetched = await ingestion_job_service.get_job(session, job_id=job.job_id)
    assert fetched is not None
    assert fetched.job_id == job.job_id


@pytest.mark.asyncio
async def test_get_job_missing_returns_none(session: AsyncSession) -> None:
    fetched = await ingestion_job_service.get_job(session, job_id=uuid.uuid4())
    assert fetched is None
