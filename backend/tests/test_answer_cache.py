"""Answer cache tests.

Pins the Slice 5 contracts:

* :class:`PostgresAnswerCacheStore` round-trips a :class:`CachedAnswer`
  through the ``AnswerCache`` table using the in-memory SQLite engine
  from ``tests/conftest.py``.
* :class:`NoOpAnswerCacheStore` always misses and writes nothing.
* :func:`build_cache_key` is deterministic and changes when
  ``source_version_hash`` changes (the cache-invalidation contract
  from ``docs/ARCHITECTURE.md`` §5.3).
* :func:`build_answer_cache_store` selects the no-op variant when
  ``settings.cache_enabled`` is False.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.answer_cache import (
    CachedAnswer,
    NoOpAnswerCacheStore,
    PostgresAnswerCacheStore,
    build_cache_key,
)
from app.cache.factory import build_answer_cache_store
from app.core.config import Settings
from app.models import AnswerCache, Confidence


def _now() -> datetime:
    return datetime.now(UTC)


def _sample(*, ttl_offset_seconds: int = 3600) -> CachedAnswer:
    return CachedAnswer(
        answer="Cited answer [1].",
        citations=[{"chunk_id": "abc", "url": "https://docs.test/x"}],
        confidence=Confidence.high,
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
        created_at=_now(),
        ttl_expires_at=_now() + timedelta(seconds=ttl_offset_seconds),
    )


# ---------------------------------------------------------------------------
# build_cache_key
# ---------------------------------------------------------------------------


def test_build_cache_key_is_stable() -> None:
    args = dict(
        normalized_question="how do I configure permissions",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )
    assert build_cache_key(**args) == build_cache_key(**args)


def test_build_cache_key_changes_with_source_version_hash() -> None:
    """The cache invalidation contract: bumping the source checksum
    MUST produce a new key so the next read is a miss."""
    base = dict(
        normalized_question="q",
        product_area="codex",
        source_version_hash="sha256:old",
        answer_policy_version="v1",
    )
    bumped = {**base, "source_version_hash": "sha256:new"}
    assert build_cache_key(**base) != build_cache_key(**bumped)


def test_build_cache_key_changes_with_question() -> None:
    base = dict(
        normalized_question="q1",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )
    assert build_cache_key(**base) != build_cache_key(**{**base, "normalized_question": "q2"})


def test_build_cache_key_changes_with_product_area() -> None:
    base = dict(
        normalized_question="q",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )
    assert build_cache_key(**base) != build_cache_key(**{**base, "product_area": "codex"})


def test_build_cache_key_changes_with_policy_version() -> None:
    base = dict(
        normalized_question="q",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )
    assert build_cache_key(**base) != build_cache_key(**{**base, "answer_policy_version": "v2"})


def test_build_cache_key_format_is_hex_sha256() -> None:
    """Sanity check: the digest is a 64-char hex string so it fits
    the ``AnswerCache.cache_key`` VARCHAR(256) column."""
    key = build_cache_key(
        normalized_question="q",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


# ---------------------------------------------------------------------------
# PostgresAnswerCacheStore
# ---------------------------------------------------------------------------


async def test_postgres_store_round_trips_cached_answer(session: AsyncSession) -> None:
    store = PostgresAnswerCacheStore(session)
    value = _sample()
    key = build_cache_key(
        normalized_question="q",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )

    assert await store.get(cache_key=key) is None
    await store.put(cache_key=key, value=value)
    await session.commit()

    loaded = await store.get(cache_key=key)
    assert loaded is not None
    assert loaded.answer == value.answer
    assert loaded.citations == value.citations
    assert loaded.confidence == value.confidence
    assert loaded.source_version_hash == value.source_version_hash
    assert loaded.answer_policy_version == value.answer_policy_version

    # Row exists in the underlying table.
    row = await session.scalar(select(AnswerCache).where(AnswerCache.cache_key == key))
    assert row is not None
    assert row.answer == value.answer


async def test_postgres_store_treats_expired_row_as_miss(session: AsyncSession) -> None:
    """``ttl_expires_at`` in the past must be reported as a miss so the
    orchestrator re-generates the answer."""
    store = PostgresAnswerCacheStore(session)
    value = _sample(ttl_offset_seconds=-10)
    key = build_cache_key(
        normalized_question="q",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )
    await store.put(cache_key=key, value=value)
    await session.commit()

    assert await store.get(cache_key=key) is None


async def test_postgres_store_upsert_overwrites_existing_row(session: AsyncSession) -> None:
    """``put`` is idempotent: writing the same key twice updates the
    row in place rather than inserting a duplicate."""
    store = PostgresAnswerCacheStore(session)
    key = build_cache_key(
        normalized_question="q",
        product_area="claude_code",
        source_version_hash="sha256:abc",
        answer_policy_version="v1",
    )
    first = _sample()
    first.answer = "first"
    second = _sample()
    second.answer = "second"

    await store.put(cache_key=key, value=first)
    await store.put(cache_key=key, value=second)
    await session.commit()

    rows = (
        (await session.execute(select(AnswerCache).where(AnswerCache.cache_key == key)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].answer == "second"

    loaded = await store.get(cache_key=key)
    assert loaded is not None
    assert loaded.answer == "second"


# ---------------------------------------------------------------------------
# NoOpAnswerCacheStore
# ---------------------------------------------------------------------------


async def test_noop_store_always_misses() -> None:
    store = NoOpAnswerCacheStore()
    assert await store.get(cache_key="any") is None
    # Even after a put, get must miss.
    await store.put(cache_key="any", value=_sample())
    assert await store.get(cache_key="any") is None


async def test_noop_store_put_is_silent() -> None:
    """``put`` should not raise and should not require a DB session."""
    store = NoOpAnswerCacheStore()
    await store.put(cache_key="any", value=_sample())


# ---------------------------------------------------------------------------
# build_answer_cache_store factory
# ---------------------------------------------------------------------------


def test_factory_returns_postgres_when_cache_enabled(session: AsyncSession) -> None:
    settings = Settings(cache_enabled=True)
    store = build_answer_cache_store(settings, session)
    assert isinstance(store, PostgresAnswerCacheStore)


def test_factory_returns_noop_when_cache_disabled(session: AsyncSession) -> None:
    settings = Settings(cache_enabled=False)
    store = build_answer_cache_store(settings, session)
    assert isinstance(store, NoOpAnswerCacheStore)
