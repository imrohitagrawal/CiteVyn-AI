"""Answer cache table.

Stores safe cached answers keyed by ``cache_key``, which composes the
normalized question, product area, source version hash, and answer
policy version. Citations are stored inline as JSON for simplicity in
Slice 2; they may be normalized into a separate table later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StrEnumType
from app.models.enums import Confidence


class AnswerCache(Base):
    __tablename__ = "answer_cache"

    cache_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    product_area: Mapped[str] = mapped_column(String(64), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    source_version_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    answer_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Confidence] = mapped_column(StrEnumType(Confidence), nullable=False)
    ttl_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
