"""Round-trip tests for every ORM model.

Each test inserts a single row through the ORM and reads it back,
verifying the columns, the UUID type, JSON serialization, and enum
coercion behave as documented in ``docs/DATA_MODEL.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnswerCache,
    AuditAction,
    AuditEvent,
    Chunk,
    Confidence,
    Document,
    DocumentStatus,
    EvaluationBehavior,
    EvaluationCase,
    EvaluationRun,
    EvaluationStatus,
    ExactTerm,
    IndexStatus,
    IndexVersion,
    IngestionJob,
    JobStage,
    JobStatus,
    Message,
    MessageRole,
    RetrievalType,
    RetrievedEvidence,
    Session,
    TermType,
    User,
    UserRole,
)


def _now() -> datetime:
    return datetime.now(UTC)


async def _session_id(db_session: AsyncSession) -> uuid.UUID:
    user = User(user_id="demo_user", role=UserRole.demo_user, created_at=_now())
    db_session.add(user)
    await db_session.flush()
    session = Session(
        user_id="demo_user",
        channel="chat",
        created_at=_now(),
        expires_at=_now() + timedelta(hours=2),
    )
    db_session.add(session)
    await db_session.flush()
    return session.session_id


async def test_user_round_trip(db_session: AsyncSession) -> None:
    user = User(user_id="admin", role=UserRole.admin, created_at=_now())
    db_session.add(user)
    await db_session.commit()

    loaded = await db_session.scalar(select(User).where(User.user_id == "admin"))
    assert loaded is not None
    assert loaded.user_id == "admin"
    assert loaded.role is UserRole.admin


async def test_index_version_round_trip(db_session: AsyncSession) -> None:
    version = IndexVersion(
        index_version="index_v1",
        status=IndexStatus.candidate,
        source_version_hash="abc123",
        created_at=_now(),
    )
    db_session.add(version)
    await db_session.commit()

    loaded = await db_session.scalar(
        select(IndexVersion).where(IndexVersion.index_version == "index_v1")
    )
    assert loaded is not None
    assert loaded.status is IndexStatus.candidate


async def test_document_round_trip(db_session: AsyncSession) -> None:
    db_session.add(
        IndexVersion(
            index_version="index_v1",
            status=IndexStatus.candidate,
            source_version_hash="abc",
            created_at=_now(),
        )
    )
    doc = Document(
        index_version="index_v1",
        source_name="codex",
        product_area="codex",
        source_url="https://example.com/docs",
        title="Codex CLI",
        content_checksum="deadbeef",
        last_fetched_at=_now(),
        status=DocumentStatus.active,
    )
    db_session.add(doc)
    await db_session.commit()

    loaded = await db_session.scalar(select(Document))
    assert loaded is not None
    assert loaded.source_name == "codex"
    assert loaded.status is DocumentStatus.active
    assert isinstance(loaded.document_id, uuid.UUID)


async def test_chunk_round_trip_with_json(db_session: AsyncSession) -> None:
    db_session.add(
        IndexVersion(
            index_version="index_v1",
            status=IndexStatus.candidate,
            source_version_hash="abc",
            created_at=_now(),
        )
    )
    doc = Document(
        index_version="index_v1",
        source_name="codex",
        product_area="codex",
        source_url="https://example.com",
        title="T",
        content_checksum="h",
        last_fetched_at=_now(),
        status=DocumentStatus.active,
    )
    db_session.add(doc)
    await db_session.flush()

    chunk = Chunk(
        document_id=doc.document_id,
        product_area="codex",
        section_path="CLI > auth",
        heading="auth",
        parent_heading="CLI",
        chunk_text="How to use --api-key flag",
        context_summary="Authentication section",
        exact_terms=["--api-key"],
        chunk_order=0,
        content_checksum="hh",
    )
    db_session.add(chunk)
    await db_session.commit()

    loaded = await db_session.scalar(select(Chunk))
    assert loaded is not None
    assert loaded.exact_terms == ["--api-key"]
    assert isinstance(loaded.chunk_id, uuid.UUID)


async def test_exact_term_unique_constraint(db_session: AsyncSession) -> None:
    db_session.add(
        IndexVersion(
            index_version="index_v1",
            status=IndexStatus.candidate,
            source_version_hash="abc",
            created_at=_now(),
        )
    )
    doc = Document(
        index_version="index_v1",
        source_name="codex",
        product_area="codex",
        source_url="u",
        title="t",
        content_checksum="c",
        last_fetched_at=_now(),
        status=DocumentStatus.active,
    )
    db_session.add(doc)
    await db_session.flush()
    chunk = Chunk(
        document_id=doc.document_id,
        product_area="codex",
        section_path="s",
        heading="h",
        chunk_text="t",
        context_summary="c",
        exact_terms=[],
        chunk_order=0,
        content_checksum="k",
    )
    db_session.add(chunk)
    await db_session.flush()

    db_session.add(
        ExactTerm(
            term_text="--api-key",
            term_type=TermType.flag,
            product_area="codex",
            document_id=doc.document_id,
            chunk_id=chunk.chunk_id,
        )
    )
    await db_session.commit()

    from sqlalchemy.exc import IntegrityError

    db_session.add(
        ExactTerm(
            term_text="--api-key",
            term_type=TermType.flag,
            product_area="codex",
            document_id=doc.document_id,
            chunk_id=chunk.chunk_id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_ingestion_job_round_trip(db_session: AsyncSession) -> None:
    job = IngestionJob(
        source_name="codex",
        status=JobStatus.running,
        stage=JobStage.embedding,
        started_at=_now(),
        retryable=True,
    )
    db_session.add(job)
    await db_session.commit()

    loaded = await db_session.scalar(select(IngestionJob))
    assert loaded is not None
    assert loaded.status is JobStatus.running
    assert loaded.stage is JobStage.embedding


async def test_session_and_message_round_trip(db_session: AsyncSession) -> None:
    session_id = await _session_id(db_session)
    msg = Message(
        session_id=session_id,
        role=MessageRole.user,
        content="Hello",
        domain="codex",
        intent="how_to",
        created_at=_now(),
    )
    db_session.add(msg)
    await db_session.commit()

    loaded = await db_session.scalar(select(Message))
    assert loaded is not None
    assert loaded.role is MessageRole.user
    assert loaded.domain == "codex"


async def test_retrieved_evidence_round_trip(db_session: AsyncSession) -> None:
    db_session.add(
        IndexVersion(
            index_version="index_v1",
            status=IndexStatus.candidate,
            source_version_hash="abc",
            created_at=_now(),
        )
    )
    doc = Document(
        index_version="index_v1",
        source_name="codex",
        product_area="codex",
        source_url="u",
        title="t",
        content_checksum="c",
        last_fetched_at=_now(),
        status=DocumentStatus.active,
    )
    db_session.add(doc)
    await db_session.flush()
    chunk = Chunk(
        document_id=doc.document_id,
        product_area="codex",
        section_path="s",
        heading="h",
        chunk_text="t",
        context_summary="c",
        exact_terms=[],
        chunk_order=0,
        content_checksum="k",
    )
    db_session.add(chunk)
    await db_session.flush()

    session_id = await _session_id(db_session)
    msg = Message(
        session_id=session_id,
        role=MessageRole.user,
        content="Q?",
        created_at=_now(),
    )
    db_session.add(msg)
    await db_session.flush()

    evidence = RetrievedEvidence(
        message_id=msg.message_id,
        chunk_id=chunk.chunk_id,
        rank=1,
        score=0.92,
        retrieval_type=RetrievalType.hybrid,
        used_in_answer=True,
    )
    db_session.add(evidence)
    await db_session.commit()

    loaded = await db_session.scalar(select(RetrievedEvidence))
    assert loaded is not None
    assert loaded.retrieval_type is RetrievalType.hybrid
    assert loaded.used_in_answer is True


async def test_answer_cache_round_trip(db_session: AsyncSession) -> None:
    cache = AnswerCache(
        cache_key="k1",
        normalized_question="how do I",
        product_area="codex",
        answer="use X",
        citations=[{"chunk_id": "abc", "url": "u"}],
        source_version_hash="h",
        answer_policy_version="v1",
        confidence=Confidence.high,
        ttl_expires_at=_now() + timedelta(hours=1),
        created_at=_now(),
        last_used_at=_now(),
    )
    db_session.add(cache)
    await db_session.commit()

    loaded = await db_session.scalar(select(AnswerCache))
    assert loaded is not None
    assert loaded.confidence is Confidence.high
    assert loaded.citations == [{"chunk_id": "abc", "url": "u"}]


async def test_evaluation_case_and_run_round_trip(db_session: AsyncSession) -> None:
    db_session.add(
        IndexVersion(
            index_version="index_v1",
            status=IndexStatus.candidate,
            source_version_hash="abc",
            created_at=_now(),
        )
    )
    case = EvaluationCase(
        question="How do I configure X?",
        expected_domain="codex",
        expected_intent="how_to",
        expected_sources=["docs"],
        required_answer_points=["mentions X"],
        forbidden_answer_points=["unsupported claim"],
        expected_behavior=EvaluationBehavior.answer,
    )
    db_session.add(case)
    await db_session.flush()

    run = EvaluationRun(
        suite_name="mvp_golden_50",
        index_version="index_v1",
        started_at=_now(),
        status=EvaluationStatus.running,
        metrics={"pass_rate": 0.0},
        failure_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    loaded_case = await db_session.scalar(select(EvaluationCase))
    loaded_run = await db_session.scalar(select(EvaluationRun))
    assert loaded_case is not None and loaded_case.expected_behavior is EvaluationBehavior.answer
    assert loaded_run is not None and loaded_run.metrics == {"pass_rate": 0.0}


async def test_audit_event_round_trip(db_session: AsyncSession) -> None:
    db_session.add(User(user_id="demo_user", role=UserRole.demo_user, created_at=_now()))
    event = AuditEvent(
        user_id="demo_user",
        role=UserRole.demo_user,
        action=AuditAction.ask_question,
        resource_type="session",
        resource_id="sess_001",
        timestamp=_now(),
        metadata_={"request_id": "req_123", "latency_ms": 200},
    )
    db_session.add(event)
    await db_session.commit()

    loaded = await db_session.scalar(select(AuditEvent))
    assert loaded is not None
    assert loaded.action is AuditAction.ask_question
    # ``metadata`` is reserved by SQLAlchemy; we renamed the Python
    # attribute to ``metadata_`` but the column keeps its public name.
    assert loaded.metadata_ == {"request_id": "req_123", "latency_ms": 200}
