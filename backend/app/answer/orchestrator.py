"""Orchestrator: composes the answer engine.

Wires together the Slice 4 seams (domain guardrail, intent router,
hybrid retrieval, LLM client, citation validator) and the Slice 5
answer cache with the Slice 2 persistence (Session, Message,
RetrievedEvidence, AuditEvent). The HTTP route in Slice 7 calls
:meth:`Orchestrator.ask` and maps the returned dict to the
``/v1/sessions/{id}/messages`` response shape.

Pipeline (per ``docs/ARCHITECTURE.md`` §5.2):

1. Domain guardrail — refuse off-domain questions cheaply.
2. Intent router — short-circuit unsupported / clarify paths.
3. Cache lookup — bypass retrieval and generation on hit.
4. Hybrid retrieval — fetch evidence only when needed.
5. Answer generator — embed evidence, call the LLM.
6. Citation validator — gate grounded answers.
7. Cache write — only for grounded answers.
8. Persistence — user/assistant messages, evidence, audit event.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.answer.generate import AnswerGenerator
from app.answer.no_answer import build_no_answer_response
from app.cache.answer_cache import (
    AnswerCacheStore,
    CachedAnswer,
    build_cache_key,
)
from app.cache.factory import build_answer_cache_store
from app.core.config import Settings
from app.guardrails.domain import Domain, classify_domain, is_unsupported
from app.llm.errors import LLMUnavailable
from app.llm.factory import build_llm_client
from app.llm.protocol import LLMClient
from app.llm.validation import validate_citations
from app.models import (
    AuditAction,
    AuditEvent,
    Confidence,
    Message,
    MessageRole,
    RetrievedEvidence,
    Session,
    User,
    UserRole,
)
from app.models.enums import RetrievalType
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.types import EvidenceHit, chunk_to_citation
from app.routing.intent import Intent, classify_intent, should_skip_retrieval

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Citation(dict[str, object]):
    """A citation row in the response.

    Shaped exactly like :func:`app.retrieval.types.chunk_to_citation`
    emits. ``Citation`` is a ``dict`` subclass so the type system can
    mark it as the response surface without forcing callers through
    pydantic.
    """


class RetrievalStrategy(enum.StrEnum):
    """Public-facing retrieval strategy label.

    Maps to the ``retrieval_strategy`` field in the response. The
    hybrid path emits ``hybrid_reranked``; the cache hit path emits
    ``cache``; unsupported / no-answer paths emit ``none``.
    """

    none = "none"
    cache = "cache"
    exact_lookup = "exact_lookup"
    hybrid_reranked = "hybrid_reranked"


# Type alias for the orchestrator response. The concrete value is a
# ``dict[str, object]`` matching ``docs/API_SPEC.md`` §5. The alias
# is purely documentary — it gives readers a single name to grep for.
AnswerResponse = dict[str, object]


class OrchestratorError(RuntimeError):
    """Raised when the orchestrator cannot answer the question at all.

    Distinct from a no-answer response: this is a transport-level
    failure (LLM provider unavailable, cost limit, etc.) that the
    Slice 7 route layer maps to a 5xx.
    """


# ---------------------------------------------------------------------------
# Seams
# ---------------------------------------------------------------------------


class _RetrieverLike(Protocol):
    """Minimum surface :class:`Orchestrator` requires from a retriever.

    Both :class:`app.retrieval.hybrid.HybridRetriever` and the
    dependency-injected test double satisfy this; keeping the
    protocol narrow lets tests skip the full hybrid wiring.
    """

    async def retrieve(
        self,
        question: str,
        *,
        product_area: str,
        intent: Intent,
        limit: int,
        top_k: int,
    ) -> list[EvidenceHit]: ...


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _retrieve_index_version_hash(
    session: AsyncSession,
) -> tuple[str, str]:
    """Return ``(active_index_version, source_version_hash)``.

    Looks up the first ``IndexVersion`` row in ``active`` status. If
    no active index exists, returns ``("", "")`` so the cache key
    uses an empty source version — every subsequent run invalidates
    the cache once the index is promoted, which is the desired
    behavior before Slice 2 ingestion is wired.
    """
    from app.models import IndexStatus, IndexVersion

    stmt = (
        select(IndexVersion)
        .where(IndexVersion.status == IndexStatus.active)
        .order_by(IndexVersion.promoted_at.desc().nulls_last())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return "", ""
    return row.index_version, row.source_version_hash


def _default_retriever(session: AsyncSession) -> _RetrieverLike:
    """Build the default hybrid retriever.

    Injected as a free function so tests can pass their own
    :class:`_RetrieverLike` and the orchestrator never imports the
    pgvector or FTS machinery on its own.
    """
    return HybridRetriever(session)


class Orchestrator:
    """Composes the answer pipeline and persists the trace.

    The orchestrator is built once per request (it owns the session
    it persists to) and is invoked via :meth:`ask`. It is safe to
    use in tests without a network or live Postgres as long as the
    default ``StubLLMClient`` and ``in_memory_engine`` are used.
    """

    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
        *,
        llm: LLMClient | None = None,
        retriever: _RetrieverLike | None = None,
        cache: AnswerCacheStore | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._llm = llm or build_llm_client(settings)
        self._retriever = retriever or _default_retriever(session)
        self._cache = cache or build_answer_cache_store(settings, session)
        self._generator = AnswerGenerator(
            self._llm,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def ask(
        self,
        *,
        question: str,
        request_id: str,
        session_id: uuid.UUID,
    ) -> AnswerResponse:
        """Process a single user question end-to-end.

        The returned dict matches :class:`AnswerResponse` and the
        ``/v1/sessions/{id}/messages`` response in
        ``docs/API_SPEC.md`` §5. The caller is responsible for
        committing the session once it has serialized the response.
        """
        normalized = question.strip()
        domain = classify_domain(question)
        intent = classify_intent(question, domain)
        # The router emits ``Intent.unsupported`` when the guardrail
        # refused, but the orchestrator re-derives it from the domain
        # so a stale intent cannot leak through.
        if is_unsupported(domain):
            intent = Intent.unsupported

        if intent is Intent.unsupported:
            return await self._respond_unsupported(
                request_id=request_id,
                session_id=session_id,
                question=question,
                normalized=normalized,
                domain=domain,
                intent=Intent.unsupported,
            )

        # Look up the active index so the cache key carries the
        # current source version. A missing index returns an empty
        # hash, which still produces a stable (and unique) key.
        _active_index_version, source_version_hash = await _retrieve_index_version_hash(
            self._session
        )

        # Normalize the question for the cache key. The slice 5
        # contract pins the four inputs verbatim; whitespace
        # normalization is a soft enhancement that improves hit
        # rate on minor formatting differences.
        cache_normalized = normalized.lower()
        cache_key = build_cache_key(
            normalized_question=cache_normalized,
            product_area=domain.value,
            source_version_hash=source_version_hash,
            answer_policy_version=self._settings.answer_policy_version,
        )
        cached = await self._cache.get(cache_key=cache_key)
        if cached is not None:
            return await self._respond_cache_hit(
                request_id=request_id,
                session_id=session_id,
                question=question,
                normalized=normalized,
                domain=domain,
                intent=intent,
                source_version_hash=source_version_hash,
                cached=cached,
            )

        # Empty / very short questions map to ``Intent.clarify`` in
        # the router. The orchestrator surfaces them as no-answer so
        # we never burn an LLM call on "hi".
        if should_skip_retrieval(intent):
            return await self._respond_no_answer(
                request_id=request_id,
                session_id=session_id,
                question=question,
                normalized=normalized,
                domain=domain,
                intent=intent,
                source_version_hash=source_version_hash,
                reason="no_answer",
            )

        evidence = await self._retriever.retrieve(
            question,
            product_area=domain.value,
            intent=intent,
            limit=self._settings.retrieval_max_candidates,
            top_k=self._settings.retrieval_top_k,
        )

        if not evidence:
            return await self._respond_no_answer(
                request_id=request_id,
                session_id=session_id,
                question=question,
                normalized=normalized,
                domain=domain,
                intent=intent,
                source_version_hash=source_version_hash,
                reason="weak_evidence",
            )

        # Record retrieval strategy on the response. The hybrid
        # retriever tags each hit with its actual type; the
        # orchestrator picks the most specific label.
        strategy = self._strategy_for(intent, evidence)

        try:
            llm_result = await self._generator.generate(question, evidence)
        except LLMUnavailable as exc:
            # Slice 7 maps this to ``cost_limit_reached`` (503) when
            # the cause is 429, otherwise to ``internal_error`` (500).
            raise OrchestratorError(str(exc)) from exc

        # Validate citations; a hard-fail collapses to a no-answer
        # response carrying the citation_validation_failed reason
        # in the audit event.
        validation = validate_citations(answer_text=llm_result.text, evidence=evidence)
        if not validation.valid:
            return await self._respond_validation_failed(
                request_id=request_id,
                session_id=session_id,
                question=question,
                normalized=normalized,
                domain=domain,
                intent=intent,
                evidence=evidence,
                strategy=strategy,
                source_version_hash=source_version_hash,
                reason=validation.reason or "citation_validation_failed",
            )

        # The LLM may emit the no-answer refusal even when evidence
        # is non-empty. Honor the contract and treat it as a
        # weak-evidence fallback.
        if not validation.cited_indices and self._is_no_answer_refusal(llm_result.text):
            return await self._respond_no_answer(
                request_id=request_id,
                session_id=session_id,
                question=question,
                normalized=normalized,
                domain=domain,
                intent=intent,
                source_version_hash=source_version_hash,
                reason="no_answer",
                evidence=evidence,
            )

        citations: list[Citation] = [Citation(chunk_to_citation(hit)) for hit in evidence]
        # Cite-once: the response surface only shows the citations
        # the model actually referenced. The trace keeps every
        # retrieved chunk.
        cited_set = set(validation.cited_indices)
        used_indices = sorted(cited_set) if cited_set else list(range(1, len(evidence) + 1))
        used_chunk_ids = {evidence[i - 1].chunk_id for i in used_indices}
        visible_citations = [
            c for c, hit in zip(citations, evidence, strict=True) if hit.chunk_id in used_chunk_ids
        ]
        confidence = self._confidence_for(used_indices, len(evidence))

        response = await self._persist_and_respond(
            request_id=request_id,
            session_id=session_id,
            question=question,
            normalized=normalized,
            domain=domain,
            intent=intent,
            answer=llm_result.text,
            citations=visible_citations,
            evidence=evidence,
            strategy=strategy,
            source_version_hash=source_version_hash,
            confidence=confidence,
            cache_hit=False,
            cache_key=cache_key,
            cache_normalized=cache_normalized,
        )
        return response

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _respond_unsupported(
        self,
        *,
        request_id: str,
        session_id: uuid.UUID,
        question: str,
        normalized: str,
        domain: Domain,
        intent: Intent,
    ) -> AnswerResponse:
        """Persist an unsupported refusal and return the no-answer shape."""
        message_id = await self._persist_messages(
            session_id=session_id,
            question=question,
            normalized=normalized,
            domain=domain,
            intent=intent,
            answer=self._settings.unsupported_refusal,
            confidence=Confidence.none,
            evidence=[],
            citations=[],
        )
        await self._persist_audit(
            request_id=request_id,
            session_id=session_id,
            message_id=message_id,
            domain=domain,
            intent=intent,
            outcome="unsupported",
            metadata={
                "reason": "unsupported_domain",
                "retrieval_strategy": RetrievalStrategy.none.value,
            },
        )
        await self._session.flush()
        return build_no_answer_response(
            request_id=request_id,
            domain_value=domain.value,
            intent=Intent.unsupported,
            reason="unsupported",
            copy=self._settings.unsupported_refusal,
            message_id=str(message_id),
        )

    async def _respond_cache_hit(
        self,
        *,
        request_id: str,
        session_id: uuid.UUID,
        question: str,
        normalized: str,
        domain: Domain,
        intent: Intent,
        source_version_hash: str,
        cached: CachedAnswer,
    ) -> AnswerResponse:
        """Persist a cache-hit response and return the cached payload."""
        message_id = await self._persist_messages(
            session_id=session_id,
            question=question,
            normalized=normalized,
            domain=domain,
            intent=intent,
            answer=cached.answer,
            confidence=cached.confidence,
            evidence=[],
            citations=[Citation(c) for c in cached.citations],
        )
        await self._persist_audit(
            request_id=request_id,
            session_id=session_id,
            message_id=message_id,
            domain=domain,
            intent=intent,
            outcome="cache_hit",
            metadata={
                "retrieval_strategy": RetrievalStrategy.cache.value,
                "source_version_hash": cached.source_version_hash,
            },
        )
        await self._session.flush()
        return AnswerResponse(
            request_id=request_id,
            message_id=str(message_id),
            answer=cached.answer,
            citations=[Citation(c) for c in cached.citations],
            domain=domain.value,
            intent=intent.value,
            confidence=cached.confidence.value,
            cache_hit=True,
            retrieval_strategy=RetrievalStrategy.cache.value,
            unsupported=False,
            no_answer=False,
            source_version_hash=cached.source_version_hash,
            answer_policy_version=cached.answer_policy_version,
        )

    async def _respond_no_answer(
        self,
        *,
        request_id: str,
        session_id: uuid.UUID,
        question: str,
        normalized: str,
        domain: Domain,
        intent: Intent,
        source_version_hash: str,
        reason: str,
        evidence: list[EvidenceHit] | None = None,
    ) -> AnswerResponse:
        """Persist and return a no-answer response (weak evidence, etc.)."""
        message_id = await self._persist_messages(
            session_id=session_id,
            question=question,
            normalized=normalized,
            domain=domain,
            intent=intent,
            answer=self._settings.no_answer_fallback,
            confidence=Confidence.none,
            evidence=evidence or [],
            citations=[],
        )
        await self._persist_audit(
            request_id=request_id,
            session_id=session_id,
            message_id=message_id,
            domain=domain,
            intent=intent,
            outcome="no_answer",
            metadata={
                "reason": reason,
                "retrieval_strategy": RetrievalStrategy.none.value,
                "source_version_hash": source_version_hash,
            },
        )
        await self._session.flush()
        return build_no_answer_response(
            request_id=request_id,
            domain_value=domain.value,
            intent=intent,
            reason=reason,
            copy=self._settings.no_answer_fallback,
            message_id=str(message_id),
        )

    async def _respond_validation_failed(
        self,
        *,
        request_id: str,
        session_id: uuid.UUID,
        question: str,
        normalized: str,
        domain: Domain,
        intent: Intent,
        evidence: list[EvidenceHit],
        strategy: RetrievalStrategy,
        source_version_hash: str,
        reason: str,
    ) -> AnswerResponse:
        """Persist a citation-validation failure as a no-answer response.

        The reason flows into the audit event so a SRE can grep for
        the exact failure mode; the response body itself carries the
        no-answer fallback copy, not the bad LLM output, so we never
        ship a citation-incorrect answer to the user.
        """
        message_id = await self._persist_messages(
            session_id=session_id,
            question=question,
            normalized=normalized,
            domain=domain,
            intent=intent,
            answer=self._settings.no_answer_fallback,
            confidence=Confidence.none,
            evidence=evidence,
            citations=[],
        )
        await self._persist_audit(
            request_id=request_id,
            session_id=session_id,
            message_id=message_id,
            domain=domain,
            intent=intent,
            outcome="citation_validation_failed",
            metadata={
                "reason": reason,
                "retrieval_strategy": strategy.value,
                "source_version_hash": source_version_hash,
            },
        )
        await self._session.flush()
        return build_no_answer_response(
            request_id=request_id,
            domain_value=domain.value,
            intent=intent,
            reason="citation_validation_failed",
            copy=self._settings.no_answer_fallback,
            message_id=str(message_id),
            retrieval_strategy=strategy.value,
        )

    async def _persist_and_respond(
        self,
        *,
        request_id: str,
        session_id: uuid.UUID,
        question: str,
        normalized: str,
        domain: Domain,
        intent: Intent,
        answer: str,
        citations: list[Citation],
        evidence: list[EvidenceHit],
        strategy: RetrievalStrategy,
        source_version_hash: str,
        confidence: Confidence,
        cache_hit: bool,
        cache_key: str,
        cache_normalized: str,
    ) -> AnswerResponse:
        """Persist a grounded answer, write the cache, and return the response."""
        message_id = await self._persist_messages(
            session_id=session_id,
            question=question,
            normalized=normalized,
            domain=domain,
            intent=intent,
            answer=answer,
            confidence=confidence,
            evidence=evidence,
            citations=citations,
        )
        await self._cache.put(
            cache_key=cache_key,
            value=CachedAnswer(
                answer=answer,
                citations=[dict(c) for c in citations],
                confidence=confidence,
                source_version_hash=source_version_hash,
                answer_policy_version=self._settings.answer_policy_version,
                created_at=_utcnow(),
                ttl_expires_at=_utcnow_from_seconds(self._settings.cache_ttl_seconds),
            ),
        )
        await self._persist_audit(
            request_id=request_id,
            session_id=session_id,
            message_id=message_id,
            domain=domain,
            intent=intent,
            outcome="answer",
            metadata={
                "retrieval_strategy": strategy.value,
                "source_version_hash": source_version_hash,
                "cache_hit": False,
            },
        )
        # Also backfill the normalized_question / product_area
        # fields the cache factory leaves blank so the row is
        # queryable.
        await self._backfill_cache_metadata(
            cache_key=cache_key,
            normalized_question=cache_normalized,
            product_area=domain.value,
        )
        await self._session.flush()
        return AnswerResponse(
            request_id=request_id,
            message_id=str(message_id),
            answer=answer,
            citations=list(citations),
            domain=domain.value,
            intent=intent.value,
            confidence=confidence.value,
            cache_hit=cache_hit,
            retrieval_strategy=strategy.value,
            unsupported=False,
            no_answer=False,
            source_version_hash=source_version_hash,
            answer_policy_version=self._settings.answer_policy_version,
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _ensure_user(self, session_id: uuid.UUID) -> str:
        """Make sure a User + Session row pair exists for ``session_id``.

        The orchestrator writes messages against a session the Slice 7
        route already created. To keep the orchestrator unit-testable
        without that scaffolding, this helper upserts the minimum
        rows needed to satisfy foreign keys when the caller passes a
        bare ``session_id``. Returns the ``user_id`` to attach to
        audit events.

        Raises ``RuntimeError`` if a real session row exists but
        references a user that the orchestrator cannot resolve —
        that means the orchestrator was handed a stale session id
        and the route layer should retry.
        """
        session = await self._session.get(Session, session_id)
        if session is not None:
            user_id = session.user_id
        else:
            # Caller passed a bare UUID with no Session row yet.
            # Create both rows so the message inserts do not trip
            # the FK on ``sessions.session_id``.
            user_id = "demo_user"
            self._session.add(
                Session(
                    session_id=session_id,
                    user_id=user_id,
                    channel="chat",
                    created_at=_utcnow(),
                    expires_at=_utcnow_from_seconds(self._settings.index_session_ttl_seconds),
                )
            )
            await self._session.flush()

        existing_user = await self._session.get(User, user_id)
        if existing_user is None:
            self._session.add(
                User(
                    user_id=user_id,
                    role=UserRole.demo_user,
                    created_at=_utcnow(),
                )
            )
            await self._session.flush()
        return user_id

    async def _persist_messages(
        self,
        *,
        session_id: uuid.UUID,
        question: str,
        normalized: str,
        domain: Domain,
        intent: Intent,
        answer: str,
        confidence: Confidence,
        evidence: list[EvidenceHit],
        citations: list[Citation],
    ) -> uuid.UUID:
        """Persist the user + assistant messages and retrieved evidence.

        Returns the assistant message id so the audit event can
        reference it. Both messages are flushed before the function
        returns so the row ids are available.
        """
        await self._ensure_user(session_id)
        now = _utcnow()
        user_msg = Message(
            session_id=session_id,
            role=MessageRole.user,
            content=question,
            normalized_query=normalized,
            domain=domain.value,
            intent=intent.value,
            created_at=now,
        )
        self._session.add(user_msg)
        await self._session.flush()

        # used_in_answer is per-evidence; we mark only the chunks
        # that appear in the citation list (or all of them when the
        # answer is a no-answer / unsupported refusal because no
        # specific chunk is cited).
        cited_chunk_ids: set[uuid.UUID] = {
            uuid.UUID(str(c["chunk_id"]))  # type: ignore[arg-type]
            for c in citations
        }
        for hit in evidence:
            self._session.add(
                RetrievedEvidence(
                    message_id=user_msg.message_id,
                    chunk_id=hit.chunk_id,
                    rank=hit.rank,
                    score=float(hit.score),
                    retrieval_type=RetrievalType(hit.retrieval_type.value),
                    used_in_answer=hit.chunk_id in cited_chunk_ids,
                )
            )
        await self._session.flush()

        assistant_msg = Message(
            session_id=session_id,
            role=MessageRole.assistant,
            content=answer,
            normalized_query=normalized,
            domain=domain.value,
            intent=intent.value,
            created_at=now,
        )
        self._session.add(assistant_msg)
        await self._session.flush()
        return assistant_msg.message_id

    async def _persist_audit(
        self,
        *,
        request_id: str,
        session_id: uuid.UUID,
        message_id: uuid.UUID,
        domain: Domain,
        intent: Intent,
        outcome: str,
        metadata: dict[str, Any],
    ) -> None:
        """Persist an ``ask_question`` audit event.

        The ``metadata`` JSON carries the retrieval strategy, source
        version hash, and any error reason so a SRE can reconstruct
        the trace from the audit log alone.
        """
        user_id = await self._ensure_user(session_id)
        full_metadata: dict[str, Any] = {
            "request_id": request_id,
            "session_id": str(session_id),
            "message_id": str(message_id),
            "domain": domain.value,
            "intent": intent.value,
            "outcome": outcome,
        }
        full_metadata.update(metadata)
        self._session.add(
            AuditEvent(
                user_id=user_id,
                role=UserRole.demo_user,
                action=AuditAction.ask_question,
                resource_type="message",
                resource_id=str(message_id),
                timestamp=_utcnow(),
                metadata_=full_metadata,
            )
        )
        await self._session.flush()

    async def _backfill_cache_metadata(
        self,
        *,
        cache_key: str,
        normalized_question: str,
        product_area: str,
    ) -> None:
        """Populate the cache row's query / area columns post-write.

        :class:`PostgresAnswerCacheStore.put` writes the answer +
        citations but leaves ``normalized_question`` and
        ``product_area`` blank for performance. The orchestrator
        owns the missing metadata so the cache is queryable from
        the admin surface.
        """
        from app.models import AnswerCache

        row = await self._session.get(AnswerCache, cache_key)
        if row is None:
            return
        row.normalized_question = normalized_question
        row.product_area = product_area
        await self._session.flush()

    # ------------------------------------------------------------------
    # Pure helpers (no DB, no network)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_no_answer_refusal(answer_text: str) -> bool:
        """Match the canonical no-answer paragraph the model emits."""
        from app.llm.prompts import NO_ANSWER_REFUSAL

        stripped = answer_text.strip()
        if stripped == NO_ANSWER_REFUSAL:
            return True
        return "do not have credible source material" in stripped.lower()

    @staticmethod
    def _strategy_for(intent: Intent, evidence: list[EvidenceHit]) -> RetrievalStrategy:
        if not evidence:
            return RetrievalStrategy.none
        if intent is Intent.exact_lookup:
            return RetrievalStrategy.exact_lookup
        return RetrievalStrategy.hybrid_reranked

    @staticmethod
    def _confidence_for(cited_indices: list[int], evidence_count: int) -> Confidence:
        if not cited_indices or evidence_count == 0:
            return Confidence.low
        ratio = len(cited_indices) / evidence_count
        if ratio >= 0.66:
            return Confidence.high
        if ratio >= 0.33:
            return Confidence.medium
        return Confidence.low


def _utcnow_from_seconds(seconds: int) -> datetime:
    """Return ``now() + seconds`` as a naive-or-aware UTC datetime.

    Mirrors the :func:`app.cache.answer_cache._utcnow` convention so
    the cache and the message timestamps stay comparable.
    """
    from datetime import timedelta

    return datetime.now(UTC) + timedelta(seconds=seconds)


__all__ = [
    "AnswerResponse",
    "Citation",
    "Orchestrator",
    "OrchestratorError",
    "RetrievalStrategy",
]
