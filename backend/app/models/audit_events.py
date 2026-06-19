"""Audit event table.

Captures security-relevant and operational events. The role is recorded
explicitly so the row is meaningful even if the referenced user is
later removed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, Base, StrEnumType
from app.models.enums import AuditAction, UserRole


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[UserRole | None] = mapped_column(StrEnumType(UserRole), nullable=True)
    action: Mapped[AuditAction] = mapped_column(StrEnumType(AuditAction, length=64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
