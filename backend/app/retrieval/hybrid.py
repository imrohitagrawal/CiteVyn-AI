"""Hybrid retriever.

Orchestrates the three orthogonal retrievers and produces the final
ordered hit list. The reranker is then called on that list.

Scoring contract:

* exact hits start at ``1.0``.
* keyword hits start at ``0.5``.
* vector hits start at ``1 - distance`` (already done by
  :class:`VectorRetriever`).

When two retrievers find the same chunk we add the per-retriever
scores. The result is sorted descending and capped at ``limit``. The
exact lookup path short-circuits the keyword and vector retrievers
when intent is ``exact_lookup``.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RetrievalType
from app.retrieval.exact import ExactRetriever
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.rerank import Reranker
from app.retrieval.types import EvidenceHit, RetrievedChunk
from app.retrieval.vector import Embedder, VectorRetriever
from app.routing.intent import Intent


class HybridRetriever:
    def __init__(
        self,
        session: AsyncSession,
        *,
        active_index_version: str | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._session = session
        self._active_index_version = active_index_version
        self._embedder = embedder
        self._reranker = reranker or Reranker()

    async def retrieve(
        self,
        question: str,
        *,
        product_area: str,
        intent: Intent,
        limit: int = 20,
        top_k: int = 6,
    ) -> list[EvidenceHit]:
        exact = ExactRetriever(self._session, active_index_version=self._active_index_version)
        keyword = KeywordRetriever(self._session, active_index_version=self._active_index_version)
        vector = VectorRetriever(
            self._session,
            active_index_version=self._active_index_version,
            embedder=self._embedder,
        )

        if intent is Intent.exact_lookup:
            exact_hits = await exact.retrieve(question, product_area=product_area, limit=top_k)
            evidence = [
                _to_evidence(h, RetrievalType.exact, idx + 1) for idx, h in enumerate(exact_hits)
            ]
            return evidence[:top_k]

        exact_hits, keyword_hits, vector_hits = await asyncio.gather(
            exact.retrieve(question, product_area=product_area, limit=limit),
            keyword.retrieve(question, product_area=product_area, limit=limit),
            vector.retrieve(question, product_area=product_area, limit=limit),
        )

        merged = _merge(question, exact_hits, keyword_hits, vector_hits)
        merged.sort(key=lambda h: h.score, reverse=True)
        merged = merged[:limit]

        reranked = await self._reranker.rerank(question, merged, top_k=top_k)
        for idx, hit in enumerate(reranked, start=1):
            hit.rank = idx
        return reranked


def _merge(
    question: str,
    exact: list[RetrievedChunk],
    keyword: list[RetrievedChunk],
    vector: list[RetrievedChunk],
) -> list[EvidenceHit]:
    by_chunk: dict[uuid.UUID, EvidenceHit] = {}
    for chunk in exact:
        by_chunk[chunk.chunk_id] = _to_evidence(chunk, RetrievalType.exact, 0, base_score=1.0)
    for chunk in keyword:
        if chunk.chunk_id in by_chunk:
            by_chunk[chunk.chunk_id].score += 0.5
            continue
        by_chunk[chunk.chunk_id] = _to_evidence(chunk, RetrievalType.keyword, 0, base_score=0.5)
    for chunk in vector:
        if chunk.chunk_id in by_chunk:
            by_chunk[chunk.chunk_id].score += chunk.score
            continue
        by_chunk[chunk.chunk_id] = _to_evidence(
            chunk, RetrievalType.vector, 0, base_score=chunk.score
        )
    return list(by_chunk.values())


def _to_evidence(
    chunk: RetrievedChunk,
    retrieval_type: RetrievalType,
    rank: int,
    *,
    base_score: float | None = None,
) -> EvidenceHit:
    return EvidenceHit(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        product_area=chunk.product_area,
        source_name=chunk.source_name,
        document_title=chunk.document_title,
        section_path=chunk.section_path,
        heading=chunk.heading,
        parent_heading=chunk.parent_heading,
        chunk_text=chunk.chunk_text,
        context_summary=chunk.context_summary,
        source_url=chunk.source_url,
        score=base_score if base_score is not None else chunk.score,
        retrieval_type=retrieval_type,
        rank=rank,
    )
