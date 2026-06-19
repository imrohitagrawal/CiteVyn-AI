"""Alembic environment.

Reads ``CITEVYN_DATABASE_URL`` from the environment, imports the SQLAlchemy
``Base.metadata`` from the backend package, and runs migrations online.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the backend package importable regardless of where Alembic is
# invoked from.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402,F401  -- import registers models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the database URL. The configuration file ships a placeholder;
# prefer ``CITEVYN_DATABASE_URL`` from the environment so developers
# and CI can switch engines without editing ``alembic.ini``. Tests may
# also set the URL directly on the ``Config`` object — honor that when
# present.
configured_url = config.get_main_option("sqlalchemy.url")
if configured_url and configured_url != "sqlite:///placeholder.db":
    database_url = configured_url
else:
    database_url = get_settings().database_url

config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def _sync_url(async_url: str) -> str:
    """Convert an async SQLAlchemy URL into the corresponding sync URL.

    Alembic itself only supports synchronous engines. The application
    uses ``postgresql+psycopg://`` and ``sqlite+aiosqlite://``; we map
    those to ``postgresql+psycopg://`` (psycopg is sync-capable) and
    ``sqlite:///`` respectively.
    """
    if async_url.startswith("sqlite+aiosqlite://"):
        return async_url.replace("sqlite+aiosqlite://", "sqlite:///", 1)
    return async_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=_sync_url(database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations to a live database connection."""
    # Re-read the URL through the sync adapter so the synchronous
    # engine Alembic requires is built correctly.
    config.set_main_option("sqlalchemy.url", _sync_url(database_url))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
