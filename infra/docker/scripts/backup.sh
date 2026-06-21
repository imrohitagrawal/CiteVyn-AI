#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# backup.sh — on-demand Postgres dump to ./backups/.
#
# Wraps the one-shot ``backup`` profile container. Runs against the
# live database; the ``db`` service must be healthy first.
#
# Usage:
#   ./scripts/backup.sh
#
# The output file lands in ./backups/citevyn-<UTC timestamp>.dump.
# Restore with:
#   pg_restore --clean --if-exists --no-owner --no-privileges \
#       -h <host> -U citevyn -d citevyn ./backups/citevyn-<ts>.dump
# ────────────────────────────────────────────────────────────────────────────
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${COMPOSE_DIR}"

if [[ ! -f .env ]]; then
    echo "error: .env not found at ${COMPOSE_DIR}/.env" >&2
    exit 1
fi

mkdir -p ./backups

# The profile ``backup`` service is configured to dump and exit;
# ``docker compose run`` waits for the container to finish, so the
# script blocks until the dump is on disk.
docker compose --profile backup run --rm backup

echo
echo "==> dumps in ${COMPOSE_DIR}/backups/:"
ls -lh ./backups/ | tail -n +2