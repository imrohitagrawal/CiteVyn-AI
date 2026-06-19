"""Exact terms table.

Used for first-class exact lookup of flags, commands, config keys,
model names, errors, environment variables, and so on. The natural
unique key is ``(term_text, product_area, chunk_id)`` because the same
term may appear in multiple chunks or product areas.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, StrEnumType
from app.models.enums import TermType

if TYPE_CHECKING:
    from app.models.chunks import Chunk
    from app.models.documents import Document


class ExactTerm(Base):
    __tablename__ = "exact_terms"
    __table_args__ = (
        UniqueConstraint(
            "term_text",
            "product_area",
            "chunk_id",
            name="uq_exact_terms_term_product_chunk",
        ),
    )

    term_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    term_text: Mapped[str] = mapped_column(Text, nullable=False)
    term_type: Mapped[TermType] = mapped_column(StrEnumType(TermType), nullable=False)
    product_area: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("chunks.chunk_id", ondelete="CASCADE"),
        nullable=False,
    )

    document: Mapped[Document] = relationship(
        back_populates="exact_terms",
        lazy="raise",
    )
    chunk: Mapped[Chunk] = relationship(lazy="raise")
