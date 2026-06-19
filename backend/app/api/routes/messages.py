"""Message HTTP routes (Slice 7).

Implements the two endpoints defined in ``docs/API_SPEC.md`` §5:

* ``POST /v1/sessions/{session_id}/messages`` — the answer endpoint.
  Calls :class:`app.answer.orchestrator.Orchestrator.ask` and maps the
  returned dict to the response shape. Returns 200 for every
  orchestrator outcome (grounded, cache, no-answer, unsupported) so
  the body carries the truth; transport errors propagate to the
  Slice 7 exception handler.
* ``GET /v1/sessions/{session_id}/messages/{message_id}`` — fetch a
  single message for citation hydration on the client.

Both endpoints require a valid bearer token via
:func:`app.core.security.require_demo_api_key`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.answer.orchestrator import Orchestrator
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import APIErrorCode, error_response
from app.core.security import require_demo_api_key
from app.models import Message, Session

router = APIRouter(prefix="/v1/sessions", tags=["messages"])


def _request_id(request: Request) -> str:
    """Return the request id stamped on :class:`Request` by the middleware."""
    return str(request.state.request_id)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AnswerRequest(BaseModel):
    """Body for ``POST /v1/sessions/{session_id}/messages``.

    ``answer_style`` is restricted to the two values the MVP supports.
    Anything else is rejected with a 400 so a typo doesn't silently
    degrade quality.
    """

    message: str = Field(min_length=1, max_length=4000)
    answer_style: str = Field(default="short")


_ALLOWED_ANSWER_STYLES: frozenset[str] = frozenset({"short", "step_by_step"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_session(db: AsyncSession, *, request_id: str, session_id: uuid.UUID) -> Session:
    """Load a session row or raise the standard 404 envelope."""
    row = await db.get(Session, session_id)
    if row is None:
        raise error_response(
            request_id=request_id,
            code=APIErrorCode.not_found,
            message=f"Session {session_id} not found.",
        )
    return row


async def _require_message(
    db: AsyncSession,
    *,
    request_id: str,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
) -> Message:
    """Load a message scoped to ``session_id`` or raise 404."""
    stmt = select(Message).where(
        Message.message_id == message_id,
        Message.session_id == session_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise error_response(
            request_id=request_id,
            code=APIErrorCode.not_found,
            message=f"Message {message_id} not found in session {session_id}.",
        )
    return row


def _message_payload(message: Message) -> dict[str, Any]:
    """Project a :class:`Message` row into the public response shape."""
    # ``Message.role`` is stored as a ``String(32)``; SQLAlchemy
    # returns the raw string on read so we coerce defensively.
    role = message.role
    role_value = role.value if hasattr(role, "value") else str(role)
    return {
        "message_id": str(message.message_id),
        "session_id": str(message.session_id),
        "role": role_value,
        "content": message.content,
        "normalized_query": message.normalized_query,
        "domain": message.domain,
        "intent": message.intent,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# POST /v1/sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/messages",
    status_code=status.HTTP_200_OK,
    summary="Ask a question and receive a grounded answer.",
    description=(
        "Per ``docs/API_SPEC.md`` §5. Delegates to "
        ":class:`app.answer.orchestrator.Orchestrator.ask`. The body "
        "shape is the orchestrator's response unchanged — the route "
        "does not invent or rename fields. Transport failures (LLM "
        "down, cost limit) are mapped by the Slice 7 exception "
        "handler to 5xx with the standard error envelope."
    ),
    response_description="A grounded, cached, no-answer, or unsupported response.",
)
async def post_message(
    request: Request,
    session_id: Annotated[uuid.UUID, Path()],
    body: Annotated[AnswerRequest, Body()],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_session)],
    _user_id: Annotated[str, Depends(require_demo_api_key)],
) -> dict[str, Any]:
    """Ask a question and return the orchestrator's response shape."""
    request_id = _request_id(request)
    if body.answer_style not in _ALLOWED_ANSWER_STYLES:
        raise error_response(
            request_id=request_id,
            code=APIErrorCode.validation_error,
            message=(
                f"Unsupported answer_style '{body.answer_style}'. Allowed: short, step_by_step."
            ),
        )

    await _require_session(db, request_id=request_id, session_id=session_id)
    orchestrator = Orchestrator(settings, db)
    response = await orchestrator.ask(
        question=body.message,
        request_id=request_id,
        session_id=session_id,
    )
    # ``Orchestrator.ask`` mutates ``db`` (adds + flushes) but does not
    # commit; commit here so the message + audit rows survive the
    # request boundary.
    await db.commit()
    return response


# ---------------------------------------------------------------------------
# GET /v1/sessions/{session_id}/messages/{message_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/messages/{message_id}",
    summary="Fetch a single message for citation hydration.",
    description=(
        "Returns the message and the per-chunk retrieval trace "
        "(``retrieved_evidence``) so the client can hydrate "
        "citations without re-asking the question."
    ),
    response_description="Message payload plus retrieved-evidence trace.",
)
async def get_message(
    request: Request,
    session_id: Annotated[uuid.UUID, Path()],
    message_id: Annotated[uuid.UUID, Path()],
    db: Annotated[AsyncSession, Depends(get_session)],
    _user_id: Annotated[str, Depends(require_demo_api_key)],
) -> dict[str, Any]:
    """Return a message and its retrieval trace."""
    request_id = _request_id(request)
    await _require_session(db, request_id=request_id, session_id=session_id)
    message = await _require_message(
        db,
        request_id=request_id,
        session_id=session_id,
        message_id=message_id,
    )

    # Fetch the evidence rows for the message. The relationship is
    # ``raise``-lazy so we query explicitly to avoid an implicit
    # SELECT in the ORM.
    from app.models import RetrievedEvidence

    evidence_stmt = (
        select(RetrievedEvidence)
        .where(RetrievedEvidence.message_id == message_id)
        .order_by(RetrievedEvidence.rank.asc())
    )
    evidence_rows = list((await db.execute(evidence_stmt)).scalars().all())
    evidence_payload = [
        {
            "chunk_id": str(row.chunk_id),
            "rank": row.rank,
            "score": row.score,
            "retrieval_type": row.retrieval_type.value,
            "used_in_answer": row.used_in_answer,
        }
        for row in evidence_rows
    ]

    return {
        "request_id": request_id,
        **_message_payload(message),
        "evidence": evidence_payload,
    }


__all__ = ["router"]


# Touch _utcnow so static analyzers see it as used; the helper is kept
# for symmetry with the other route modules that need a tz-aware now.
_ = _utcnow
