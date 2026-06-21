"""Search HTTP routes (Slice 8 step 3).

* ``POST /v1/search/exact`` — exact-term lookup. The intent is
  "did the user paste a known flag, command, config key, model
  name, etc.?" and short-circuit the answer pipeline. Backed
  by :func:`app.services.exact_lookup.exact_lookup`.
* ``GET /health/index`` — moved here from the placeholder
  health module so it lives next to its sibling search route
  and so it can read the real :class:`IndexVersion` rows.

Both endpoints sit behind :func:`require_demo_api_key` for the
search route; the index-health route is unauthenticated so a
load balancer can probe it.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.rate_limit import rate_limited_demo
from app.models.enums import IndexStatus, TermType
from app.models.index_versions import IndexVersion
from app.services.exact_lookup import (
    MAX_RESULTS,
    ExactLookupHit,
    exact_lookup,
)

router = APIRouter(tags=["search"])


def _request_id(request: Request) -> str:
    """Return the request id stamped on :class:`Request` by the middleware."""
    return str(request.state.request_id)


# ---------------------------------------------------------------------------
# /v1/search/exact
# ---------------------------------------------------------------------------


class ExactSearchRequest(BaseModel):
    """Body for ``POST /v1/search/exact``.

    ``term`` is the verbatim string the user pasted (e.g.
    ``"--max-tokens"``). ``product_area`` is required so we
    never run an unscoped global lookup — the same flag name
    in two products can mean different things.
    """

    term: str = Field(min_length=1, max_length=512)
    product_area: str = Field(min_length=1, max_length=64)
    term_type: TermType | None = None
    index_version: str = Field(default="active", max_length=64)
    limit: int = Field(default=10, ge=1, le=MAX_RESULTS)


class ExactSearchHit(BaseModel):
    """One hit in the response list."""

    term_id: uuid.UUID
    term_text: str
    term_type: TermType
    product_area: str
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    index_version: str
    score: float


class ExactSearchResponse(BaseModel):
    """Response envelope for :http:post:`/v1/search/exact`."""

    request_id: str
    query: str
    product_area: str
    index_version: str
    total: int
    hits: list[ExactSearchHit]


@router.post("/v1/search/exact", response_model=ExactSearchResponse)
async def search_exact(
    request: Request,
    body: Annotated[ExactSearchRequest, Body()],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_session)],
    _user_id: Annotated[str, Depends(rate_limited_demo)],
) -> ExactSearchResponse:
    """Return exact-term matches for ``body.term`` in ``body.product_area``.

    The demo path runs as a single :data:`DEMO_USER_ID`; the
    per-user limiter still applies so a flood of exact searches
    doesn't starve the answer endpoint. The ``rate_limited_demo``
    dependency chains :func:`require_demo_api_key` with
    :func:`enforce_rate_limit` so every authenticated route
    shares one enforcement path.
    """
    request_id = _request_id(request)

    hits: list[ExactLookupHit] = await exact_lookup(
        db,
        term=body.term,
        product_area=body.product_area,
        term_type=body.term_type,
        index_version=body.index_version,
        limit=body.limit,
    )

    return ExactSearchResponse(
        request_id=request_id,
        query=body.term,
        product_area=body.product_area,
        index_version=body.index_version,
        total=len(hits),
        hits=[
            ExactSearchHit(
                term_id=uuid.UUID(hit.term_id),
                term_text=hit.term_text,
                term_type=hit.term_type,
                product_area=hit.product_area,
                document_id=uuid.UUID(hit.document_id),
                chunk_id=uuid.UUID(hit.chunk_id),
                index_version=hit.index_version,
                score=hit.score,
            )
            for hit in hits
        ],
    )


# ---------------------------------------------------------------------------
# /health/index
# ---------------------------------------------------------------------------


@router.get("/health/index")
async def health_index(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Report the active and previous-good index versions.

    Reads the :class:`IndexVersion` table; returns a 200 with
    ``status="pre_index"`` and ``active_index=None`` when no
    index has been promoted yet. The shape matches the
    Slice 1 placeholder so the load balancer / dashboard
    doesn't need a code change.
    """
    request_id = _request_id(request)

    # Fetch the active and previous_good rows in one roundtrip.
    # A "no row" return is not an error — pre-index is a valid
    # state during cold start.
    stmt = select(IndexVersion).where(
        IndexVersion.status.in_((IndexStatus.active, IndexStatus.previous_good))
    )
    rows = (await db.execute(stmt)).scalars().all()

    active = next((r for r in rows if r.status is IndexStatus.active), None)
    previous = next((r for r in rows if r.status is IndexStatus.previous_good), None)

    if active is None and previous is None:
        return {
            "request_id": request_id,
            "status": "pre_index",
            "active_index": None,
            "previous_good_index": None,
            "message": "No active index exists yet.",
        }

    return {
        "request_id": request_id,
        "status": "ready" if active is not None else "degraded",
        "active_index": _index_payload(active) if active else None,
        "previous_good_index": _index_payload(previous) if previous else None,
        "message": None,
    }


def _index_payload(row: IndexVersion) -> dict[str, Any]:
    """Project an :class:`IndexVersion` row into the response shape."""
    return {
        "index_version": row.index_version,
        "source_version_hash": row.source_version_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "promoted_at": row.promoted_at.isoformat() if row.promoted_at else None,
        "evaluation_run_id": str(row.evaluation_run_id) if row.evaluation_run_id else None,
    }


__all__ = ["router", "search_exact", "health_index"]
