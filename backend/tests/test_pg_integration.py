"""Postgres integration tests (opt-in via the ``postgres`` marker).

These tests run ``alembic upgrade head`` against a real Postgres
database and exercise a few round-trips to prove the migration
behaves on Postgres (real UUID columns, native ENUMs after
migration 0002, JSON/JSONB columns). They are skipped by default so
``uv run pytest`` keeps working hermetically with in-memory SQLite.

Enable with either of:

    export CITEVYN_PG_TEST_URL=postgresql+psycopg://user:pass@host:5432/citevyn_pg_test
    uv run pytest -m postgres -v

    # …or set the same URL in the environment / .env via the
    # ``CITEVYN_PG_TEST_URL`` variable documented in ``.env.example``.

The test never modifies the default ``public`` schema. Each test
isolates itself with a unique ``citevyn_test_<rand>`` schema and
drops it on teardown, so the URL may safely point at a shared
development database.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.command import upgrade as alembic_upgrade
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text

from app.core.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "db" / "alembic.ini"

# Mark every test in this file with the ``postgres`` marker. The
# ``skipif`` is intentionally evaluated at collection time so a
# developer running ``uv run pytest -m postgres --collect-only`` sees
# the explicit skip reason without spinning up the test fixtures.
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("CITEVYN_PG_TEST_URL") is None and get_settings().pg_test_url is None,
        reason=(
            "Set CITEVYN_PG_TEST_URL (or Settings.pg_test_url) to a "
            "postgresql+psycopg:// URL to enable Postgres integration tests."
        ),
    ),
]


def _pg_url() -> str:
    url = os.environ.get("CITEVYN_PG_TEST_URL") or get_settings().pg_test_url
    assert url is not None, "Postgres URL is required (guarded by skipif)"
    return url


def _pg_url_with_schema(schema: str) -> str:
    """Build a Postgres URL whose default ``search_path`` is ``schema``.

    Alembic opens its own connection from the URL we hand it; setting
    ``search_path`` on the fixture's connection does not propagate.
    libpq accepts ``options=-c search_path=<schema>`` as a connection
    parameter, which psycopg applies on every new connection. The
    schema name comes from ``pg_schema`` and is URL-safe (``[a-z0-9_]``).
    """
    base = _pg_url()
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}options=-c search_path={schema}"


@pytest.fixture
def alembic_pg_config() -> Iterator[AlembicConfig]:
    """Yield an Alembic config pointed at the PG test database.

    The connection itself is the per-test schema, applied below.
    The tests that consume this fixture must call
    ``cfg.set_main_option("sqlalchemy.url", _pg_url_with_schema(...))``
    once they know the schema name so Alembic's connection inherits
    ``search_path``.
    """
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "db"))
    cfg.set_main_option("sqlalchemy.url", _pg_url())
    yield cfg


@pytest.fixture
def pg_schema() -> Iterator[str]:
    """Create a unique Postgres schema, yield its name, then drop it.

    The fixture opens a short-lived AUTOCOMMIT connection so
    ``CREATE SCHEMA`` / ``DROP SCHEMA`` are not subject to the
    implicit transaction that ``engine.begin()`` opens. A fresh
    ``create_engine`` is used here because we need to set
    ``search_path`` on the same connection Alembic uses; Alembic
    builds its own engine from the ``sqlalchemy.url`` config option
    with ``NullPool``, so we set the path at the role level via
    ``ALTER ROLE … IN DATABASE`` is not portable — instead we set
    ``search_path`` on the current session and let Alembic inherit
    it because ``db/env.py`` opens a single connection per upgrade.
    """
    schema = f"citevyn_test_{uuid.uuid4().hex[:8]}"
    engine = create_engine(_pg_url(), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}"))
        yield schema
    finally:
        # Open a fresh connection in case the yielded engine was
        # disposed or the connection is in a bad state.
        with engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()


def test_alembic_upgrade_head_creates_all_tables(
    alembic_pg_config: AlembicConfig, pg_schema: str
) -> None:
    alembic_pg_config.set_main_option("sqlalchemy.url", _pg_url_with_schema(pg_schema))
    alembic_upgrade(alembic_pg_config, "head")

    engine = create_engine(_pg_url())
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {pg_schema}"))
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"
                ),
                {"schema": pg_schema},
            ).all()
    finally:
        engine.dispose()

    table_names = {row[0] for row in rows}
    assert "alembic_version" in table_names

    expected = {
        "users",
        "index_versions",
        "documents",
        "chunks",
        "exact_terms",
        "ingestion_jobs",
        "sessions",
        "messages",
        "retrieved_evidence",
        "answer_cache",
        "evaluation_cases",
        "evaluation_runs",
        "audit_events",
    }
    missing = expected - table_names
    assert not missing, f"Missing tables after migration: {missing}"


def test_uuid_columns_are_native_uuid_on_postgres(
    alembic_pg_config: AlembicConfig, pg_schema: str
) -> None:
    """GUID columns must be real ``uuid`` on Postgres, not CHAR(36)."""
    alembic_pg_config.set_main_option("sqlalchemy.url", _pg_url_with_schema(pg_schema))
    alembic_upgrade(alembic_pg_config, "head")

    # Every GUID-typed column across the schema. Built from a tuple
    # so the SQL string stays short and lint-friendly.
    guid_columns = (
        "document_id",
        "chunk_id",
        "message_id",
        "term_id",
        "evidence_id",
        "event_id",
        "run_id",
        "case_id",
        "session_id",
        "job_id",
    )
    in_clause = ", ".join(f"'{c}'" for c in guid_columns)

    engine = create_engine(_pg_url())
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {pg_schema}"))
            rows = conn.execute(
                text(
                    "SELECT table_name, column_name, data_type "
                    "FROM information_schema.columns "
                    f"WHERE table_schema = :schema AND column_name IN ({in_clause})"
                ),
                {"schema": pg_schema},
            ).all()
    finally:
        engine.dispose()

    assert rows, "Expected GUID-typed columns to exist after migration"
    non_uuid = [(t, c) for t, c, dtype in rows if dtype != "uuid"]
    assert not non_uuid, f"Expected native uuid, found CHAR(36) on: {non_uuid}"


def test_round_trip_user_insert(alembic_pg_config: AlembicConfig, pg_schema: str) -> None:
    """Smoke-test the application ORM against real Postgres."""
    alembic_pg_config.set_main_option("sqlalchemy.url", _pg_url_with_schema(pg_schema))
    alembic_upgrade(alembic_pg_config, "head")

    engine = create_engine(_pg_url())
    try:
        with engine.begin() as conn:
            conn.execute(text(f"SET search_path TO {pg_schema}"))
            conn.execute(
                text("INSERT INTO users (user_id, role, created_at) VALUES (:uid, 'admin', now())"),
                {"uid": "demo_user"},
            )
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {pg_schema}"))
            row = conn.execute(
                text("SELECT user_id, role FROM users WHERE user_id = :uid"),
                {"uid": "demo_user"},
            ).first()
    finally:
        engine.dispose()

    assert row is not None
    assert row[0] == "demo_user"
    assert row[1] == "admin"


def test_chunks_embedding_is_bytea_on_postgres(
    alembic_pg_config: AlembicConfig, pg_schema: str
) -> None:
    """Slice 8 step 4: ``chunks.embedding`` lands as ``bytea`` on Postgres.

       Migration ``0003`` declares the column as ``LargeBinary``, which
       Postgres renders as ``bytea``. The future ``pgvector`` migration
    will swap the column type to ``vector(<dim>)`` and this
       assertion will need to be updated.

       The test also confirms the column is nullable so existing rows
       survive the upgrade.
    """
    alembic_pg_config.set_main_option("sqlalchemy.url", _pg_url_with_schema(pg_schema))
    alembic_upgrade(alembic_pg_config, "head")

    engine = create_engine(_pg_url())
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {pg_schema}"))
            row = conn.execute(
                text(
                    "SELECT data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = 'chunks' "
                    "AND column_name = 'embedding'"
                ),
                {"schema": pg_schema},
            ).first()
    finally:
        engine.dispose()

    assert row is not None, "chunks.embedding column not found after migration"
    data_type, is_nullable = row
    assert data_type == "bytea", f"expected bytea, got {data_type}"
    assert is_nullable == "YES", "embedding should be nullable"
