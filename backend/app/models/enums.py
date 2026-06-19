"""Enumerations used across the data model.

These mirror the textual constraints described in
``docs/DATA_MODEL.md``. They are stored as ``VARCHAR`` columns (we
use ``StrEnum`` so the values are always strings) so the test suite
can run hermetically against SQLite.

On Postgres, migration ``0002_promote_strenum_to_native`` promotes
each of the 13 columns listed there to a native ``citevyn_<name>``
ENUM type. The ORM models intentionally keep declaring ``String``;
Postgres automatically coerces enum-typed values to and from their
textual representation, so application code is unaffected.
"""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    demo_user = "demo_user"
    admin = "admin"


class DocumentStatus(enum.StrEnum):
    active = "active"
    failed = "failed"
    deprecated = "deprecated"


class IndexStatus(enum.StrEnum):
    candidate = "candidate"
    active = "active"
    previous_good = "previous_good"
    failed = "failed"


class JobStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobStage(enum.StrEnum):
    fetching = "fetching"
    parsing = "parsing"
    chunking = "chunking"
    embedding = "embedding"
    indexing = "indexing"


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"


class RetrievalType(enum.StrEnum):
    exact = "exact"
    keyword = "keyword"
    vector = "vector"
    hybrid = "hybrid"


class EvaluationStatus(enum.StrEnum):
    running = "running"
    passed = "passed"
    failed = "failed"


class EvaluationBehavior(enum.StrEnum):
    answer = "answer"
    no_answer = "no_answer"
    unsupported = "unsupported"
    clarify = "clarify"


class TermType(enum.StrEnum):
    flag = "flag"
    command = "command"
    config_key = "config_key"
    model_name = "model_name"
    api_parameter = "api_parameter"
    error_message = "error_message"
    environment_variable = "environment_variable"
    file_name = "file_name"
    slash_command = "slash_command"


class AuditAction(enum.StrEnum):
    ask_question = "ask_question"
    trigger_ingestion = "trigger_ingestion"
    run_evaluation = "run_evaluation"
    promote_index = "promote_index"
    login = "login"
    admin_auth_failure = "admin_auth_failure"
    auth_failed = "auth_failed"
    rate_limited = "rate_limited"
    unsupported_query = "unsupported_query"
    ingestion_failed = "ingestion_failed"


class Confidence(enum.StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"
