"""Answer cache package (Slice 5).

Provides the :class:`AnswerCacheStore` seam and the deterministic
:class:`CachedAnswer` value object the answer engine (Slice 6)
consumes. Storage is the ``AnswerCache`` table from :mod:`app.models`
— the retrieval-result cache (Redis) is a Slice 6 concern and is not
implemented here.
"""

from app.cache.answer_cache import (
    AnswerCacheStore,
    CachedAnswer,
    NoOpAnswerCacheStore,
    PostgresAnswerCacheStore,
    build_cache_key,
)
from app.cache.factory import build_answer_cache_store

__all__ = [
    "AnswerCacheStore",
    "CachedAnswer",
    "NoOpAnswerCacheStore",
    "PostgresAnswerCacheStore",
    "build_answer_cache_store",
    "build_cache_key",
]
