"""Slice 4 retrieval layer.

Composes the four orthogonal ways the system finds relevant chunks:

* :mod:`app.retrieval.exact` — term-table lookup for flags, env vars, etc.
* :mod:`app.retrieval.keyword` — SQL ``LIKE`` over chunk_text (placeholder
  for the Postgres FTS work that lands with Slice 3 ingestion).
* :mod:`app.retrieval.vector` — pgvector cosine-distance query (stubbed
  on SQLite).
* :mod:`app.retrieval.rerank` — identity reranker (swap point for a
  cross-encoder later).

The :mod:`app.retrieval.hybrid` orchestrator runs the three retrievers,
deduplicates by ``chunk_id``, weights the scores, and hands off to the
reranker.
"""

from app.retrieval.exact import ExactRetriever
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.rerank import Reranker
from app.retrieval.types import EvidenceHit, RetrievedChunk, chunk_to_citation
from app.retrieval.vector import Embedder, StubEmbedder, VectorRetriever, build_embedder

__all__ = [
    "Embedder",
    "EvidenceHit",
    "ExactRetriever",
    "HybridRetriever",
    "KeywordRetriever",
    "Reranker",
    "RetrievedChunk",
    "StubEmbedder",
    "VectorRetriever",
    "build_embedder",
    "chunk_to_citation",
]
