"""Admin HTTP routes (Slice 8 step 5).

All endpoints sit behind :func:`require_admin_api_key`; the
admin key is a static header (``X-Admin-API-Key``) configured
via :attr:`Settings.admin_api_key`. See
:mod:`app.core.security` for the dependency.

Surface
-------
* ``GET  /v1/admin/index_versions``              — list versions
* ``GET  /v1/admin/index_versions/{version}``   — version + counts
* ``POST /v1/admin/index_versions/{version}/promote``
                                                   — promote to active
* ``GET  /v1/admin/evaluations``                 — list runs
* ``GET  /v1/admin/evaluations/{run_id}``        — run detail
* ``GET  /v1/admin/ingestion_jobs``              — list jobs
* ``GET  /v1/admin/ingestion_jobs/{job_id}``     — job detail

The worker (Step 6) is the only writer to ``ingestion_jobs`` and
``evaluation_runs``; this surface is read-only + the
``promote_index`` write. Re-running a failed ingestion is
deliberately out of scope for Step 5.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import APIErrorCode, error_response
from app.core.middleware import get_current_request_id
from app.core.rate_limit import rate_limited_admin
from app.core.security import ADMIN_USER_ID
from app.models.enums import IndexStatus, JobStatus
from app.services import evaluations as evaluation_service
from app.services import index_versions as index_version_service
from app.services import ingestion_jobs as ingestion_job_service

router = APIRouter(prefix="/v1/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class IndexVersionSummary(BaseModel):
    """One row in the index-version list response."""

    model_config = ConfigDict(from_attributes=True)

    index_version: str
    status: IndexStatus
    source_version_hash: str
    created_at: datetime
    promoted_at: datetime | None
    evaluation_run_id: uuid.UUID | None


class IndexVersionListResponse(BaseModel):
    """List envelope for ``GET /v1/admin/index_versions``."""

    request_id: str
    total: int
    versions: list[IndexVersionSummary]


class IndexVersionDetailResponse(BaseModel):
    """Detail envelope for ``GET /v1/admin/index_versions/{version}``."""

    request_id: str
    version: IndexVersionSummary
    document_count: int


class PromoteIndexResponse(BaseModel):
    """Response envelope for the promote endpoint."""

    request_id: str
    index_version: str
    status: IndexStatus
    promoted_at: datetime
    already_active: bool


class EvaluationRunSummary(BaseModel):
    """One row in the evaluation-runs list response.

    Flattened metrics so the list view doesn't have to parse
    the ``metrics`` JSON blob to render "12/15 passed".
    """

    run_id: uuid.UUID
    suite_name: str
    index_version: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    summary: dict[str, Any | None]


class EvaluationRunListResponse(BaseModel):
    request_id: str
    total: int
    runs: list[EvaluationRunSummary]


class EvaluationRunDetailResponse(BaseModel):
    request_id: str
    run: dict[str, Any]


class IngestionJobSummary(BaseModel):
    """One row in the ingestion-jobs list response."""

    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    source_name: str
    status: JobStatus
    stage: str
    started_at: datetime
    completed_at: datetime | None
    error_type: str | None
    retryable: bool


class IngestionJobListResponse(BaseModel):
    request_id: str
    total: int
    jobs: list[IngestionJobSummary]


class IngestionJobDetailResponse(BaseModel):
    request_id: str
    job: IngestionJobSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_id(request: Request) -> str:
    """Return the request id stamped on :class:`Request` by the middleware."""
    return str(getattr(request.state, "request_id", "") or get_current_request_id() or "")


def _http_404(message: str, *, request_id: str) -> HTTPException:
    """Build a 404 :class:`HTTPException` with the standard error envelope."""
    return error_response(
        request_id=request_id,
        code=APIErrorCode.not_found,
        message=message,
    )


# ---------------------------------------------------------------------------
# /v1/admin/index_versions
# ---------------------------------------------------------------------------


@router.get(
    "/index_versions",
    response_model=IndexVersionListResponse,
)
async def list_index_versions(
    request: Request,
    _: Annotated[str, Depends(rate_limited_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    status_filter: IndexStatus | None = Query(default=None, alias="status"),  # noqa: B008
) -> IndexVersionListResponse:
    """Return all index versions, optionally filtered by ``?status=``."""
    request_id = _request_id(request)
    versions = await index_version_service.list_versions(db, status=status_filter)
    return IndexVersionListResponse(
        request_id=request_id,
        total=len(versions),
        versions=[IndexVersionSummary.model_validate(v) for v in versions],
    )


@router.get(
    "/index_versions/{index_version}",
    response_model=IndexVersionDetailResponse,
)
async def get_index_version(
    request: Request,
    index_version: str,
    _: Annotated[str, Depends(rate_limited_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> IndexVersionDetailResponse:
    """Return a single index version and its document count."""
    request_id = _request_id(request)
    version = await index_version_service.get_version(db, index_version=index_version)
    if version is None:
        raise _http_404(f"index_version not found: {index_version}", request_id=request_id)
    doc_count = await index_version_service.count_documents_for_version(
        db, index_version=index_version
    )
    return IndexVersionDetailResponse(
        request_id=request_id,
        version=IndexVersionSummary.model_validate(version),
        document_count=doc_count,
    )


@router.post(
    "/index_versions/{index_version}/promote",
    response_model=PromoteIndexResponse,
)
async def promote_index_version(
    request: Request,
    index_version: str,
    admin_user_id: Annotated[str, Depends(rate_limited_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> PromoteIndexResponse:
    """Promote ``index_version`` to :data:`IndexStatus.active`.

    Idempotent on the same target: if the row is already
    active, the call returns ``already_active=True`` and
    does not write an audit row.
    """
    request_id = _request_id(request)
    actor = admin_user_id or ADMIN_USER_ID

    # Snapshot the prior status so we can tell the caller
    # whether the call was a no-op.
    prior = await index_version_service.get_version(db, index_version=index_version)
    if prior is None:
        raise _http_404(f"index_version not found: {index_version}", request_id=request_id)
    already_active = prior.status is IndexStatus.active

    try:
        updated = await index_version_service.promote_version(
            db,
            index_version=index_version,
            admin_user_id=actor,
            request_id=request_id,
        )
    except index_version_service.IndexVersionNotFound as exc:
        # Race: row deleted between the snapshot and the lock.
        raise _http_404(
            f"index_version not found: {exc.index_version}", request_id=request_id
        ) from exc

    # The service does not commit (it leaves the transaction
    # boundary to the caller). The route's FastAPI dependency
    # gives us an ``AsyncSession`` that auto-commits on close
    # only when the route returns successfully — in our setup
    # the get_session generator does an explicit ``commit()``
    # on success and ``rollback()`` on exception. So committing
    # here is enough; the session generator's post-yield code
    # is a no-op when nothing else changed.
    await db.commit()
    await db.refresh(updated)

    promoted_at = updated.promoted_at or datetime.now(UTC)
    return PromoteIndexResponse(
        request_id=request_id,
        index_version=updated.index_version,
        status=updated.status,
        promoted_at=promoted_at,
        already_active=already_active,
    )


# ---------------------------------------------------------------------------
# /v1/admin/evaluations
# ---------------------------------------------------------------------------


@router.get(
    "/evaluations",
    response_model=EvaluationRunListResponse,
)
async def list_evaluations(
    request: Request,
    _: Annotated[str, Depends(rate_limited_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    index_version: str | None = Query(default=None, max_length=64),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
) -> EvaluationRunListResponse:
    """Return the most recent evaluation runs, newest first."""
    request_id = _request_id(request)
    runs = await evaluation_service.list_runs(db, index_version=index_version, limit=limit)
    return EvaluationRunListResponse(
        request_id=request_id,
        total=len(runs),
        runs=[
            EvaluationRunSummary.model_validate(evaluation_service.summarize_run(r)) for r in runs
        ],
    )


@router.get(
    "/evaluations/{run_id}",
    response_model=EvaluationRunDetailResponse,
)
async def get_evaluation(
    request: Request,
    run_id: uuid.UUID,
    _: Annotated[str, Depends(rate_limited_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationRunDetailResponse:
    """Return a single evaluation run (full metrics + failure summary)."""
    request_id = _request_id(request)
    run = await evaluation_service.get_run(db, run_id=run_id)
    if run is None:
        raise _http_404(f"evaluation_run not found: {run_id}", request_id=request_id)
    payload = evaluation_service.summarize_run(run)
    payload["metrics"] = dict(run.metrics or {})
    payload["failure_summary"] = dict(run.failure_summary or {})
    return EvaluationRunDetailResponse(request_id=request_id, run=payload)


# ---------------------------------------------------------------------------
# /v1/admin/ingestion_jobs
# ---------------------------------------------------------------------------


@router.get(
    "/ingestion_jobs",
    response_model=IngestionJobListResponse,
)
async def list_ingestion_jobs(
    request: Request,
    _: Annotated[str, Depends(rate_limited_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
    status_filter: JobStatus | None = Query(default=None, alias="status"),  # noqa: B008
    source_name: str | None = Query(default=None, max_length=64),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
) -> IngestionJobListResponse:
    """Return the most recent ingestion jobs, newest first."""
    request_id = _request_id(request)
    jobs = await ingestion_job_service.list_jobs(
        db,
        status=status_filter,
        source_name=source_name,
        limit=limit,
    )
    return IngestionJobListResponse(
        request_id=request_id,
        total=len(jobs),
        jobs=[IngestionJobSummary.model_validate(j) for j in jobs],
    )


@router.get(
    "/ingestion_jobs/{job_id}",
    response_model=IngestionJobDetailResponse,
)
async def get_ingestion_job(
    request: Request,
    job_id: uuid.UUID,
    _: Annotated[str, Depends(rate_limited_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> IngestionJobDetailResponse:
    """Return a single ingestion job."""
    request_id = _request_id(request)
    job = await ingestion_job_service.get_job(db, job_id=job_id)
    if job is None:
        raise _http_404(f"ingestion_job not found: {job_id}", request_id=request_id)
    return IngestionJobDetailResponse(
        request_id=request_id,
        job=IngestionJobSummary.model_validate(job),
    )
