"""Retrieved evidence table.

Records each chunk considered while answering a message, with its
post-rerank score and whether it was actually used in the answer
(cited). This is the primary trace used by the citation validator and
the observability layer.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, StrEnumType
from app.models.enums import RetrievalType

if TYPE_CHECKING:
    from app.models.chunks import Chunk
    from app.models.messages import Message


class RetrievedEvidence(Base):
    __tablename__ = "retrieved_evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("messages.message_id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("chunks.chunk_id", ondelete="CASCADE"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_type: Mapped[RetrievalType] = mapped_column(
        StrEnumType(RetrievalType), nullable=False
    )
    used_in_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    message: Mapped[Message] = relationship(
        back_populates="evidence",
        lazy="raise",
    )
    chunk: Mapped[Chunk] = relationship(lazy="raise")
