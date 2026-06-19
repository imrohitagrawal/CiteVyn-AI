"""Index version table.

Tracks candidate and active indexes for rollback. The primary key is a
human-friendly string (``index_v1``) rather than a UUID because
operations need to reference it directly (e.g. promote a candidate).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, StrEnumType
from app.models.enums import IndexStatus

if TYPE_CHECKING:
    from app.models.documents import Document
    from app.models.evaluation import EvaluationRun


class IndexVersion(Base):
    __tablename__ = "index_versions"

    index_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[IndexStatus] = mapped_column(StrEnumType(IndexStatus), nullable=False)
    source_version_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evaluation_runs.run_id", ondelete="SET NULL"),
        nullable=True,
    )

    documents: Mapped[list[Document]] = relationship(
        back_populates="index_version_ref",
        lazy="raise",
    )
    evaluation_run: Mapped[EvaluationRun | None] = relationship(
        "EvaluationRun",
        primaryjoin="IndexVersion.evaluation_run_id == EvaluationRun.run_id",
        foreign_keys="[IndexVersion.evaluation_run_id]",
        back_populates="index_versions",
        lazy="raise",
    )
