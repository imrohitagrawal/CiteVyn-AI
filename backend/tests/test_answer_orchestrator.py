"""Orchestrator tests.

Covers the six required paths (per Slice 6 spec):

* Grounded answer — guardrail pass → retrieval → generation →
  citation validation → cache write.
* Cache hit — warm cache → no retrieval / no LLM call.
* No-answer — empty evidence → no_answer response, nothing cached.
* Unsupported — guardrail rejects → unsupported response, nothing
  cached.
* Citation validation failure — bad ``[n]`` marker → no_answer
  response with the citation_validation_failed reason in the audit
  event, nothing cached.
* Session / message / retrieved_evidence / audit rows are persisted
  with the right shapes.

The orchestrator is wired with the in-memory SQLite engine and a
deterministic ``StubLLMClient`` so the suite is hermetic. We inject a
fake retriever that returns a pre-built :class:`EvidenceHit` list so
the tests do not depend on the hybrid retriever's keyword matching.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.answer.orchestrator import (
    Orchestrator,
    OrchestratorError,
    RetrievalStrategy,
)
from app.core.config import Settings
from app.llm.errors import LLMUnavailable
from app.llm.stub import StubLLMClient
from app.models import (
    AnswerCache,
    AuditAction,
    AuditEvent,
    Confidence,
    Message,
    MessageRole,
    RetrievalType,
    RetrievedEvidence,
)
from app.models.enums import (
    RetrievalType as ModelRetrievalType,
)
from app.retrieval.types import EvidenceHit
from app.routing.intent import Intent

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    """Hermetic settings: stub LLM, cache enabled, deterministic TTLs."""
    base: dict[str, Any] = dict(
        llm_provider="stub",
        llm_model="claude-opus-4-8",
        cache_enabled=True,
        cache_ttl_seconds=3600,
        unsupported_refusal=(
            "I can answer questions about Claude, Claude Code, Codex, and "
            "Gemini using indexed official documentation. I do not have "
            "credible source material in this assistant to answer that."
        ),
        no_answer_fallback=(
            "I do not have credible source material in this assistant to answer that."
        ),
    )
    base.update(overrides)
    return Settings(**base)


def _evidence(*, count: int, score: float = 1.0) -> list[EvidenceHit]:
    """Build a deterministic list of evidence bullets.

    The chunks reference random UUIDs; the orchestrator only uses
    them to look up the chunk_id and to populate
    :class:`RetrievedEvidence`. Real Chunk rows are not required
    because the tests do not need the FK to resolve.
    """
    out: list[EvidenceHit] = []
    for i in range(count):
        out.append(
            EvidenceHit(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                product_area="claude_code",
                source_name="docs.test",
                document_title=f"Doc {i + 1}",
                section_path="/x",
                heading="H",
                parent_heading=None,
                chunk_text=f"snippet {i + 1}",
                context_summary="summary",
                source_url=f"https://docs.test/{i + 1}",
                score=score,
                retrieval_type=RetrievalType.hybrid,
                rank=i + 1,
            )
        )
    return out


class _FakeRetriever:
    """In-memory retriever that returns a pre-built evidence list."""

    def __init__(self, evidence: list[EvidenceHit]) -> None:
        self._evidence = evidence
        self.calls: list[dict[str, Any]] = []

    async def retrieve(
        self,
        question: str,
        *,
        product_area: str,
        intent: Intent,
        limit: int,
        top_k: int,
    ) -> list[EvidenceHit]:
        self.calls.append(
            {
                "question": question,
                "product_area": product_area,
                "intent": intent,
                "limit": limit,
                "top_k": top_k,
            }
        )
        return list(self._evidence)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_index_version(session: Any) -> str:
    """Insert an active IndexVersion row and return its source version hash."""
    from datetime import UTC, datetime

    from app.models import IndexStatus, IndexVersion

    version = IndexVersion(
        index_version="index_v1",
        status=IndexStatus.active,
        source_version_hash="sha256:index-v1",
        created_at=datetime.now(UTC),
        promoted_at=datetime.now(UTC),
    )
    session.add(version)
    await session.flush()
    return version.source_version_hash


# ---------------------------------------------------------------------------
# 1. Grounded answer path
# ---------------------------------------------------------------------------


async def test_grounded_answer_persists_messages_and_evidence_and_caches(
    session: Any,
) -> None:
    """The full happy path: grounded answer, cache write, four
    persistence rows."""
    settings = _settings()
    source_version_hash = await _seed_index_version(session)
    retriever = _FakeRetriever(_evidence(count=2))
    orchestrator = Orchestrator(settings, session, retriever=retriever)

    response = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_grounded",
        session_id=uuid.uuid4(),
    )

    # Response shape.
    assert response["no_answer"] is False
    assert response["unsupported"] is False
    assert response["cache_hit"] is False
    assert response["retrieval_strategy"] == RetrievalStrategy.hybrid_reranked.value
    # The stub cites [1] only, so 1 of 2 evidence is cited → medium.
    assert response["confidence"] == Confidence.medium.value
    assert response["domain"] == "claude_code"
    assert response["intent"] == "how_to"
    assert response["source_version_hash"] == source_version_hash
    assert response["answer_policy_version"] == settings.answer_policy_version
    assert "[1]" in response["answer"]  # stub emits a citation marker
    # Citation list excludes the chunk we did not cite (the model only
    # cites [1]); the trace still records both.
    assert len(response["citations"]) == 1
    assert response["citations"][0]["source_name"] == "docs.test"

    # Persistence: 1 user message, 1 assistant message, 2 evidence rows,
    # 1 audit event.
    msg_list = list((await session.execute(select(Message))).scalars().all())
    assert len(msg_list) == 2
    user_msgs = [m for m in msg_list if m.role == MessageRole.user]
    assistant_msgs = [m for m in msg_list if m.role == MessageRole.assistant]
    assert len(user_msgs) == 1
    assert len(assistant_msgs) == 1
    user_msg = user_msgs[0]
    assistant_msg = assistant_msgs[0]
    assert user_msg.content == "How do I configure Claude Code permissions?"
    assert user_msg.domain == "claude_code"
    assert user_msg.intent == "how_to"
    assert assistant_msg.content == response["answer"]
    assert assistant_msg.normalized_query is not None

    evidence_rows = (await session.execute(select(RetrievedEvidence))).scalars().all()
    assert len(evidence_rows) == 2
    assert {e.rank for e in evidence_rows} == {1, 2}
    used = {e.chunk_id for e in evidence_rows if e.used_in_answer}
    unused = {e.chunk_id for e in evidence_rows if not e.used_in_answer}
    assert used == {uuid.UUID(response["citations"][0]["chunk_id"])}
    assert len(unused) == 1
    assert all(e.retrieval_type == ModelRetrievalType.hybrid for e in evidence_rows)

    audit_rows = (await session.execute(select(AuditEvent))).scalars().all()
    assert len(audit_rows) == 1
    audit = audit_rows[0]
    assert audit.action == AuditAction.ask_question
    assert audit.resource_id == str(assistant_msg.message_id)
    assert audit.metadata_["outcome"] == "answer"
    assert audit.metadata_["retrieval_strategy"] == "hybrid_reranked"
    assert audit.metadata_["source_version_hash"] == source_version_hash
    assert audit.metadata_["domain"] == "claude_code"
    assert audit.metadata_["intent"] == "how_to"

    # Cache row written through.
    cache_rows = (await session.execute(select(AnswerCache))).scalars().all()
    assert len(cache_rows) == 1
    assert cache_rows[0].answer == response["answer"]
    assert cache_rows[0].source_version_hash == source_version_hash
    assert cache_rows[0].answer_policy_version == settings.answer_policy_version
    assert cache_rows[0].normalized_question == "how do i configure claude code permissions?"
    assert cache_rows[0].product_area == "claude_code"

    # Retriever was called once with the expected args.
    assert len(retriever.calls) == 1
    assert retriever.calls[0]["intent"] is Intent.how_to


# ---------------------------------------------------------------------------
# 2. Cache hit path
# ---------------------------------------------------------------------------


async def test_cache_hit_skips_retrieval_and_llm(session: Any) -> None:
    """A warm cache must bypass retrieval entirely and the LLM call
    must not be made."""
    source_version_hash = await _seed_index_version(session)
    settings = _settings()
    retriever = _FakeRetriever(_evidence(count=2))
    # Wrap the LLM in a spy so we can assert it was not called.
    llm = StubLLMClient()
    llm_spy = AsyncMock(wraps=llm)

    # Warm the cache: the first call writes through; the second
    # should hit it.
    orchestrator = Orchestrator(settings, session, llm=llm_spy, retriever=retriever)
    first = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_first",
        session_id=uuid.uuid4(),
    )
    assert first["cache_hit"] is False

    # Second request: same question, same session_id family
    # (orchestrator doesn't require a real Session row).
    second = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_second",
        session_id=uuid.uuid4(),
    )

    assert second["cache_hit"] is True
    assert second["retrieval_strategy"] == RetrievalStrategy.cache.value
    assert second["answer"] == first["answer"]
    assert second["source_version_hash"] == source_version_hash

    # The retriever was called only on the first (uncached) request.
    assert len(retriever.calls) == 1
    # LLM was called only once (during the warm-up).
    assert llm_spy.complete.await_count == 1

    # Persistence: each request wrote its own user + assistant
    # message and audit event. The cache row remains unique.
    assert len((await session.execute(select(Message))).scalars().all()) == 4
    assert len((await session.execute(select(AuditEvent))).scalars().all()) == 2
    assert len((await session.execute(select(AnswerCache))).scalars().all()) == 1


# ---------------------------------------------------------------------------
# 3. No-answer path (empty evidence)
# ---------------------------------------------------------------------------


async def test_empty_evidence_returns_no_answer_without_caching(
    session: Any,
) -> None:
    """Empty retrieval results in a no_answer response and no cache
    write."""
    await _seed_index_version(session)
    settings = _settings()
    retriever = _FakeRetriever(evidence=[])
    llm_spy = AsyncMock(wraps=StubLLMClient())
    orchestrator = Orchestrator(settings, session, llm=llm_spy, retriever=retriever)

    response = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_noanswer",
        session_id=uuid.uuid4(),
    )

    assert response["no_answer"] is True
    assert response["unsupported"] is False
    assert response["confidence"] == "none"
    assert response["retrieval_strategy"] == RetrievalStrategy.none.value
    assert response["citations"] == []
    assert response["answer"] == settings.no_answer_fallback
    assert response["domain"] == "claude_code"
    assert response["intent"] == "how_to"

    # No cache write.
    assert (await session.execute(select(AnswerCache))).scalars().all() == []
    # LLM was not called because retrieval was empty.
    assert llm_spy.complete.await_count == 0

    # Audit event records the no_answer outcome.
    audits = (await session.execute(select(AuditEvent))).scalars().all()
    assert len(audits) == 1
    assert audits[0].metadata_["outcome"] == "no_answer"
    assert audits[0].metadata_["reason"] == "weak_evidence"


# ---------------------------------------------------------------------------
# 4. Unsupported path
# ---------------------------------------------------------------------------


async def test_unsupported_question_returns_refusal_without_caching(
    session: Any,
) -> None:
    """An off-domain question triggers the unsupported refusal with
    no cache write and no LLM call."""
    settings = _settings()
    retriever = _FakeRetriever(_evidence(count=2))
    llm_spy = AsyncMock(wraps=StubLLMClient())
    orchestrator = Orchestrator(settings, session, llm=llm_spy, retriever=retriever)

    response = await orchestrator.ask(
        question="What is the recipe for chocolate cake?",
        request_id="req_unsupported",
        session_id=uuid.uuid4(),
    )

    assert response["unsupported"] is True
    assert response["no_answer"] is True
    assert response["domain"] == "unsupported"
    assert response["intent"] == "unsupported"
    assert response["answer"] == settings.unsupported_refusal

    # No retrieval, no LLM, no cache.
    assert retriever.calls == []
    assert llm_spy.complete.await_count == 0
    assert (await session.execute(select(AnswerCache))).scalars().all() == []

    # Audit event records the unsupported outcome.
    audits = (await session.execute(select(AuditEvent))).scalars().all()
    assert len(audits) == 1
    assert audits[0].metadata_["outcome"] == "unsupported"
    assert audits[0].metadata_["reason"] == "unsupported_domain"


# ---------------------------------------------------------------------------
# 5. Citation validation failure
# ---------------------------------------------------------------------------


async def test_citation_validation_failure_returns_no_answer_with_audit(
    session: Any,
) -> None:
    """A bad citation marker collapses to a no_answer response with
    the citation_validation_failed reason in the audit event and
    nothing written to the cache."""
    await _seed_index_version(session)
    settings = _settings()

    class _BadLLM:
        async def complete(self, **_kwargs: Any) -> Any:
            from app.llm.types import LLMResult

            return LLMResult(
                text="This answer cites a non-existent bullet [99].",
                input_tokens=10,
                output_tokens=8,
                model="bad-stub",
                provider="stub",
            )

    retriever = _FakeRetriever(_evidence(count=2))
    orchestrator = Orchestrator(settings, session, llm=_BadLLM(), retriever=retriever)

    response = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_citation_fail",
        session_id=uuid.uuid4(),
    )

    assert response["no_answer"] is True
    assert response["unsupported"] is False
    assert response["confidence"] == "none"
    assert response["citations"] == []
    assert response["answer"] == settings.no_answer_fallback
    assert response["retrieval_strategy"] == RetrievalStrategy.hybrid_reranked.value

    # No cache write.
    assert (await session.execute(select(AnswerCache))).scalars().all() == []

    # Audit event records the citation_validation_failed reason.
    audits = (await session.execute(select(AuditEvent))).scalars().all()
    assert len(audits) == 1
    audit = audits[0]
    assert audit.metadata_["outcome"] == "citation_validation_failed"
    assert "out of range" in audit.metadata_["reason"].lower()

    # Evidence rows ARE still persisted (the orchestrator ran
    # retrieval, it just didn't trust the answer). The user message
    # is also persisted.
    assert len((await session.execute(select(Message))).scalars().all()) == 2
    assert len((await session.execute(select(RetrievedEvidence))).scalars().all()) == 2


# ---------------------------------------------------------------------------
# 6. LLM unavailable → orchestrator error
# ---------------------------------------------------------------------------


async def test_llm_unavailable_raises_orchestrator_error(session: Any) -> None:
    """An LLM transport failure surfaces as :class:`OrchestratorError`
    so the slice 7 route can map it to 503 / cost_limit_reached."""
    await _seed_index_version(session)
    settings = _settings()

    class _DownLLM:
        async def complete(self, **_kwargs: Any) -> Any:
            raise LLMUnavailable("provider is down")

    retriever = _FakeRetriever(_evidence(count=1))
    orchestrator = Orchestrator(settings, session, llm=_DownLLM(), retriever=retriever)

    with pytest.raises(OrchestratorError):
        await orchestrator.ask(
            question="How do I configure Claude Code permissions?",
            request_id="req_llm_down",
            session_id=uuid.uuid4(),
        )


# ---------------------------------------------------------------------------
# 7. Session / user upsert
# ---------------------------------------------------------------------------


async def test_orchestrator_creates_session_and_user_when_missing(
    session: Any,
) -> None:
    """The orchestrator should be able to operate with a bare
    ``session_id`` (no Session row pre-seeded)."""
    from app.models import Session, User

    await _seed_index_version(session)
    settings = _settings()
    retriever = _FakeRetriever(_evidence(count=1))
    orchestrator = Orchestrator(settings, session, retriever=retriever)

    session_id = uuid.uuid4()
    response = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_upsert",
        session_id=session_id,
    )

    # Session row + User row created.
    session_row = await session.get(Session, session_id)
    assert session_row is not None
    assert session_row.user_id == "demo_user"
    user_row = await session.get(User, "demo_user")
    assert user_row is not None
    assert response["message_id"] is not None
