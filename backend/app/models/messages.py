"""Message table.

Stores user and assistant messages along with classification metadata
(``domain``, ``intent``) so the system can replay the trace for a
session and reconstruct context for follow-up questions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, StrEnumType
from app.models.enums import MessageRole

if TYPE_CHECKING:
    from app.models.retrieved_evidence import RetrievedEvidence
    from app.models.sessions import Session


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(StrEnumType(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped[Session] = relationship(
        back_populates="messages",
        lazy="raise",
    )
    evidence: Mapped[list[RetrievedEvidence]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="raise",
    )
