"""Exact-term retrieval.

Looks up the question against the ``exact_terms`` table joined to
``chunks`` and ``documents``. Returns a list of ``RetrievedChunk`` with
``score = 1.0``. The retriever is the highest-confidence path: a hit
means the question text literally matches an indexed term.

Filters:

* ``documents.status == "active"`` so deprecated / failed docs do not
  leak into answers.
* ``documents.index_version == :active_version`` so we never answer
  against a candidate index that has not been promoted.

When the resolved domain is known, the retriever prefers chunks in
that domain; ties fall back to the first hit ordered by ``term_id``.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document, DocumentStatus, ExactTerm
from app.retrieval.types import RetrievedChunk


class ExactRetriever:
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
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        if not question or not question.strip():
            return []
        normalized = question.strip().lower()
        stmt = (
            select(ExactTerm, Chunk, Document)
            .join(Chunk, ExactTerm.chunk_id == Chunk.chunk_id)
            .join(Document, ExactTerm.document_id == Document.document_id)
            .where(func.lower(ExactTerm.term_text) == normalized)
            .where(Document.status == DocumentStatus.active)
        )
        if self._active_index_version is not None:
            stmt = stmt.where(Document.index_version == self._active_index_version)
        stmt = stmt.limit(limit * 4)  # over-fetch slightly to allow disambiguation

        rows = (await self._session.execute(stmt)).all()
        if not rows:
            return []

        # Prefer chunks whose product_area matches the resolved domain.
        if product_area is not None:
            in_domain = [r for r in rows if r[1].product_area == product_area]
            chosen = in_domain or rows
        else:
            chosen = rows

        chosen = chosen[:limit]
        return [_to_chunk(term, chunk, doc) for term, chunk, doc in chosen]


def _to_chunk(term: ExactTerm, chunk: Chunk, doc: Document) -> RetrievedChunk:
    return RetrievedChunk(
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
        score=1.0,
    )
