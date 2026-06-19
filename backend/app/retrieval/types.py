"""Shared types for the retrieval layer.

``RetrievedChunk`` is the value object that flows from any retriever
into the answer engine. ``EvidenceHit`` adds the metadata (rank,
retrieval type) the engine needs to persist the trace.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel

from app.models.enums import RetrievalType


class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    product_area: str
    source_name: str
    document_title: str
    section_path: str
    heading: str
    parent_heading: str | None = None
    chunk_text: str
    context_summary: str
    source_url: str
    score: float = 0.0


class EvidenceHit(RetrievedChunk):
    retrieval_type: RetrievalType = RetrievalType.hybrid
    rank: int = 0


def chunk_to_citation(chunk: RetrievedChunk) -> dict[str, Any]:
    """Project a chunk into the response ``Citation`` shape."""
    return {
        "source_name": chunk.source_name,
        "title": chunk.document_title,
        "url": chunk.source_url,
        "chunk_id": str(chunk.chunk_id),
    }
