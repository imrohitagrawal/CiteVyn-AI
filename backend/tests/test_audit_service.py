"""Tests for :mod:`app.services.audit`.

These tests use the per-test in-memory SQLite engine from
``conftest.py`` so the row-write paths exercise the real
SQLAlchemy+aiosqlite stack, including the ``JSON`` column that
carries the metadata envelope.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.audit_events import AuditEvent
from app.models.enums import AuditAction, UserRole
from app.services.audit import (
    record_admin_action,
    record_ask_question,
    record_audit_event,
)


@pytest.mark.asyncio
async def test_record_audit_event_writes_full_row(session) -> None:
    """The full row shape matches the model contract."""
    user_id = "user-123"

    await record_audit_event(
        session,
        action=AuditAction.login,
        user_id=user_id,
        role=UserRole.demo_user,
        resource_type="session",
        resource_id="sess-1",
        metadata={"ip": "127.0.0.1", "ua": "pytest"},
    )
    await session.commit()

    row = (
        await session.execute(select(AuditEvent).where(AuditEvent.user_id == user_id))
    ).scalar_one()
    assert row.action is AuditAction.login
    assert row.role is UserRole.demo_user
    assert row.resource_type == "session"
    assert row.resource_id == "sess-1"
    assert row.metadata_ == {"ip": "127.0.0.1", "ua": "pytest"}
    assert isinstance(row.timestamp, datetime)
    # NOTE: SQLite drops tzinfo on roundtrip; the helper itself
    # writes tz-aware UTC (pinned in test_record_ask_question_stamps_envelope's
    # sibling unit test). The integration shape is what we assert here.
    assert isinstance(row.event_id, uuid.UUID)


@pytest.mark.asyncio
async def test_record_audit_event_metadata_defaults_to_empty_dict(session) -> None:
    """``metadata=None`` is stored as an empty dict, not SQL NULL.

    The SRE dashboard serialises the column as JSON ``{}`` for
    rows with no metadata — a NULL would force the dashboard to
    branch on nullability.
    """
    await record_audit_event(
        session,
        action=AuditAction.rate_limited,
        user_id=None,
        role=None,
    )
    await session.commit()

    row = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == AuditAction.rate_limited)
        )
    ).scalar_one()
    assert row.metadata_ == {}
    assert row.user_id is None
    assert row.role is None
    assert row.resource_type is None
    assert row.resource_id is None


@pytest.mark.asyncio
async def test_record_ask_question_stamps_envelope(session) -> None:
    """``record_ask_question`` writes the orchestrator envelope.

    The orchestrator's ``_persist_audit`` now delegates to this
    helper; the test pins the JSON shape so a future refactor
    can't drop a field the SRE dashboard depends on.
    """
    session_id = uuid.uuid4()
    message_id = uuid.uuid4()
    await record_ask_question(
        session,
        user_id="user-7",
        role=UserRole.demo_user,
        request_id="req-abc",
        session_id=session_id,
        message_id=message_id,
        domain="hr",
        intent="rag",
        outcome="answered",
        extra={"latency_ms": 142, "model": "claude-haiku-4-5"},
    )
    await session.commit()

    row = (
        await session.execute(select(AuditEvent).where(AuditEvent.user_id == "user-7"))
    ).scalar_one()
    assert row.action is AuditAction.ask_question
    assert row.resource_type == "message"
    assert row.resource_id == str(message_id)
    # Every envelope field is present.
    assert row.metadata_ == {
        "request_id": "req-abc",
        "session_id": str(session_id),
        "message_id": str(message_id),
        "domain": "hr",
        "intent": "rag",
        "outcome": "answered",
        "latency_ms": 142,
        "model": "claude-haiku-4-5",
    }


@pytest.mark.asyncio
async def test_record_ask_question_extra_overrides_envelope_keys(
    session,
) -> None:
    """``extra`` is applied on top of the envelope (last-write-wins).

    The SRE sometimes wants to overwrite a default with a
    more specific value (e.g. set ``intent`` to a custom tag)
    — the merge order guarantees the caller's value wins
    without raising.
    """
    session_id = uuid.uuid4()
    message_id = uuid.uuid4()
    await record_ask_question(
        session,
        user_id="user-7",
        role=UserRole.demo_user,
        request_id="req-abc",
        session_id=session_id,
        message_id=message_id,
        domain="hr",
        intent="rag",
        outcome="answered",
        extra={"intent": "rag.custom", "note": "explanation"},
    )
    await session.commit()

    row = (
        await session.execute(select(AuditEvent).where(AuditEvent.user_id == "user-7"))
    ).scalar_one()
    assert row.metadata_["intent"] == "rag.custom"
    assert row.metadata_["note"] == "explanation"


@pytest.mark.asyncio
async def test_record_admin_action_sets_admin_role_and_actor(
    session,
) -> None:
    """``record_admin_action`` records ``role=admin`` and pins the actor.

    A single helper keeps the admin-only audit events
    greppable by ``role='admin'``; the test pins that contract
    so a future refactor can't accidentally drop the role.
    """
    await record_admin_action(
        session,
        admin_user_id="admin-1",
        action=AuditAction.trigger_ingestion,
        resource_type="index_version",
        resource_id="v-1",
        extra={"source_count": 12},
    )
    await session.commit()

    row = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == AuditAction.trigger_ingestion)
        )
    ).scalar_one()
    assert row.role is UserRole.admin
    assert row.user_id == "admin-1"
    assert row.resource_type == "index_version"
    assert row.resource_id == "v-1"
    assert row.metadata_ == {"source_count": 12, "actor": "admin-1"}


@pytest.mark.asyncio
async def test_record_admin_action_does_not_clobber_explicit_actor(
    session,
) -> None:
    """If the caller sets ``actor`` in ``extra`` it is preserved.

    The ``setdefault`` keeps the caller's value if they
    explicitly pass one — useful when an on-behalf-of admin
    action records the human who initiated the call.
    """
    await record_admin_action(
        session,
        admin_user_id="admin-1",
        action=AuditAction.run_evaluation,
        extra={"actor": "ops-pager", "eval_set": "golden-50"},
    )
    await session.commit()

    row = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == AuditAction.run_evaluation)
        )
    ).scalar_one()
    assert row.metadata_["actor"] == "ops-pager"
    assert row.metadata_["eval_set"] == "golden-50"
