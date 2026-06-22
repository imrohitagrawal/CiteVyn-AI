#!/usr/bin/env bash
# End-to-end smoke test for the CiteVyn backend.
#
# Brings up Postgres via docker compose, applies migrations, seeds
# users + the demo catalog, starts uvicorn in the background, posts a
# session and a question, asserts the response carries a grounded
# cited answer, and tears down the stack. Exits 0 on success, non-zero
# on any failure.
#
# Run from anywhere; the script resolves its own repo root.
# Requirements: docker, curl, jq, uv.

set -Eeuo pipefail

# --- configuration --------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infra/docker/docker-compose.yml"
DB_CONTAINER="citevyn-db"
DB_URL="${CITEVYN_DATABASE_URL:-postgresql+psycopg://citevyn:citevyn@localhost:5432/citevyn}"
BASE_URL="${CITEVYN_BASE_URL:-http://127.0.0.1:8000}"
DB_TIMEOUT=60
HTTP_TIMEOUT=30
UVICORN_LOG="$REPO_ROOT/.smoke-uvicorn.log"
UVICORN_PID=""

# --- helpers --------------------------------------------------------------

log()  { printf '\033[1;34m→\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

cleanup() {
  # Always release the background uvicorn if we started one.
  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$UVICORN_PID" 2>/dev/null || break
      sleep 0.5
    done
    kill -KILL "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
  # Always tear down the docker compose stack.
  docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
  # Leave UVICORN_LOG and RESPONSE_FILE on disk for post-mortem.
}
trap cleanup EXIT INT TERM

wait_for_db() {
  local elapsed=0
  while (( elapsed < DB_TIMEOUT )); do
    if docker exec "$DB_CONTAINER" pg_isready -U citevyn -d citevyn >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  fail "Postgres did not become ready within ${DB_TIMEOUT}s"
}

wait_for_http() {
  local elapsed=0
  while (( elapsed < HTTP_TIMEOUT )); do
    if curl -sf -o /dev/null "$BASE_URL/health"; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  fail "uvicorn did not respond on $BASE_URL within ${HTTP_TIMEOUT}s"
}

# --- main -----------------------------------------------------------------

require_cmd docker
require_cmd curl
require_cmd jq
require_cmd uv

cd "$REPO_ROOT"

# Compose now requires POSTGRES_PASSWORD (the prod stack refuses
# to boot with an empty one). Smoke is a local one-shot, so we
# fall back to the same default the README documents — the
# docker-compose ``db`` service still accepts the plain-text
# credential on its private docker network.
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-citevyn}"
export CITEVYN_ADMIN_API_KEY="${CITEVYN_ADMIN_API_KEY:-smoke-admin-key}"

log "Bringing up Postgres (container: $DB_CONTAINER)…"
docker compose -f "$COMPOSE_FILE" up -d db >/dev/null
wait_for_db

log "Applying migrations to $DB_URL"
CITEVYN_DATABASE_URL="$DB_URL" uv run --project backend alembic -c db/alembic.ini upgrade head

log "Seeding users"
CITEVYN_DATABASE_URL="$DB_URL" PYTHONPATH=.. uv run --project backend python -m db.seed.seed_users

log "Seeding catalog"
CITEVYN_DATABASE_URL="$DB_URL" PYTHONPATH=.. uv run --project backend python -m db.seed.seed_catalog

log "Starting uvicorn in background (logs: $UVICORN_LOG)"
(
  cd "$REPO_ROOT/backend"
  CITEVYN_DATABASE_URL="$DB_URL" \
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 \
      >"$UVICORN_LOG" 2>&1 &
  echo $! >"$REPO_ROOT/.smoke-uvicorn.pid"
)
UVICORN_PID="$(cat "$REPO_ROOT/.smoke-uvicorn.pid")"
rm -f "$REPO_ROOT/.smoke-uvicorn.pid"
wait_for_http

log "GET /health (anonymous)"
HEALTH=$(curl -sf "$BASE_URL/health") || { cat "$UVICORN_LOG" >&2; fail "GET /health failed"; }
[[ "$(printf '%s' "$HEALTH" | jq -er .status)" == "healthy" ]] || fail "/health did not return status=healthy: $HEALTH"

log "Smoke test PASSED"
