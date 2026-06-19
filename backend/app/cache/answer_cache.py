"""Answer cache layer.

The answer cache stores the result of a successful grounded answer so
the next request with the same (question, product area, source version)
can skip retrieval and generation. Backed by the ``AnswerCache`` table
from :mod:`app.models` (no Redis — the retrieval-result cache is a
Slice 6 concern and lives elsewhere).

Cache key composition (per ``docs/ARCHITECTURE.md`` §5.3):

    normalized_question
    || "\x1f" || product_area
    || "\x1f" || source_version_hash
    || "\x1f" || answer_policy_version

The SHA-256 hex digest of the concatenation is the cache key. A
``source_version_hash`` change MUST change the key, so cached answers
are invalidated when the underlying evidence corpus moves
(``test_answer_cache.py`` pins that contract).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnswerCache
from app.models.enums import Confidence

# Field separator for the cache key pre-image. ``\x1f`` (Unit Separator)
# is a non-printing ASCII control char that cannot appear in a question
# or product area, so it cannot introduce a collision.
_KEY_SEPARATOR = "\x1f"


class CachedAnswer(BaseModel):
    """Snapshot of a grounded answer suitable for serving from cache.

    Mirrors ``docs/API_SPEC.md`` §5 minus the request/session routing
    fields (those are computed per request, not stored).
    """

    answer: str
    citations: list[dict[str, Any]]
    confidence: Confidence
    source_version_hash: str
    answer_policy_version: str
    created_at: datetime
    ttl_expires_at: datetime


@runtime_checkable
class AnswerCacheStore(Protocol):
    """Storage seam for the answer cache.

    The orchestrator (Slice 6) consumes this protocol so the
    production Postgres path and the test no-op path are
    interchangeable.
    """

    async def get(self, *, cache_key: str) -> CachedAnswer | None: ...

    async def put(self, *, cache_key: str, value: CachedAnswer) -> None: ...


def build_cache_key(
    *,
    normalized_question: str,
    product_area: str,
    source_version_hash: str,
    answer_policy_version: str,
) -> str:
    """Build a deterministic SHA-256 cache key from the four inputs.

    Concatenation order (separator ``\\x1f`` between fields):

        normalized_question || product_area || source_version_hash
        || answer_policy_version

    Changing ``source_version_hash`` MUST change the key so the cache
    is invalidated when the underlying evidence corpus moves; the
    test suite pins that contract.
    """
    pre_image = _KEY_SEPARATOR.join(
        (
            normalized_question,
            product_area,
            source_version_hash,
            answer_policy_version,
        )
    )
    return hashlib.sha256(pre_image.encode("utf-8")).hexdigest()


def _to_cached_answer(row: AnswerCache) -> CachedAnswer:
    return CachedAnswer(
        answer=row.answer,
        citations=list(row.citations),
        confidence=row.confidence,
        source_version_hash=row.source_version_hash,
        answer_policy_version=row.answer_policy_version,
        created_at=row.created_at,
        ttl_expires_at=row.ttl_expires_at,
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _to_naive(value: datetime) -> datetime:
    """Return ``value`` as a naive UTC datetime.

    SQLite (the hermetic test engine) strips tzinfo on round-trip, so a
    value written via ``datetime.now(UTC)`` reads back as naive. We
    normalize before comparing so the TTL check works on both
    dialects.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class PostgresAnswerCacheStore:
    """Answer cache backed by the ``AnswerCache`` table.

    The store writes via :meth:`AsyncSession.merge` (idempotent upsert
    keyed on ``cache_key``) and reads via a primary-key ``SELECT``.
    Expired rows (``ttl_expires_at`` <= now) are treated as a miss so
    the caller re-generates the answer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, cache_key: str) -> CachedAnswer | None:
        row = await self._session.get(AnswerCache, cache_key)
        if row is None:
            return None
        if _to_naive(row.ttl_expires_at) <= _to_naive(_utcnow()):
            return None
        row.last_used_at = _utcnow()
        await self._session.flush()
        return _to_cached_answer(row)

    async def put(self, *, cache_key: str, value: CachedAnswer) -> None:
        now = _utcnow()
        row = AnswerCache(
            cache_key=cache_key,
            normalized_question="",  # not yet populated by the orchestrator
            product_area="",  # ditto
            answer=value.answer,
            citations=list(value.citations),
            source_version_hash=value.source_version_hash,
            answer_policy_version=value.answer_policy_version,
            confidence=value.confidence,
            ttl_expires_at=value.ttl_expires_at,
            created_at=now,
            last_used_at=now,
        )
        await self._session.merge(row)
        await self._session.flush()


class NoOpAnswerCacheStore:
    """Inert cache for tests and disabled-cache paths.

    :meth:`get` always returns ``None`` and :meth:`put` is a no-op so
    the orchestrator's cache calls stay no-ops without a DB roundtrip.
    """

    async def get(self, *, cache_key: str) -> CachedAnswer | None:
        del cache_key
        return None

    async def put(self, *, cache_key: str, value: CachedAnswer) -> None:
        del cache_key, value
        return None


__all__ = [
    "AnswerCacheStore",
    "CachedAnswer",
    "NoOpAnswerCacheStore",
    "PostgresAnswerCacheStore",
    "build_cache_key",
]
