"""Chunk table.

A chunk is a contextual retrievable unit carved out of a document. The
embedding column is intentionally absent in Slice 2 — pgvector lands in
Phase 2 alongside the chunker and embedding generator. The JSON
``exact_terms`` column keeps a small snapshot of any high-value terms
mentioned in the chunk, which complements the dedicated
``exact_terms`` table used for canonical lookup.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base

if TYPE_CHECKING:
    from app.models.documents import Document


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_area: Mapped[str] = mapped_column(String(64), nullable=False)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    parent_heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_summary: Mapped[str] = mapped_column(Text, nullable=False)
    exact_terms: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(128), nullable=False)

    document: Mapped[Document] = relationship(
        back_populates="chunks",
        lazy="raise",
    )
