# CiteVyn — Database

This directory holds Alembic migrations, seed scripts, and the
canonical schema for CiteVyn.

## Layout

```
db/
  alembic.ini          # Alembic configuration (URL is read from env)
  env.py               # Online/offline migration entry point
  script.py.mako       # Template for new revisions
  versions/            # Numbered migration files
  seed/                # Idempotent seed scripts
```

The SQLAlchemy models themselves live in `backend/app/models/` so the
backend and the migrations share a single `Base.metadata`.

## Environment

| Variable                 | Default                                              | Notes |
|--------------------------|------------------------------------------------------|-------|
| `CITEVYN_DATABASE_URL`   | `sqlite+aiosqlite:///./citevyn.db`                   | Async SQLAlchemy URL. For production use `postgresql+psycopg://user:pass@host:5432/dbname`. |

The driver prefix (`postgresql+psycopg` vs `sqlite+aiosqlite`) is
detected by `app.core.db.build_engine`. We also install the
`pgvector` Python package now so the dialect is registered; the
embedding column is added in a later migration.

## Common Commands

Run from the repository root unless noted.

```bash
# Apply all migrations (against whatever CITEVYN_DATABASE_URL points to)
uv run alembic -c db/alembic.ini upgrade head

# Roll back the most recent migration
uv run alembic -c db/alembic.ini downgrade -1

# Generate a new migration from model diffs
uv run alembic -c db/alembic.ini revision --autogenerate -m "describe the change"

# Show the current revision
uv run alembic -c db/alembic.ini current
```

`uv run` is used so the commands resolve the project's virtualenv. If
you are inside `backend/`, drop the `uv run` and use
`alembic -c ../db/alembic.ini ...`.

## Migrations in this Directory

* `0001_initial_schema.py` — initial tables for Slice 2. Dialect-agnostic;
  columns are `String(32|64)` so SQLite tests work unchanged.
* `0002_promote_strenum_to_native.py` — on Postgres only, promotes
  the 13 StrEnum-backed columns to native `citevyn_*` ENUM types.
  No-op on SQLite. The ORM models are intentionally unchanged.

## Local Development

A `docker-compose.yml` file lives at `infra/docker/docker-compose.yml`
and starts `postgres+pgvector` plus `redis`. See
[`infra/docker/README.md`](../infra/docker/README.md) (if present) or
the top-level `backend/README.md` for the full command sequence.

## Seed Data

`db/seed/seed_users.py` inserts the two MVP roles (`demo_user`,
`admin`) idempotently. Run after `upgrade head`:

```bash
uv run python -m db.seed.seed_users
```

The script is safe to re-run; it skips rows that already exist.
