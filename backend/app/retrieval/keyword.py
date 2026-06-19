"""Keyword retrieval.

Placeholder for Postgres full-text search (Phase 2 ingestion) using
SQL ``LIKE`` on ``chunks.chunk_text``. Good enough for the Slice 3/4
hermetic test suite and the fixture catalog; will be replaced by a
GIN-indexed ``tsvector`` query in the next iteration.

Returns at most ``limit`` chunks ordered by ``chunk_order``. Score is a
flat ``0.5`` — the retriever's job is recall, not precision; the
hybrid combiner and reranker do the scoring work.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document, DocumentStatus
from app.retrieval.types import RetrievedChunk

_STOPWORDS: frozenset[str] = frozenset(
    {"the", "a", "an", "is", "are", "do", "does", "how", "what", "which"}
)


class KeywordRetriever:
    def __init__(
        self,
        session: AsyncSession,
        *,
        active_index_version: str | None = None,
    ) -> None:
        self._session = session
        self._active_index_version = active_index_version

    async def retrieve(
        self,
        question: str,
        *,
        product_area: str | None = None,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        tokens = [
            tok
            for tok in question.lower().split()
            if tok and tok not in _STOPWORDS and any(c.isalnum() for c in tok)
        ]
        if not tokens:
            return []

        like_clauses = [Chunk.chunk_text.ilike(f"%{tok}%") for tok in tokens]
        stmt = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.document_id)
            .where(Document.status == DocumentStatus.active)
            .where(or_(*like_clauses))
        )
        if self._active_index_version is not None:
            stmt = stmt.where(Document.index_version == self._active_index_version)
        if product_area is not None:
            stmt = stmt.where(Chunk.product_area == product_area)
        stmt = stmt.order_by(Chunk.chunk_order.asc()).limit(limit)

        rows = (await self._session.execute(stmt)).all()
        return [
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
                score=0.5,
            )
            for chunk, doc in rows
        ]
