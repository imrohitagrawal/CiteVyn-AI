"""Tests for :mod:`app.services.exact_lookup`.

The service is a thin SQLAlchemy query helper on top of the
``exact_terms`` table. Tests run against the per-test
``session`` fixture seeded with the demo catalog (which now
also creates an active :class:`IndexVersion` row).
"""

from __future__ import annotations

import uuid

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
        await session.execute(select(IndexVersion).where(IndexVersion.status == IndexStatus.active))
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
        await session.execute(select(IndexVersion).where(IndexVersion.status == IndexStatus.active))
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
        await session.execute(select(IndexVersion).where(IndexVersion.status == IndexStatus.active))
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
    hits = await exact_lookup(session, term="", product_area="codex", index_version="active")
    assert hits == []


@pytest.mark.asyncio
async def test_exact_lookup_returns_empty_on_empty_product_area(
    session,
) -> None:
    """Empty ``product_area`` short-circuits — global search is not supported."""
    await _seed(session)
    hits = await exact_lookup(session, term="--model", product_area="", index_version="active")
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
        await session.execute(select(IndexVersion).where(IndexVersion.status == IndexStatus.active))
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

    hits = await exact_lookup(session, term="--model", product_area="codex", limit=1000)
    assert len(hits) == MAX_RESULTS


def test_max_results_constant_is_a_positive_int() -> None:
    """The cap is exported and is a positive integer."""
    assert isinstance(MAX_RESULTS, int)
    assert MAX_RESULTS >= 1
    assert MAX_RESULTS <= 100


@pytest.mark.asyncio
async def test_exact_lookup_pins_to_specific_index_version(session) -> None:
    """An explicit non-active ``index_version`` is honoured (replay path).

    Two non-active index versions both contain a term that the
    active index does not. Passing the version key returns the
    row; passing the other version returns nothing. This locks
    the replay / debugging branch the docstring advertises.
    """
    await _seed(session)
    from datetime import UTC, datetime

    from app.models.documents import Document
    from app.models.enums import DocumentStatus
    from app.models.exact_terms import ExactTerm
    from app.models.index_versions import IndexVersion

    # Two non-active index versions, both inactive. (active is
    # the seeded row; we explicitly avoid promoting ours so the
    # active-row filter would skip them.)
    now = datetime.now(UTC)
    v_old = IndexVersion(
        index_version="v-old-replay",
        status=IndexStatus.candidate,
        source_version_hash="sha256:replay-old",
        created_at=now,
        promoted_at=None,
    )
    v_new = IndexVersion(
        index_version="v-new-replay",
        status=IndexStatus.candidate,
        source_version_hash="sha256:replay-new",
        created_at=now,
        promoted_at=None,
    )
    session.add_all([v_old, v_new])
    await session.flush()

    # Only v_old has the term we're looking for.
    doc_old = Document(
        index_version=v_old.index_version,
        source_name="replay-old-src",
        product_area="replay",
        source_url="https://example.com/old",
        title="Replay old",
        content_checksum="x" * 64,
        last_fetched_at=now,
        status=DocumentStatus.active,
    )
    session.add(doc_old)
    await session.flush()

    session.add(
        ExactTerm(
            term_text="--replay-flag",
            product_area="replay",
            term_type=TermType.flag,
            document_id=doc_old.document_id,
            chunk_id=uuid.uuid4(),
        )
    )
    await session.flush()

    # Pin to the version that has the row.
    hits = await exact_lookup(
        session,
        term="--replay-flag",
        product_area="replay",
        index_version=v_old.index_version,
    )
    assert len(hits) == 1
    assert hits[0].index_version == v_old.index_version
    assert hits[0].term_text == "--replay-flag"

    # Pin to the version that does not have the row.
    hits_other = await exact_lookup(
        session,
        term="--replay-flag",
        product_area="replay",
        index_version=v_new.index_version,
    )
    assert hits_other == []


@pytest.mark.asyncio
async def test_exact_lookup_pinned_version_skips_active_filter(session) -> None:
    """A pinned (non-active) version returns rows even if not currently active.

    Locks the difference between ``"active"`` and a specific
    string: with the latter, the ``status='active'`` filter is
    skipped entirely. Without the test, a regression that
    *also* filters on active when a key is supplied would pass
    every other test in this file.
    """
    await _seed(session)
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.documents import Document
    from app.models.enums import DocumentStatus
    from app.models.exact_terms import ExactTerm
    from app.models.index_versions import IndexVersion

    # Confirm the active row is "v1-..." (seed value), and add a
    # candidate (not active) version with its own term.
    active = (
        await session.execute(select(IndexVersion).where(IndexVersion.status == IndexStatus.active))
    ).scalar_one()
    assert active.status is IndexStatus.active

    candidate = IndexVersion(
        index_version="v-candidate-1",
        status=IndexStatus.candidate,
        source_version_hash="sha256:cand",
        created_at=datetime.now(UTC),
        promoted_at=None,
    )
    session.add(candidate)
    await session.flush()

    doc = Document(
        index_version=candidate.index_version,
        source_name="cand-src",
        product_area="cand",
        source_url="https://example.com/cand",
        title="Candidate",
        content_checksum="y" * 64,
        last_fetched_at=datetime.now(UTC),
        status=DocumentStatus.active,
    )
    session.add(doc)
    await session.flush()

    session.add(
        ExactTerm(
            term_text="--cand-only",
            product_area="cand",
            term_type=TermType.flag,
            document_id=doc.document_id,
            chunk_id=uuid.uuid4(),
        )
    )
    await session.flush()

    # With 'active', the candidate's row is invisible.
    hits_active = await exact_lookup(
        session,
        term="--cand-only",
        product_area="cand",
        index_version="active",
    )
    assert hits_active == []

    # With the explicit candidate key, the row is found even
    # though that index is not active.
    hits_candidate = await exact_lookup(
        session,
        term="--cand-only",
        product_area="cand",
        index_version=candidate.index_version,
    )
    assert len(hits_candidate) == 1
