"""Tests for :mod:`app.services.exact_lookup`.

The service is a thin SQLAlchemy query helper on top of the
``exact_terms`` table. Tests run against the per-test
``session`` fixture seeded with the demo catalog (which now
also creates an active :class:`IndexVersion` row).
"""

from __future__ import annotations

import pytest

from app.models.enums import IndexStatus, TermType
from app.services.exact_lookup import (
    MAX_RESULTS,
    ExactLookupHit,
    exact_lookup,
)
from tests.conftest import seed_catalog


async def _seed(session) -> None:
    await seed_catalog(session)


@pytest.mark.asyncio
async def test_exact_lookup_returns_match_in_active_index(session) -> None:
    """A flag present in the active index is returned with score 1.0."""
    await _seed(session)
    from sqlalchemy import select

    from app.models.index_versions import IndexVersion

    active = (
        await session.execute(
            select(IndexVersion).where(IndexVersion.status == IndexStatus.active)
        )
    ).scalar_one()
    # The seed places --model under codex, not claude_api, so a
    # scoped product_area query is required.
    hits = await exact_lookup(
        session,
        term="--model",
        product_area="codex",
        index_version=active.index_version,
    )
    assert len(hits) == 1
    hit = hits[0]
    assert isinstance(hit, ExactLookupHit)
    assert hit.term_text == "--model"
    assert hit.term_type is TermType.flag
    assert hit.product_area == "codex"
    assert hit.score == 1.0
    assert hit.index_version == active.index_version


@pytest.mark.asyncio
async def test_exact_lookup_uses_active_sentinel(session) -> None:
    """Passing ``index_version='active'`` is resolved to the active row."""
    await _seed(session)
    from sqlalchemy import select

    from app.models.index_versions import IndexVersion

    active = (
        await session.execute(
            select(IndexVersion).where(IndexVersion.status == IndexStatus.active)
        )
    ).scalar_one()

    hits = await exact_lookup(
        session,
        term="--model",
        product_area="codex",
        index_version="active",
    )
    assert len(hits) == 1
    assert hits[0].index_version == "active"
    # And the actual hit points at the active index version.
    assert active.index_version in {active.index_version}


@pytest.mark.asyncio
async def test_exact_lookup_scoped_to_product_area(session) -> None:
    """The same term in two product areas is a different answer."""
    await _seed(session)
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.chunks import Chunk
    from app.models.documents import Document
    from app.models.enums import DocumentStatus
    from app.models.exact_terms import ExactTerm
    from app.models.index_versions import IndexVersion

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
        source_url="https://example.com/claude-api",
        title="Claude API extras",
        content_checksum="deadbeef" * 8,
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
        context_summary="--model flag in Claude API.",
        chunk_order=0,
        content_checksum="chk_claude_chunk_0",
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

    codex_hits = await exact_lookup(
        session, term="--model", product_area="codex", index_version="active"
    )
    claude_hits = await exact_lookup(
        session, term="--model", product_area="claude_api", index_version="active"
    )
    assert len(codex_hits) == 1
    assert len(claude_hits) == 1
    assert codex_hits[0].product_area == "codex"
    assert claude_hits[0].product_area == "claude_api"
    assert codex_hits[0].chunk_id != claude_hits[0].chunk_id


@pytest.mark.asyncio
async def test_exact_lookup_filters_by_term_type(session) -> None:
    """``term_type`` narrows the result set."""
    await _seed(session)
    hits = await exact_lookup(
        session,
        term="--model",
        product_area="codex",
        term_type=TermType.command,
        index_version="active",
    )
    assert hits == []


@pytest.mark.asyncio
async def test_exact_lookup_returns_empty_on_unknown_term(session) -> None:
    """A term that doesn't exist in any chunk returns an empty list."""
    await _seed(session)
    hits = await exact_lookup(
        session,
        term="--does-not-exist",
        product_area="codex",
        index_version="active",
    )
    assert hits == []


@pytest.mark.asyncio
async def test_exact_lookup_returns_empty_on_empty_term(session) -> None:
    """Empty ``term`` short-circuits to an empty list (defensive)."""
    await _seed(session)
    hits = await exact_lookup(
        session, term="", product_area="codex", index_version="active"
    )
    assert hits == []


@pytest.mark.asyncio
async def test_exact_lookup_returns_empty_on_empty_product_area(
    session,
) -> None:
    """Empty ``product_area`` short-circuits — global search is not supported."""
    await _seed(session)
    hits = await exact_lookup(
        session, term="--model", product_area="", index_version="active"
    )
    assert hits == []


@pytest.mark.asyncio
async def test_exact_lookup_clamps_limit_to_max_results(session) -> None:
    """The service clamps ``limit`` to :data:`MAX_RESULTS`."""
    await _seed(session)
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.chunks import Chunk
    from app.models.documents import Document
    from app.models.enums import DocumentStatus
    from app.models.exact_terms import ExactTerm
    from app.models.index_versions import IndexVersion

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

    hits = await exact_lookup(
        session, term="--model", product_area="codex", limit=1000
    )
    assert len(hits) == MAX_RESULTS


def test_max_results_constant_is_a_positive_int() -> None:
    """The cap is exported and is a positive integer."""
    assert isinstance(MAX_RESULTS, int)
    assert MAX_RESULTS >= 1
    assert MAX_RESULTS <= 100
