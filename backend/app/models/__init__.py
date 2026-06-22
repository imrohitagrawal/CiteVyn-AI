"""ORM models for CiteVyn Slice 2.

Importing this package registers every model with ``Base.metadata``,
which Alembic consults to autogenerate migrations.
"""

from app.models.answer_cache import AnswerCache
from app.models.audit_events import AuditEvent
from app.models.base import GUID, Base, PickledEmbedding, TimestampMixin
from app.models.chunks import Chunk
from app.models.documents import Document
from app.models.enums import (
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
from app.models.evaluation import EvaluationCase, EvaluationRun
from app.models.exact_terms import ExactTerm
from app.models.index_versions import IndexVersion
from app.models.ingestion_jobs import IngestionJob
from app.models.messages import Message
from app.models.retrieved_evidence import RetrievedEvidence
from app.models.sessions import Session
from app.models.users import User

__all__ = [
    "GUID",
    "AnswerCache",
    "AuditAction",
    "AuditEvent",
    "Base",
    "Chunk",
    "Confidence",
    "Document",
    "DocumentStatus",
    "EvaluationBehavior",
    "EvaluationCase",
    "EvaluationRun",
    "EvaluationStatus",
    "ExactTerm",
    "IndexStatus",
    "IndexVersion",
    "IngestionJob",
    "JobStage",
    "JobStatus",
    "Message",
    "MessageRole",
    "PickledEmbedding",
    "RetrievedEvidence",
    "RetrievalType",
    "Session",
    "TermType",
    "TimestampMixin",
    "User",
    "UserRole",
]
