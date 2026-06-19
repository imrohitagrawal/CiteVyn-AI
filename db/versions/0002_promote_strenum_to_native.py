"""promote strenum columns to native postgres enums

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-18 00:00:00

Promotes the 13 ``String(32|64)`` columns backed by ``StrEnum`` in
``backend/app/models/enums.py`` to native PostgreSQL ``ENUM`` types.

Design notes
------------
* The ORM models are intentionally **not** changed: every affected
  column stays declared as ``String(32)`` / ``String(64)`` so SQLite
  keeps working unchanged (SQLite has no native ENUM type and we want
  the test suite to remain hermetic).
* The upgrade is a no-op on SQLite; every step is guarded by
  ``connection.dialect.name == "postgresql"``.
* ENUM types are namespaced with the ``citevyn_`` prefix to avoid
  colliding with any user-defined types in the destination schema.
* Each ``CREATE TYPE`` uses a ``DO $$ … EXCEPTION WHEN
  duplicate_object`` block so re-running the upgrade after a
  downgrade is safe (Postgres has no ``CREATE TYPE … IF NOT EXISTS``
  on versions < 14 in the form we need; the DO block is portable).

Columns promoted
----------------
users.role                       -> citevyn_userrole
audit_events.role                -> citevyn_userrole        (nullable)
index_versions.status            -> citevyn_indexstatus
documents.status                 -> citevyn_documentstatus
ingestion_jobs.status            -> citevyn_jobstatus
ingestion_jobs.stage             -> citevyn_jobstage
messages.role                    -> citevyn_messagerole
retrieved_evidence.retrieval_type-> citevyn_retrievaltype
answer_cache.confidence          -> citevyn_confidence
evaluation_cases.expected_behavior
                                 -> citevyn_evaluationbehavior  (nullable)
evaluation_runs.status           -> citevyn_evaluationstatus
exact_terms.term_type            -> citevyn_termtype
audit_events.action              -> citevyn_auditaction

Downgrade
---------
The reverse casts each column back to ``VARCHAR(<original length>)``
and drops the ``citevyn_*`` types. Existing data is preserved because
each enum value already equals its textual representation.
"""

from collections.abc import Sequence
from pathlib import Path
import sys

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Re-use the same sys.path tweak as 0001 so we import the same
# Python objects (StrEnum values, GUID) the application uses.
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.models.enums import (  # noqa: E402
    AuditAction,
    Confidence,
    DocumentStatus,
    EvaluationBehavior,
    EvaluationStatus,
    IndexStatus,
    JobStage,
    JobStatus,
    MessageRole,
    RetrievalType,
    TermType,
    UserRole,
)

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (StrEnum class, postgres type name, [(table, column, varchar_length), ...])
def _enum_targets() -> list[
    tuple[type[sa.Enum], str, list[tuple[str, str, int]]]
]:
    return [
        (UserRole, "citevyn_userrole", [
            ("users", "role", 32),
            ("audit_events", "role", 32),
        ]),
        (DocumentStatus, "citevyn_documentstatus", [
            ("documents", "status", 32),
        ]),
        (IndexStatus, "citevyn_indexstatus", [
            ("index_versions", "status", 32),
        ]),
        (JobStatus, "citevyn_jobstatus", [
            ("ingestion_jobs", "status", 32),
        ]),
        (JobStage, "citevyn_jobstage", [
            ("ingestion_jobs", "stage", 32),
        ]),
        (MessageRole, "citevyn_messagerole", [
            ("messages", "role", 32),
        ]),
        (RetrievalType, "citevyn_retrievaltype", [
            ("retrieved_evidence", "retrieval_type", 32),
        ]),
        (Confidence, "citevyn_confidence", [
            ("answer_cache", "confidence", 32),
        ]),
        (EvaluationBehavior, "citevyn_evaluationbehavior", [
            ("evaluation_cases", "expected_behavior", 32),
        ]),
        (EvaluationStatus, "citevyn_evaluationstatus", [
            ("evaluation_runs", "status", 32),
        ]),
        (TermType, "citevyn_termtype", [
            ("exact_terms", "term_type", 32),
        ]),
        (AuditAction, "citevyn_auditaction", [
            ("audit_events", "action", 64),
        ]),
    ]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for enum_cls, type_name, _columns in _enum_targets():
        values = ", ".join(f"'{m.value}'" for m in enum_cls)
        op.execute(
            f"DO $$ BEGIN "
            f"CREATE TYPE {type_name} AS ENUM ({values}); "
            f"EXCEPTION WHEN duplicate_object THEN null; "
            f"END $$;"
        )

    for enum_cls, type_name, columns in _enum_targets():
        enum_obj = postgresql.ENUM(
            *(m.value for m in enum_cls),
            name=type_name,
            create_type=False,
        )
        for table, col, length in columns:
            op.alter_column(
                table,
                col,
                type_=enum_obj,
                existing_type=sa.String(length),
                postgresql_using=f"{col}::text::{type_name}",
            )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # Reverse the column alters first — you cannot drop a type that a
    # column still depends on.
    for enum_cls, type_name, columns in reversed(_enum_targets()):
        enum_obj = postgresql.ENUM(
            *(m.value for m in enum_cls),
            name=type_name,
            create_type=False,
        )
        for table, col, length in columns:
            op.alter_column(
                table,
                col,
                type_=sa.String(length),
                existing_type=enum_obj,
                postgresql_using=f"{col}::text",
            )

    for _enum_cls, type_name, _columns in reversed(_enum_targets()):
        op.execute(f"DROP TYPE IF EXISTS {type_name}")
