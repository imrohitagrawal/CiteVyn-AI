"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-18 00:00:00

Creates every table from ``docs/DATA_MODEL.md`` for Slice 2:

* users
* index_versions
* documents
* chunks
* exact_terms
* ingestion_jobs
* sessions
* messages
* retrieved_evidence
* answer_cache
* evaluation_cases
* evaluation_runs
* audit_events

The embedding column on ``chunks`` and the ``tsvector``/vector indexes
are intentionally deferred to Phase 2 alongside the chunker.

Embedding deferral note
-----------------------
``chunks.embedding`` is left out of the initial schema on purpose.
The MVP vector retriever uses a ``StubEmbedder`` that returns the
zero vector, so retrieval collapses to a pure exact + keyword
search. Adding the column now would (a) require picking an
embedding model and dimension we have not committed to and (b)
constrain the migration once the Phase 2 embedder is chosen. The
follow-up migration will introduce:

* ``chunks.embedding vector(<dim>)`` using ``pgvector`` on Postgres
  and a no-op ``BLOB`` on SQLite.
* An ``ivfflat`` (or ``hnsw``) index over ``embedding`` for cosine
  similarity, created ``CONCURRENTLY`` so a backfill can run with
  the table online.
* A downgrade that drops the index and the column together.

Until that lands, the retriever route is exercised in tests with
``StubEmbedder`` (see ``backend/app/retrieval/vector.py``) and the
hybrid short-circuit on exact-lookup queries is the only retrieval
path that has a real effect on the live demo.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# ``GUID`` is the dialect-agnostic UUID type used by the ORM models. We
# import it from the application so the migration creates the same
# column type the models expect (real UUID on Postgres, CHAR(36) on
# SQLite).
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.models.base import GUID  # noqa: E402

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tables are created in dependency order. ``users`` and
    # ``evaluation_runs`` come first so the rest of the schema can
    # reference them via foreign key on first creation — SQLite cannot
    # ``ALTER TABLE ... ADD CONSTRAINT`` afterward, so we never rely on
    # back-fill FKs.
    # -- users -----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=128), primary_key=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- evaluation_runs -------------------------------------------------
    # Created before index_versions so the latter can FK to it directly.
    op.create_table(
        "evaluation_runs",
        sa.Column("run_id", GUID(), primary_key=True),
        sa.Column("suite_name", sa.String(length=64), nullable=False),
        sa.Column("index_version", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("failure_summary", sa.JSON(), nullable=False),
    )
    op.create_index("ix_evaluation_runs_suite_name", "evaluation_runs", ["suite_name"])

    # -- index_versions --------------------------------------------------
    op.create_table(
        "index_versions",
        sa.Column("index_version", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_version_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluation_run_id", GUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.run_id"],
            name="fk_index_versions_evaluation_run",
            ondelete="SET NULL",
        ),
    )

    # -- documents -------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("document_id", GUID(), primary_key=True),
        sa.Column("index_version", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("product_area", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_checksum", sa.String(length=128), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["index_version"],
            ["index_versions.index_version"],
            name="fk_documents_index_version",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_documents_source_name", "documents", ["source_name"])
    op.create_index("ix_documents_product_area", "documents", ["product_area"])

    # -- chunks ----------------------------------------------------------
    op.create_table(
        "chunks",
        sa.Column("chunk_id", GUID(), primary_key=True),
        sa.Column("document_id", GUID(), nullable=False),
        sa.Column("product_area", sa.String(length=64), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("parent_heading", sa.Text(), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=False),
        sa.Column(
            "exact_terms",
            # JSONB on Postgres falls back to JSON elsewhere; we use the
            # generic JSON type to keep the migration portable.
            sa.JSON(),
            nullable=False,
        ),
        sa.Column("chunk_order", sa.Integer(), nullable=False),
        sa.Column("content_checksum", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name="fk_chunks_document",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_chunks_product_area", "chunks", ["product_area"])

    # -- exact_terms -----------------------------------------------------
    op.create_table(
        "exact_terms",
        sa.Column("term_id", GUID(), primary_key=True),
        sa.Column("term_text", sa.Text(), nullable=False),
        sa.Column("term_type", sa.String(length=32), nullable=False),
        sa.Column("product_area", sa.String(length=64), nullable=False),
        sa.Column("document_id", GUID(), nullable=False),
        sa.Column("chunk_id", GUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name="fk_exact_terms_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.chunk_id"],
            name="fk_exact_terms_chunk",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "term_text",
            "product_area",
            "chunk_id",
            name="uq_exact_terms_term_product_chunk",
        ),
    )

    # -- ingestion_jobs --------------------------------------------------
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", GUID(), primary_key=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])

    # -- sessions --------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("session_id", GUID(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("current_product_area", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_sessions_user",
            ondelete="RESTRICT",
        ),
    )

    # -- messages --------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("message_id", GUID(), primary_key=True),
        sa.Column("session_id", GUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=64), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.session_id"],
            name="fk_messages_session",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    # -- retrieved_evidence ---------------------------------------------
    op.create_table(
        "retrieved_evidence",
        sa.Column("evidence_id", GUID(), primary_key=True),
        sa.Column("message_id", GUID(), nullable=False),
        sa.Column("chunk_id", GUID(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("retrieval_type", sa.String(length=32), nullable=False),
        sa.Column("used_in_answer", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.message_id"],
            name="fk_retrieved_evidence_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.chunk_id"],
            name="fk_retrieved_evidence_chunk",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_retrieved_evidence_message_id",
        "retrieved_evidence",
        ["message_id"],
    )

    # -- answer_cache ----------------------------------------------------
    op.create_table(
        "answer_cache",
        sa.Column("cache_key", sa.String(length=256), primary_key=True),
        sa.Column("normalized_question", sa.Text(), nullable=False),
        sa.Column("product_area", sa.String(length=64), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("source_version_hash", sa.String(length=128), nullable=False),
        sa.Column("answer_policy_version", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- evaluation_cases ------------------------------------------------
    op.create_table(
        "evaluation_cases",
        sa.Column("case_id", GUID(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_domain", sa.String(length=64), nullable=True),
        sa.Column("expected_intent", sa.String(length=64), nullable=True),
        sa.Column("expected_sources", sa.JSON(), nullable=False),
        sa.Column("required_answer_points", sa.JSON(), nullable=False),
        sa.Column("forbidden_answer_points", sa.JSON(), nullable=False),
        sa.Column("expected_behavior", sa.String(length=32), nullable=True),
    )

    # -- audit_events ----------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("event_id", GUID(), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_audit_events_user",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])


def downgrade() -> None:
    # Drop in reverse order so we never violate a foreign key.
    op.drop_index("ix_audit_events_timestamp", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_table("evaluation_cases")
    op.drop_index("ix_evaluation_runs_suite_name", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")

    op.drop_table("answer_cache")

    op.drop_index("ix_retrieved_evidence_message_id", table_name="retrieved_evidence")
    op.drop_table("retrieved_evidence")

    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("sessions")

    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_table("exact_terms")

    op.drop_index("ix_chunks_product_area", table_name="chunks")
    op.drop_table("chunks")

    op.drop_index("ix_documents_product_area", table_name="documents")
    op.drop_index("ix_documents_source_name", table_name="documents")
    op.drop_table("documents")

    op.drop_table("index_versions")
    op.drop_table("users")
