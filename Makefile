# CiteVyn AI — repo-root developer entry points.
#
# These targets wrap the cross-cutting commands needed to bring the
# stack up, apply migrations, seed demo data, run the API, and tear
# down. Every target is intentionally thin: the heavy lifting lives
# in backend scripts, db/seed/*.py, and infra/docker/docker-compose.yml.
#
# Variables you can override on the command line:
#   DB_URL  — SQLAlchemy URL (default points at the docker-compose db)
#   API_KEY — bearer token for /v1/* requests

SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker/docker-compose.yml
DB_URL ?= postgresql+psycopg://citevyn:citevyn@localhost:5432/citevyn
API_KEY ?= local-demo-key
export CITEVYN_DATABASE_URL := $(DB_URL)

.PHONY: help db-up db-down migrate seed demo stop smoke clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

db-up: ## Start Postgres + Redis (Redis is provisioned but not used in MVP)
	$(COMPOSE) up -d db
	@echo "Waiting for Postgres to accept connections…"
	@for i in $$(seq 1 60); do \
	  if docker exec citevyn-db pg_isready -U citevyn -d citevyn >/dev/null 2>&1; then \
	    echo "Postgres ready"; exit 0; \
	  fi; \
	  sleep 1; \
	done; \
	echo "Postgres did not become ready in 60s" >&2; exit 1

db-down: ## Stop the docker-compose stack
	$(COMPOSE) down

migrate: ## Apply Alembic migrations to head
	uv run --project backend alembic -c db/alembic.ini upgrade head

seed: ## Seed demo users + catalog (idempotent)
	uv run --project backend python -m db.seed.seed_users
	uv run --project backend python -m db.seed.seed_catalog

demo: db-up migrate seed ## Bring up db, migrate, seed (one-shot)
	@echo "Demo stack is up. Run 'make stop' to tear down."

stop: db-down ## Tear the demo stack down

smoke: ## Run end-to-end smoke (db-up + migrate + seed + uvicorn + curl + stop)
	bash scripts/smoke.sh

clean: ## Remove __pycache__ + .pytest_cache + .ruff_cache + .smoke-* artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .smoke-uvicorn.log .smoke-uvicorn.pid .smoke-last-response.json
