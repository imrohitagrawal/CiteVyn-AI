"""Evaluation tables.

Two tables live here:

* ``evaluation_cases`` — golden test cases. Sourced from
  ``docs/TEST_STRATEGY.md § 5``.
* ``evaluation_runs`` — execution results for a run of a suite against a
  candidate ``index_version``. Phase 4 adds the runner that writes to
  this table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, Base, StrEnumType
from app.models.enums import EvaluationBehavior, EvaluationStatus

if TYPE_CHECKING:
    from app.models.index_versions import IndexVersion


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    case_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_sources: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    required_answer_points: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    forbidden_answer_points: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    expected_behavior: Mapped[EvaluationBehavior | None] = mapped_column(
        StrEnumType(EvaluationBehavior), nullable=True
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    suite_name: Mapped[str] = mapped_column(String(64), nullable=False)
    index_version: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("index_versions.index_version", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[EvaluationStatus] = mapped_column(StrEnumType(EvaluationStatus), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    failure_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    index_versions: Mapped[list[IndexVersion]] = relationship(
        "IndexVersion",
        primaryjoin="EvaluationRun.run_id == IndexVersion.evaluation_run_id",
        foreign_keys="IndexVersion.evaluation_run_id",
        back_populates="evaluation_run",
        lazy="raise",
    )
