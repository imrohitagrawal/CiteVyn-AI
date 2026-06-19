"""Identity reranker.

The rerank step is the seam where a cross-encoder (or hosted rerank
service) will plug in. For Slice 3/4 it returns the first ``top_k``
hits unchanged; the orchestrator still calls :func:`Reranker.rerank` so
the wiring is in place.
"""

from __future__ import annotations

from app.retrieval.types import EvidenceHit


class Reranker:
    async def rerank(
        self,
        question: str,
        hits: list[EvidenceHit],
        *,
        top_k: int,
    ) -> list[EvidenceHit]:
        return list(hits[: max(0, top_k)])
