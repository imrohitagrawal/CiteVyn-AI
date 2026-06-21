# CiteVyn AI — repo-root developer + operator entry points.
#
# Developer workflow:
#   make demo        — bring up the local stack (db + migrations + seed)
#   make lint        — ruff on backend/app + tests
#   make typecheck   — pyright on backend/app (strict)
#   make test        — pytest (excludes the ``postgres`` marker)
#   make smoke       — end-to-end curl against uvicorn on SQLite
#   make clean       — drop caches
#
# Production workflow (operator):
#   make deploy      — first-time cold start (see infra/docker/scripts/deploy.sh)
#   make refresh     — rebuild + re-deploy without losing data
#   make logs        — tail logs from api, worker, caddy
#   make backup      — pg_dump to ./backups/
#
# Variables you can override on the command line:
#   DB_URL     — SQLAlchemy URL for local alembic (default: docker-compose db)
#   VERSION    — image tag (default: dev); set from CI via git tag
#   PROFILE    — docker compose profile (default: prod)
#
# Heavy lifting lives in backend/, db/, infra/docker/, and scripts/.

SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker/docker-compose.yml
DB_URL ?= postgresql+psycopg://citevyn:citevyn@localhost:5432/citevyn
API_KEY ?= local-demo-key
VERSION ?= dev
PROFILE ?= prod
# NOTE: CITEVYN_DATABASE_URL is intentionally NOT exported globally
# because the ``test`` target runs against an in-memory SQLite
# (see ``backend/tests/conftest.py::_default_database_url``).
# Targets that need a real Postgres (``migrate``, ``seed``, ``db-up``,
# ``smoke``) set the variable on the command line they run.
export VERSION
export PROFILE

.PHONY: help db-up db-down migrate seed demo stop smoke clean lint typecheck test ci \
        build push deploy refresh logs backup restore

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ─────────────────────────── Code quality ───────────────────────────
lint: ## Run ruff over backend/app + tests (check only — fixes go in a separate commit)
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .

typecheck: ## Run pyright strict on backend/app
	cd backend && uv run pyright

test: ## Run the pytest suite (excludes the postgres marker; uses in-memory SQLite)
	cd backend && uv sync --group dev
	cd backend && env -u CITEVYN_DATABASE_URL uv run pytest -m "not postgres" -q

test-pg: ## Run the postgres-marked tests (requires CITEVYN_PG_TEST_URL)
	cd backend && uv run pytest -m postgres -q

# ─────────────────────────── Local development ───────────────────────────
db-up: ## Start Postgres + Redis via docker compose (no app containers)
	$(COMPOSE) up -d db redis
	@echo "Waiting for Postgres to accept connections…"
	@for i in $$(seq 1 60); do \
	  if docker exec citevyn-db pg_isready -U citevyn -d citevyn >/dev/null 2>&1; then \
	    echo "Postgres ready"; exit 0; \
	  fi; \
	  sleep 1; \
	done; \
	echo "Postgres did not become ready in 60s" >&2; exit 1

db-down: ## Stop the docker-compose db stack (keeps volumes)
	$(COMPOSE) down

db-reset: ## Destroy and recreate the database volume (DESTRUCTIVE; requires CONFIRM=yes)
	@if [[ "${CONFIRM:-}" != "yes" ]]; then \
	  echo "error: this drops the database volume (all data lost)" >&2; \
	  echo "       re-run with: make db-reset CONFIRM=yes" >&2; \
	  exit 2; \
	fi
	$(COMPOSE) down -v

migrate: ## Apply Alembic migrations to head against DB_URL
	CITEVYN_DATABASE_URL=$(DB_URL) uv run --project backend alembic -c db/alembic.ini upgrade head

seed: ## Seed demo users + catalog (idempotent)
	CITEVYN_DATABASE_URL=$(DB_URL) uv run --project backend python -m db.seed.seed_users
	CITEVYN_DATABASE_URL=$(DB_URL) uv run --project backend python -m db.seed.seed_catalog

demo: db-up migrate seed ## Bring up db, migrate, seed (one-shot)
	@echo "Demo stack is up. Run 'make stop' to tear down."

stop: db-down ## Tear the demo stack down

smoke: ## End-to-end smoke (db-up + migrate + seed + uvicorn + curl + stop)
	bash scripts/smoke.sh

clean: ## Remove __pycache__ + .pytest_cache + .ruff_cache + smoke artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .smoke-uvicorn.log .smoke-uvicorn.pid .smoke-last-response.json

# ─────────────────────────── Production build ───────────────────────────
build: ## Build the api + worker images (VERSION=tag to label)
	$(COMPOSE) --profile $(PROFILE) build --pull

push: ## Push the api + worker images to the configured registry
	$(COMPOSE) --profile $(PROFILE) push

# ─────────────────────────── Production deploy ───────────────────────────
deploy: ## First-time / cold-start deploy (run from infra/docker/.env host)
	./infra/docker/scripts/deploy.sh

refresh: ## Rebuild + re-deploy in place (no data loss)
	./infra/docker/scripts/refresh.sh

logs: ## Tail logs from api, worker, caddy
	$(COMPOSE) --profile $(PROFILE) logs -f --tail=100 api worker caddy

ps: ## Show running containers (prod profile)
	$(COMPOSE) --profile $(PROFILE) ps

backup: ## Dump the live database to ./backups/
	./infra/docker/scripts/backup.sh

restore: ## Restore a pg_dump file (usage: make restore FILE=path)
	@if [[ -z "$(FILE)" ]]; then echo "usage: make restore FILE=path/to/citevyn-*.dump" >&2; exit 2; fi
	@if [[ ! -f "$(FILE)" ]]; then echo "error: $(FILE) not found" >&2; exit 1; fi
	# Source the env file so docker compose + the backup container
	# can read POSTGRES_PASSWORD (the ``backup`` service has it
	# in env_file, which docker compose requires to be present
	# at run-time).
	@if [[ ! -f infra/docker/.env ]]; then echo "error: infra/docker/.env not found; copy prod.env.example first" >&2; exit 1; fi
	@set -a; . infra/docker/.env; set +a; \
	docker compose --profile backup run --rm \
		backup sh -c "pg_restore --clean --if-exists --no-owner --no-privileges \
			-h db -U citevyn -d citevyn < /dev/stdin" < $(FILE)

# ─────────────────────────── Convenience composites ───────────────────────────
# ``make ci`` is the deterministic gate the pr-quality workflow uses
# (lint + typecheck + test, hermetic SQLite). ``make verify`` is the
# developer-side equivalent with the same dependencies.
ci: lint typecheck test ## Deterministic CI gate used by .github/workflows/pr-quality.yml
	@echo "make ci: all checks passed"

verify: lint typecheck test ## Run the full pre-merge gate locally
