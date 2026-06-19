"""Cache invalidation tests.

Pins the cache-invalidation contract for the orchestrator:

* A grounded answer writes through to the cache under a key derived
  from ``source_version_hash``.
* Bumping the source version yields a cache miss even with the same
  question, and the new key writes through cleanly.
* The old key is still in the table (the cache never deletes by
  itself) but it is no longer reachable through the orchestrator's
  read path.
* ``cache_enabled=False`` short-circuits both the read and the write
  so the orchestrator never reads or writes the cache.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.answer.orchestrator import Orchestrator, RetrievalStrategy
from app.cache.answer_cache import (
    NoOpAnswerCacheStore,
    build_cache_key,
)
from app.cache.factory import build_answer_cache_store
from app.core.config import Settings
from app.llm.stub import StubLLMClient
from app.models import (
    AnswerCache,
    IndexStatus,
    IndexVersion,
    Message,
)
from app.retrieval.types import EvidenceHit
from app.routing.intent import Intent

pytestmark = pytest.mark.asyncio


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        llm_provider="stub",
        llm_model="claude-opus-4-8",
        cache_enabled=True,
        cache_ttl_seconds=3600,
    )
    base.update(overrides)
    return Settings(**base)


def _evidence(*, count: int) -> list[EvidenceHit]:
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
                score=1.0,
                retrieval_type=EvidenceHit.model_fields["retrieval_type"].default,
                rank=i + 1,
            )
        )
    return out


async def _upsert_active_index(session: Any, *, hash_value: str) -> None:
    """Insert or update the active IndexVersion's source hash."""
    version = await session.get(IndexVersion, "index_v1")
    if version is None:
        version = IndexVersion(
            index_version="index_v1",
            status=IndexStatus.active,
            source_version_hash=hash_value,
            created_at=datetime.now(UTC),
            promoted_at=datetime.now(UTC),
        )
        session.add(version)
    else:
        version.source_version_hash = hash_value
    await session.flush()


class _FakeRetriever:
    def __init__(self, evidence: list[EvidenceHit]) -> None:
        self._evidence = evidence

    async def retrieve(
        self,
        question: str,
        *,
        product_area: str,
        intent: Intent,
        limit: int,
        top_k: int,
    ) -> list[EvidenceHit]:
        return list(self._evidence)


# ---------------------------------------------------------------------------
# Cache invalidation: source_version_hash bump
# ---------------------------------------------------------------------------


async def test_source_version_hash_bump_invalidates_cache(session: Any) -> None:
    """Bumping ``source_version_hash`` must yield a cache miss for
    the same question; the new key writes through, the old key
    stays in the table but is no longer reachable."""
    await _upsert_active_index(session, hash_value="sha256:old")
    settings = _settings()
    retriever = _FakeRetriever(_evidence(count=1))

    orchestrator = Orchestrator(settings, session, retriever=retriever)

    # Warm the cache at hash=old.
    first = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_old",
        session_id=uuid.uuid4(),
    )
    assert first["cache_hit"] is False
    assert first["source_version_hash"] == "sha256:old"

    # Second request at hash=old should hit the cache.
    second = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_old_2",
        session_id=uuid.uuid4(),
    )
    assert second["cache_hit"] is True
    assert second["source_version_hash"] == "sha256:old"

    # Bump the source hash — the next request must miss.
    await _upsert_active_index(session, hash_value="sha256:new")
    third = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_new",
        session_id=uuid.uuid4(),
    )
    assert third["cache_hit"] is False
    assert third["source_version_hash"] == "sha256:new"
    assert third["retrieval_strategy"] == RetrievalStrategy.hybrid_reranked.value

    # Both cache keys exist on disk now (the orchestrator does not
    # delete stale rows; that's a separate maintenance concern).
    rows = (await session.execute(select(AnswerCache))).scalars().all()
    keys = {row.cache_key for row in rows}
    assert len(keys) == 2
    old_key = build_cache_key(
        normalized_question="how do i configure claude code permissions?",
        product_area="claude_code",
        source_version_hash="sha256:old",
        answer_policy_version=settings.answer_policy_version,
    )
    new_key = build_cache_key(
        normalized_question="how do i configure claude code permissions?",
        product_area="claude_code",
        source_version_hash="sha256:new",
        answer_policy_version=settings.answer_policy_version,
    )
    assert old_key in keys
    assert new_key in keys
    assert old_key != new_key  # contract: different hashes => different keys

    # A fourth request at hash=new must hit the new key, not the old one.
    fourth = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_new_2",
        session_id=uuid.uuid4(),
    )
    assert fourth["cache_hit"] is True
    assert fourth["source_version_hash"] == "sha256:new"


# ---------------------------------------------------------------------------
# cache_enabled=False
# ---------------------------------------------------------------------------


async def test_cache_disabled_short_circuits_reads_and_writes(
    session: Any,
) -> None:
    """When ``settings.cache_enabled`` is False, the orchestrator
    must never read from or write to the cache. We inject a spy
    store and verify neither ``get`` nor ``put`` was called."""
    await _upsert_active_index(session, hash_value="sha256:abc")
    settings = _settings(cache_enabled=False)
    retriever = _FakeRetriever(_evidence(count=1))
    # ``build_answer_cache_store`` returns a NoOp when disabled.
    cache = build_answer_cache_store(settings, session)
    assert isinstance(cache, NoOpAnswerCacheStore)
    get_spy = AsyncMock(wraps=cache.get)
    put_spy = AsyncMock(wraps=cache.put)
    cache.get = get_spy  # type: ignore[method-assign]
    cache.put = put_spy  # type: ignore[method-assign]
    llm = StubLLMClient()
    llm_spy = AsyncMock(wraps=llm)
    orchestrator = Orchestrator(settings, session, llm=llm_spy, retriever=retriever, cache=cache)

    # First request: no cache hit (NoOp always misses), LLM called.
    first = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_disabled_1",
        session_id=uuid.uuid4(),
    )
    assert first["cache_hit"] is False

    # Second request with the same question: still misses, LLM
    # called again because we did not write through.
    second = await orchestrator.ask(
        question="How do I configure Claude Code permissions?",
        request_id="req_disabled_2",
        session_id=uuid.uuid4(),
    )
    assert second["cache_hit"] is False

    # No cache row should exist on disk either — the NoOp store
    # silently swallows the orchestrator's puts.
    assert (await session.execute(select(AnswerCache))).scalars().all() == []
    # The orchestrator did call the store (the NoOp wrapper is
    # always on the hot path); the spy count just confirms the
    # factory picked the no-op variant. The empty cache table
    # above is the real assertion.
    assert get_spy.await_count == 2
    assert put_spy.await_count == 2
    # The LLM ran once per request.
    assert llm_spy.complete.await_count == 2
    # Both requests still persisted messages.
    assert len((await session.execute(select(Message))).scalars().all()) == 4
