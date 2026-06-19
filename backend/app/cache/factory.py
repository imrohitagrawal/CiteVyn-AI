"""Factory for the answer cache store.

Mirrors :func:`app.llm.factory.build_llm_client` and
:func:`app.retrieval.vector.build_embedder`: takes :class:`Settings`
and the request-scoped :class:`AsyncSession`, returns the concrete
store the orchestrator should use for this request.

When ``settings.cache_enabled`` is False, the factory returns
:class:`NoOpAnswerCacheStore` so the orchestrator's cache calls
remain on the hot path but never touch the database.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.answer_cache import (
    AnswerCacheStore,
    NoOpAnswerCacheStore,
    PostgresAnswerCacheStore,
)
from app.core.config import Settings


def build_answer_cache_store(
    settings: Settings,
    session: AsyncSession,
) -> AnswerCacheStore:
    """Resolve the answer cache store for this request.

    ``settings.cache_enabled=False`` → :class:`NoOpAnswerCacheStore`.
    Otherwise → :class:`PostgresAnswerCacheStore` backed by ``session``.
    """
    if not settings.cache_enabled:
        return NoOpAnswerCacheStore()
    return PostgresAnswerCacheStore(session)


__all__ = ["build_answer_cache_store"]
