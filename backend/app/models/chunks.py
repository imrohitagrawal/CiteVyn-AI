"""Chunk table.

A chunk is a contextual retrievable unit carved out of a document.
The ``embedding`` column stores a ``list[float]`` of fixed dimension
(:attr:`app.core.config.Settings.embedding_dim`). It is implemented
as a portable pickled-blob type (BLOB on SQLite, ``bytea`` on Postgres)
so the hermetic test suite can run without a real vector database.
A follow-up migration (``0004``) will swap the Postgres column to
``pgvector``'s ``vector(<dim>)`` and add an ``ivfflat``/``hnsw``
index; the SQLite path keeps using the pickle-backed column.

The JSON ``exact_terms`` column keeps a small snapshot of any
high-value terms mentioned in the chunk, which complements the
dedicated ``exact_terms`` table used for canonical lookup.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, PickledEmbedding

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
    # ``embedding`` is nullable: chunks inserted before migration
    # ``0003`` (or by tests that don't care about vectors) have no
    # embedding. The retriever short-circuits on ``is None`` so the
    # pipeline stays functional. ``nullable=True`` already implies
    # the default is ``None`` — no need to spell it out.
    embedding: Mapped[list[float] | None] = mapped_column(PickledEmbedding(), nullable=True)

    document: Mapped[Document] = relationship(
        back_populates="chunks",
        lazy="raise",
    )
