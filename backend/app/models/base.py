"""SQLAlchemy declarative base and shared mixins.

We use SQLAlchemy 2.x style with a single ``Base`` so Alembic sees all
models in one ``Base.metadata``. UUID columns vary by dialect: ``Uuid``
on Postgres (real 128-bit type) and ``CHAR(36)`` on SQLite (string), so
tests can run hermetically without needing a Postgres server.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CHAR, DateTime, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GUID(TypeDecorator):  # type: ignore[type-arg]
    """Platform-independent UUID column.

    Uses the native ``UUID`` type on Postgres and stores as ``CHAR(36)``
    on SQLite. Always accepts and emits :class:`uuid.UUID` instances.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID

            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any | None:
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class StrEnumType(TypeDecorator):  # type: ignore[type-arg]
    """Platform-independent column for :class:`enum.StrEnum` values.

    Migration ``0002_promote_strenum_to_native`` converts every
    ``String(32|64)`` column backed by a ``StrEnum`` to a native
    PostgreSQL ``ENUM`` type. The ORM model still declares the column
    as ``String(32)`` so the hermetic SQLite test suite keeps working,
    which means SQLAlchemy sends a textual parameter to Postgres.
    Postgres does not auto-cast ``VARCHAR`` to a native enum, so we
    intercept the bind: on Postgres we route the value through the
    ``citevyn_<name>`` enum type via a literal cast; on SQLite we
    pass the string value through unchanged.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[enum.StrEnum], length: int = 32) -> None:
        super().__init__(length=length)
        self._enum_cls = enum_cls
        self._length = length
        # The Postgres type name is derived from the migration. Every
        # StrEnum in app.models.enums follows the pattern
        # ``citevyn_<lowercased class name>``.
        self._pg_type_name = f"citevyn_{enum_cls.__name__.lower()}"

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import ENUM

            values = tuple(m.value for m in self._enum_cls)
            return dialect.type_descriptor(
                ENUM(*values, name=self._pg_type_name, create_type=False)
            )
        return dialect.type_descriptor(String(self._length))

    def process_bind_param(self, value: Any, dialect: Any) -> Any | None:
        if value is None:
            return None
        # Always normalise to the underlying string value.
        if isinstance(value, enum.Enum):
            return value.value
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> enum.StrEnum | None:
        if value is None:
            return None
        if isinstance(value, self._enum_cls):
            return value
        return self._enum_cls(str(value))


class Base(DeclarativeBase):
    """Project-wide declarative base.

    Subclasses must set ``__tablename__`` explicitly. We avoid the
    snake-case / pluralization helper because the inferred return
    type is not a string literal — SQLAlchemy's ``__tablename__`` is
    declared as a string and pyright's strict mode rejects the
    auto-derivation.
    """


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def uuid_column(*, primary_key: bool = False, **kwargs: Any) -> Mapped[uuid.UUID]:
    """Build a UUID column with sensible defaults."""
    return mapped_column(
        GUID(),
        default=new_uuid,
        primary_key=primary_key,
        nullable=kwargs.pop("nullable", primary_key),
        **kwargs,
    )


def string_pk(**kwargs: Any) -> Mapped[str]:
    """String primary key (used for ``users.user_id`` and ``index_versions``)."""
    return mapped_column(String(128), primary_key=True, **kwargs)
