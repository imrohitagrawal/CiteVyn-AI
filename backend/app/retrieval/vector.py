"""Vector retrieval (pgvector).

On Postgres, performs a cosine-distance query against the ``embedding``
column added in migration ``0003``. On SQLite (the hermetic test
engine), the column doesn't exist, so the retriever returns ``[]``.

A :class:`StubEmbedder` is shipped for tests and offline development.
It produces deterministic hash-bucketed vectors so the same text always
embeds to the same point. ``AnthropicEmbeddingsClient`` is the
production placeholder, gated by ``CITEVYN_EMBEDDING_PROVIDER=anthropic``.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Chunk, Document, DocumentStatus
from app.retrieval.types import RetrievedChunk


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class StubEmbedder:
    """Deterministic, in-process embedder.

    Same input → same vector. The vector is normalized to unit length
    so cosine distance is well defined. The hash bucket mod the
    dimension produces a stable point per text, which lets us write
    hermetic vector tests without a real embedding model.
    """

    def __init__(self, dim: int) -> None:
        self._dim = dim

    async def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dim
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Use the first 32 bytes (256 bits) and bucket into dim slots.
        ints = [b for b in digest]
        # Stretch the bytes into ``dim`` floats by repeating the digest.
        raw: list[float] = []
        i = 0
        while len(raw) < self._dim:
            raw.append((ints[i % len(ints)] - 128) / 128.0)
            i += 1
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]


class AnthropicEmbeddingsClient:
    """Production embedder placeholder. Throws until an HTTP impl ships."""

    def __init__(self, *, model: str, api_key: str | None, api_base: str) -> None:
        if not api_key:
            raise RuntimeError(
                "CITEVYN_ANTHROPIC_API_KEY is required when CITEVYN_EMBEDDING_PROVIDER=anthropic"
            )
        self._model = model
        self._api_key = api_key
        self._api_base = api_base

    async def embed(self, text: str) -> list[float]:  # pragma: no cover - network
        raise NotImplementedError(
            "AnthropicEmbeddingsClient is a placeholder; wire httpx before enabling."
        )


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "anthropic":
        return AnthropicEmbeddingsClient(
            model=settings.embedding_model,
            api_key=settings.anthropic_api_key,
            api_base=settings.anthropic_api_base,
        )
    return StubEmbedder(dim=settings.embedding_dim)


class VectorRetriever:
    def __init__(
        self,
        session: AsyncSession,
        *,
        active_index_version: str | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._session = session
        self._active_index_version = active_index_version
        self._embedder = embedder

    async def retrieve(
        self,
        question: str,
        *,
        product_area: str | None = None,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        # Vector search is only meaningful when an embedder is wired
        # AND the database supports it. The hermetic test engine is
        # SQLite (no pgvector); the production engine is Postgres. We
        # detect the dialect at runtime and bail out cleanly on
        # SQLite so the rest of the pipeline can still run.
        if self._embedder is None:
            return []
        if not self._session.bind or self._session.bind.dialect.name != "postgresql":
            return []

        embedding = await self._embedder.embed(question)
        # ``Chunk.embedding`` is a pgvector column that lands in
        # Phase 2 (see ``app/models/chunks.py`` docstring); the
        # type checker cannot see the attribute because it has not
        # been declared on the ORM model yet.
        stmt = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.document_id)
            .where(Document.status == DocumentStatus.active)
            .where(Chunk.embedding.is_not(None))  # type: ignore[attr-defined]
            .order_by(Chunk.embedding.cosine_distance(embedding))  # type: ignore[attr-defined]
            .limit(limit)
        )
        if self._active_index_version is not None:
            stmt = stmt.where(Document.index_version == self._active_index_version)
        if product_area is not None:
            stmt = stmt.where(Chunk.product_area == product_area)

        rows = (await self._session.execute(stmt)).all()
        results: list[RetrievedChunk] = []
        for chunk, doc in rows:
            distance = chunk.embedding.cosine_distance(embedding)  # type: ignore[attr-defined]
            score = max(0.0, 1.0 - float(distance))
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    product_area=chunk.product_area,
                    source_name=doc.source_name,
                    document_title=doc.title,
                    section_path=chunk.section_path,
                    heading=chunk.heading,
                    parent_heading=chunk.parent_heading,
                    chunk_text=chunk.chunk_text,
                    context_summary=chunk.context_summary,
                    source_url=doc.source_url,
                    score=score,
                )
            )
        return results
