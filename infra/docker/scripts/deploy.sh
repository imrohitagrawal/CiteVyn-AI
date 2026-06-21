#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# deploy.sh — first-time / cold-start bring-up of the production stack.
#
# Use ``refresh.sh`` for subsequent updates. Use this script the very
# first time you wire up a host, or when you need to re-create the
# database volume (e.g. after a clean-up).
#
# What it does:
#   1. Builds the API + worker images.
#   2. Starts Postgres + Redis.
#   3. Waits for both to be healthy.
#   4. Runs the full alembic migration chain.
#   5. Seeds the initial admin user (if not already present).
#   6. Brings up the api, worker, caddy stack.
#
# Usage:
#   VERSION=v1.2.3 ./scripts/deploy.sh
#
# Prereqs:
#   - .env exists with all required values
#   - DNS for CITEVYN_PUBLIC_HOST points at this host's public IP
#   - ports 80 and 443 are reachable from the internet
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${COMPOSE_DIR}"

if [[ ! -f .env ]]; then
    echo "error: .env not found at ${COMPOSE_DIR}/.env" >&2
    exit 1
fi

VERSION="${VERSION:-dev}"
export VERSION

echo "==> deploy.sh: bringing up the database + cache layer"
docker compose up -d db redis

echo "==> waiting for Postgres to accept connections (max 60s)"
for _ in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U citevyn -d citevyn >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo "==> running alembic migrations"
docker compose \
    --profile prod \
    run \
    --rm \
    --no-deps \
    api \
    alembic \
        --config /db/alembic.ini \
        --sqlalchemy-url "${CITEVYN_DATABASE_URL:?CITEVYN_DATABASE_URL must be set in .env}" \
    upgrade head

echo "==> seeding the initial admin user (idempotent)"
# The seed module lives at ``db/seed/seed_users.py`` (not under
# ``app/``); the api image has ``db/`` mounted at ``/db`` and
# ``PYTHONPATH=/db`` so ``python -m db.seed.seed_users`` resolves.
# ``seed_users.seed()`` is idempotent: existing rows are left
# untouched, so re-running this script on a populated database
# is a no-op.
docker compose \
    --profile prod \
    run \
    --rm \
    --no-deps \
    api \
    python -m db.seed.seed_users

echo "==> verifying the admin row landed"
# Sanity-check that the seed actually wrote a row (the script
# exits non-zero if the seed module's commit failed silently).
ADMIN_COUNT=$(docker compose exec -T db psql -U citevyn -d citevyn -tAc \
    "SELECT count(*) FROM users WHERE user_id = 'admin';")
if [[ "${ADMIN_COUNT}" != "1" ]]; then
    echo "error: seed step did not create the admin user (count=${ADMIN_COUNT})" >&2
    echo "       inspect: docker compose exec db psql -U citevyn -d citevyn -c '\\dt'" >&2
    exit 1
fi

echo "==> bringing up api + worker + caddy"
docker compose --profile prod up -d

echo "==> waiting for /health (max 60s)"
for _ in $(seq 1 30); do
    if curl --silent --fail http://localhost/health >/dev/null; then
        echo "==> healthy"
        echo "==> ACME cert will be issued lazily on the first :443 request"
        echo "==> tail logs with: docker compose --profile prod logs -f"
        exit 0
    fi
    sleep 2
done

echo "warning: /health did not return 200 within 60s" >&2
echo "         inspect with: docker compose --profile prod logs api" >&2
exit 1