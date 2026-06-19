"""Document table.

Represents an official documentation page or file that has been fetched
and indexed. Each document belongs to an ``index_version`` so we can
distinguish the active index from candidates.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, StrEnumType
from app.models.enums import DocumentStatus

if TYPE_CHECKING:
    from app.models.chunks import Chunk
    from app.models.exact_terms import ExactTerm
    from app.models.index_versions import IndexVersion


class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    index_version: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("index_versions.index_version", ondelete="RESTRICT"),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    product_area: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(StrEnumType(DocumentStatus), nullable=False)

    index_version_ref: Mapped[IndexVersion] = relationship(
        back_populates="documents",
        lazy="raise",
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    exact_terms: Mapped[list[ExactTerm]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="raise",
    )
