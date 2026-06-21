"""Tests for :class:`app.models.base.PickledEmbedding` and the
``Chunk.embedding`` column.

The decorator is dialect-agnostic: on SQLite it lands in a
``BLOB`` column, on Postgres in a ``bytea`` column. Tests run
against the per-test in-memory SQLite engine so they exercise
the same code path the production retriever uses on either
backend.
"""

from __future__ import annotations

import pickle
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.base import PickledEmbedding
from app.models.chunks import Chunk
from app.models.documents import Document
from app.models.enums import DocumentStatus
from app.models.index_versions import IndexStatus, IndexVersion


@pytest_asyncio.fixture
async def active_index_version(session) -> str:
    """Insert an active IndexVersion row and a parent Document.

    The ``chunks`` table has a foreign key on
    ``documents.document_id``; tests need a real parent row
    before they can insert a chunk.
    """
    now = datetime.now(UTC)
    index_version = "v1-embedding-test"
    session.add(
        IndexVersion(
            index_version=index_version,
            status=IndexStatus.active,
            source_version_hash="sha256:embed-test",
            created_at=now,
            promoted_at=now,
        )
    )
    await session.flush()
    session.add(
        Document(
            index_version=index_version,
            source_name="test-source",
            product_area="test",
            source_url="https://example.com/test",
            title="Test document",
            content_checksum="abc" * 22,
            last_fetched_at=now,
            status=DocumentStatus.active,
        )
    )
    await session.flush()
    return index_version


def _make_chunk(document_id, embedding=None) -> Chunk:
    """Build a Chunk with all required fields populated."""
    return Chunk(
        document_id=document_id,
        product_area="test",
        section_path="flags",
        heading="flags",
        parent_heading=None,
        chunk_text="--model selects the model.",
        context_summary="flags",
        chunk_order=0,
        content_checksum="chk_embed_test",
        exact_terms=[],
        embedding=embedding,
    )


async def _first_document_id(session):
    doc = (await session.execute(select(Document).limit(1))).scalar_one()
    return doc.document_id


@pytest.mark.asyncio
async def test_chunk_embedding_round_trips(session, active_index_version) -> None:
    """A list[float] embedding persists and reads back identically."""
    document_id = await _first_document_id(session)
    embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    chunk = _make_chunk(document_id=document_id, embedding=embedding)
    session.add(chunk)
    await session.commit()

    # Detach and re-read.
    await session.refresh(chunk)
    assert chunk.embedding == embedding


@pytest.mark.asyncio
async def test_chunk_embedding_defaults_to_none(session, active_index_version) -> None:
    """A chunk without an embedding has ``embedding is None``."""
    document_id = await _first_document_id(session)
    chunk = _make_chunk(document_id=document_id, embedding=None)
    session.add(chunk)
    await session.commit()

    await session.refresh(chunk)
    assert chunk.embedding is None


@pytest.mark.asyncio
async def test_chunk_embedding_persists_large_vector(session, active_index_version) -> None:
    """A 1536-dim vector (the dim the Anthropic embedder targets) round-trips."""
    document_id = await _first_document_id(session)
    embedding = [round(i * 0.0006510416666666667, 10) for i in range(1536)]
    chunk = _make_chunk(document_id=document_id, embedding=embedding)
    session.add(chunk)
    await session.commit()

    await session.refresh(chunk)
    assert chunk.embedding is not None
    assert len(chunk.embedding) == 1536
    # Floating-point equality after a pickle round-trip is exact
    # (pickle preserves the bytes), so the test can be strict.
    assert chunk.embedding == embedding


@pytest.mark.asyncio
async def test_chunk_embedding_handles_negative_and_zero_values(
    session, active_index_version
) -> None:
    """Embeddings are signed; the round-trip must preserve sign and zero."""
    document_id = await _first_document_id(session)
    embedding = [-1.0, 0.0, 0.5, -0.25, 1.0]
    chunk = _make_chunk(document_id=document_id, embedding=embedding)
    session.add(chunk)
    await session.commit()

    await session.refresh(chunk)
    assert chunk.embedding == embedding


# ---------------------------------------------------------------------------
# TypeDecorator unit tests
# ---------------------------------------------------------------------------


def test_pickled_embedding_returns_none_for_none() -> None:
    """``None`` round-trips as ``None`` (the column is nullable)."""
    decorator = PickledEmbedding()
    bound = decorator.process_bind_param(None, dialect=_NullDialect())
    assert bound is None
    result = decorator.process_result_value(None, dialect=_NullDialect())
    assert result is None


def test_pickled_embedding_pickles_list_to_bytes() -> None:
    """The bind value is pickle bytes, not the raw list."""
    decorator = PickledEmbedding()
    bound = decorator.process_bind_param([1.0, 2.0, 3.0], dialect=_NullDialect())
    assert isinstance(bound, bytes)
    # Round-tripping the bytes gives the same list back.
    assert pickle.loads(bound) == [1.0, 2.0, 3.0]


def test_pickled_embedding_rejects_non_sequence() -> None:
    """A non-list value is rejected with a clear TypeError."""
    decorator = PickledEmbedding()
    with pytest.raises(TypeError) as exc_info:
        decorator.process_bind_param({"a": 1}, dialect=_NullDialect())
    assert "embedding" in str(exc_info.value)


def test_pickled_embedding_rejects_nested_dict() -> None:
    """A dict is not a list, even if it contains numbers."""
    decorator = PickledEmbedding()
    with pytest.raises(TypeError):
        decorator.process_bind_param({"values": [1.0]}, dialect=_NullDialect())


def test_pickled_embedding_rejects_tuple() -> None:
    """Tuples are not ``list`` — convert at the producer."""
    decorator = PickledEmbedding()
    with pytest.raises(TypeError, match="must be a list"):
        decorator.process_bind_param((1.0, 2.0), dialect=_NullDialect())


def test_pickled_embedding_result_is_plain_list() -> None:
    """The unpickled value is always a plain ``list`` (not numpy)."""
    decorator = PickledEmbedding()
    bound = decorator.process_bind_param([1.0, 2.0], dialect=_NullDialect())
    loaded = decorator.process_result_value(bound, dialect=_NullDialect())
    assert isinstance(loaded, list)
    assert loaded == [1.0, 2.0]


def test_pickled_embedding_preserves_precision() -> None:
    """Floating-point precision is preserved by pickle (no truncation)."""
    decorator = PickledEmbedding()
    embedding = [0.123456789012345, -0.987654321098765]
    bound = decorator.process_bind_param(embedding, dialect=_NullDialect())
    loaded = decorator.process_result_value(bound, dialect=_NullDialect())
    assert loaded == embedding


def test_pickled_embedding_uses_large_binary_impl() -> None:
    """The TypeDecorator's impl is LargeBinary (BLOB/bytea)."""
    from sqlalchemy import LargeBinary

    assert PickledEmbedding.impl is LargeBinary or issubclass(PickledEmbedding.impl, LargeBinary)


def test_pickled_embedding_rejects_numpy_array() -> None:
    """NumPy arrays must be converted to ``list[float]`` at the producer.

    The decorator's contract is :class:`list` of :class:`float`.
    Accepting a numpy array here would push a coercion
    responsibility into the storage layer that belongs in the
    embedder. The test is gated with :func:`pytest.importorskip`
    so it skips when numpy is not installed (it is not a hard
    project dependency).
    """
    np = pytest.importorskip("numpy")
    decorator = PickledEmbedding()
    arr = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    with pytest.raises(TypeError, match="must be a list"):
        decorator.process_bind_param(arr, dialect=_NullDialect())


def test_pickled_embedding_cache_ok_is_true() -> None:
    """``cache_ok=True`` so SQLAlchemy can share the type in the type cache."""
    assert PickledEmbedding.cache_ok is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _NullDialect:
    """Stand-in dialect object with ``.name == 'sqlite'``.

    The :class:`PickledEmbedding` decorator doesn't branch on
    the dialect, so any object works. ``name`` is read by
    other decorators (e.g. :class:`GUID`) — included here to
    be safe.
    """

    name = "sqlite"
