"""Audit-event write helpers used by both the HTTP routes and the worker.

Centralising this here means:

* the route and the worker write the *same* shape of row
* adding a new field (e.g. ``source_ip``) is a one-file change
* tests can exercise the audit shape without booting FastAPI

The functions take an open SQLAlchemy ``AsyncSession`` rather than
creating one — the caller owns the transaction so a failed audit
write can be rolled back with the same unit of work as the action
it was recording.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_events import AuditEvent
from app.models.enums import AuditAction, UserRole


def _utcnow() -> datetime:
    """Naive-free UTC timestamp.

    Every audit row uses tz-aware UTC so PostgreSQL TIMESTAMPTZ
    and SQLite text columns store the same instant — sorting
    rows from a multi-region cluster is then trivial.
    """
    return datetime.now(UTC)


async def record_audit_event(
    session: AsyncSession,
    *,
    action: AuditAction,
    user_id: str | None,
    role: UserRole | None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append one audit-event row and flush the session.

    The caller owns the transaction (commit / rollback). The flush
    is what surfaces the row to subsequent ``SELECT`` queries within
    the same transaction without committing.
    """
    event = AuditEvent(
        user_id=user_id,
        role=role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        timestamp=_utcnow(),
        metadata_=metadata or {},
    )
    # ``metadata`` is a reserved attribute name on the SQLAlchemy
    # ``Base`` (it conflicts with ``Base.metadata``); the model
    # column is exposed as ``metadata_`` so the constructor kwarg
    # here is named to match.
    session.add(event)
    await session.flush()


async def record_ask_question(
    session: AsyncSession,
    *,
    user_id: str,
    role: UserRole,
    request_id: str,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    domain: str,
    intent: str,
    outcome: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record an ``ask_question`` audit event with the standard envelope.

    The orchestrator's :func:`_persist_audit` was duplicating this
    metadata dict; routing both call sites through this helper keeps
    the JSON shape stable for the SRE dashboard.
    """
    metadata: dict[str, Any] = {
        "request_id": request_id,
        "session_id": str(session_id),
        "message_id": str(message_id),
        "domain": domain,
        "intent": intent,
        "outcome": outcome,
    }
    if extra:
        metadata.update(extra)
    await record_audit_event(
        session,
        action=AuditAction.ask_question,
        user_id=user_id,
        role=role,
        resource_type="message",
        resource_id=str(message_id),
        metadata=metadata,
    )


async def record_admin_action(
    session: AsyncSession,
    *,
    admin_user_id: str,
    action: AuditAction,
    resource_type: str | None = None,
    resource_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record an admin-only action (``trigger_ingestion`` / ``run_evaluation`` / ``promote_index``).

    A single helper keeps the ``role="admin"`` and ``user_id``
    fields consistent so the SRE can grep for admin-only events
    without inferring it from the ``action`` enum value.
    """
    metadata: dict[str, Any] = dict(extra or {})
    metadata.setdefault("actor", admin_user_id)
    await record_audit_event(
        session,
        action=action,
        user_id=admin_user_id,
        role=UserRole.admin,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
    )


__all__ = [
    "record_admin_action",
    "record_ask_question",
    "record_audit_event",
]
