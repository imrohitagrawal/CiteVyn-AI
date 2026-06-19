"""User table for Slice 2.

The MVP supports two roles returned by ``app.core.security``:
``demo_user`` and ``admin``. We persist those identifiers here so that
``sessions`` and ``audit_events`` can reference them via foreign key
with cascade behavior, instead of holding an unconstrained string.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StrEnumType
from app.models.enums import UserRole

if TYPE_CHECKING:
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    role: Mapped[UserRole] = mapped_column(
        StrEnumType(UserRole),
        default=UserRole.demo_user,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
