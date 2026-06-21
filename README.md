# CiteVyn AI

> **Citation-grounded Q&A** about Claude, Claude Code, Codex, and Gemini
> — built on FastAPI + Postgres + pgvector, deployed via Docker.

CiteVyn answers user questions by retrieving and quoting **official
documentation** verbatim. Every answer carries a citation; refusal is
treated as a feature, not a failure.

---

## 1. Status

| Component           | State         | Notes                                                       |
|---------------------|---------------|-------------------------------------------------------------|
| API (FastAPI)       | Production    | Async SQLAlchemy, strict pyright, zero lint findings        |
| Worker (ingestion)  | Production    | Long-running poll of `ingestion_jobs`; no public port       |
| Database            | Production    | Postgres 16 + pgvector (semantic search)                    |
| Cache / rate-limit  | Production    | Redis 7 sliding-window limiter (per-user, per-route)        |
| TLS termination     | Production    | Caddy v2 (auto-issued Let's Encrypt)                        |
| Frontend            | In development| React + Vite, served separately                             |
| Test coverage       | 361 passed    | pytest + httpx AsyncClient; postgres-marker opt-in          |
| CI                  | 2 jobs        | pytest + lint (SQLite), alembic + postgres integration      |

---

## 2. Features

- **Citation-backed answers.** Every claim links to a source chunk
  with a confidence score and policy marker. The API surfaces a
  public envelope (`refusal`, `fallback_used`, `cache_hit`) that
  downstream consumers can render without re-parsing.
- **Strict refusal.** Out-of-domain or low-confidence questions
  return a refusal envelope instead of a guessed answer. Refusal
  messages are configurable.
- **Two-stage ingestion.** Sources are discovered, chunked,
  embedded, and indexed under versioned `index_versions`; admin
  promotion gates which version serves live traffic.
- **Sliding-window rate limiting.** Per-user, per-route, with a
  Redis-backed atomic implementation that survives uvicorn
  multi-worker (no in-process state).
- **Operator-first observability.** Structured logs, request-ID
  propagation, `/health` (DB-free) and `/metrics` endpoints.

---

## 3. Quick start (local)

```bash
# 1. Clone
git clone https://github.com/imrohitagrawal/CiteVyn-AI.git
cd CiteVyn-AI

# 2. Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Bring up Postgres + Redis + apply migrations + seed demo data
make demo

# 4. Run the API on SQLite (no DB required)
cd backend && uv run uvicorn app.main:app --reload

# 5. Smoke test
curl -s http://localhost:8000/health
# Use whatever key matches your CITEVYN_DEMO_API_KEY. The
# .env.example ships ``local-demo-key`` as the local default.
curl -s -H "X-API-Key: $CITEVYN_DEMO_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"query":"How do I install Claude Code?"}' \
     http://localhost:8000/v1/ask | jq
```

`make demo` is the single command that brings up the local stack;
see [§4 Configuration](#4-configuration) for the env vars it
expects, and [§10 Local development](#10-local-development) for
the full workflow.

---

## 4. Configuration

All knobs live in environment variables (loaded from `.env` for
local dev, or passed via `docker compose --env-file` in production).
The full list is documented in [`.env.example`](.env.example); the
production subset lives in
[`infra/docker/prod.env.example`](infra/docker/prod.env.example).

| Var                              | Required        | Purpose                                           |
|----------------------------------|-----------------|---------------------------------------------------|
| `CITEVYN_DATABASE_URL`           | yes             | Async SQLAlchemy URL (Postgres or SQLite)         |
| `CITEVYN_DEMO_API_KEY`           | yes             | Bearer token for `/v1/*` demo routes              |
| `CITEVYN_ADMIN_API_KEY`          | yes             | Bearer token for `/v1/admin/*` and ingestion      |
| `CITEVYN_REDIS_URL`              | recommended     | Enables the Redis rate limiter (production)       |
| `CITEVYN_LLM_PROVIDER`           | optional        | `stub` (default) or `anthropic`                   |
| `CITEVYN_LLM_API_KEY`            | if `anthropic`  | Live answer generation                            |
| `CITEVYN_LLM_MODEL`              | if `anthropic`  | Model id, e.g. `claude-opus-4-8`                  |
| `CITEVYN_RATE_LIMIT_*`           | optional        | Sliding-window knobs; defaults are production-safe|

**Never commit a real `.env`.** The repo `.gitignore` rejects
`.env*` except `.env.example`.

---

## 5. Architecture (5 minutes)

```
┌─────────┐    HTTPS    ┌──────────┐     SQL     ┌──────────┐
│ Browser ├────────────►│  Caddy   ├────────────►│   API    │
│  / curl │             │ (TLS+ACL)│             │ (FastAPI)│
└─────────┘             └────┬─────┘             └────┬─────┘
                             │                       │ asyncpg
                             │                       ▼
                             │                ┌──────────────┐
                             │                │  PostgreSQL  │
                             │                │  + pgvector  │
                             │                └──────┬───────┘
                             │                       │
                             │                ┌──────┴───────┐
                             │                │    Redis     │
                             │                │ (rate-limit, │
                             │                │  future cache)│
                             │                └──────────────┘
                             │
                       ┌─────┴──────┐
                       │   Worker   │  ◄── polls ingestion_jobs
                       │ (citevyn-  │      emits chunks to Postgres
                       │  worker)   │      + embeddings to pgvector
                       └────────────┘
```

- **API** ([`backend/app/`](backend/app)) — FastAPI service. Owns
  HTTP I/O, auth, rate-limiting, retrieval, answer composition.
- **Worker** ([`backend/app/worker/`](backend/app/worker)) —
  Long-running consumer for the `ingestion_jobs` queue. Same image
  family as the API; different `CMD` so the worker is headless.
- **Caddy** ([`infra/docker/Caddyfile`](infra/docker/Caddyfile)) —
  TLS termination, ACME, security headers, reverse proxy.
- **Postgres + pgvector** — source of truth (chunks, embeddings,
  jobs, audits). Vector index uses `pgvector`'s HNSW.
- **Redis** — sliding-window rate limiter (mandatory for
  multi-worker uvicorn); future answer-cache layer.

For the deep-dive, see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/ADR/0001-core-architecture.md`](docs/ADR/0001-core-architecture.md).
This slice adds [`docs/ADR/0002-deployment.md`](docs/ADR/0002-deployment.md).

---

## 6. Repository layout

```
CiteVyn-AI/
├── backend/                # Python service (FastAPI + worker)
│   ├── app/                # Runtime code
│   │   ├── api/            # HTTP routes
│   │   ├── core/           # Config, auth, rate-limit, redis client
│   │   ├── db/             # Models + session
│   │   ├── ingestion/      # Source discovery, chunking, embedding
│   │   ├── llm/            # Provider abstraction (stub + anthropic)
│   │   ├── retrieval/      # Hybrid search (pgvector + lexical)
│   │   ├── worker/         # citevyn-worker entry point + loop
│   │   └── main.py         # FastAPI app, lifespan, router wiring
│   ├── tests/              # 361 tests; pytest-asyncio; in-memory SQLite
│   ├── pyproject.toml      # uv-managed; ruff + pyright strict
│   └── uv.lock
├── db/                     # Alembic migrations (single source of truth)
├── docs/                   # ADRs, API spec, data model, runbook
├── frontend/               # React + Vite (in development)
├── infra/
│   └── docker/             # Dockerfiles, Caddyfile, compose, scripts
│       ├── Dockerfile.api
│       ├── Dockerfile.worker
│       ├── Caddyfile
│       ├── docker-compose.yml
│       ├── prod.env.example
│       ├── initdb.d/
│       ├── scripts/        # deploy.sh, refresh.sh, backup.sh
│       └── backups/        # pg_dump output (gitignored)
├── scripts/                # Repo-root helpers (smoke.sh, install-skills.sh)
├── .github/                # CI workflows, dependabot, release notes
├── .env.example            # Local env template
└── Makefile                # Single entry point for dev + operator
```

---

## 7. Production deployment (operator)

```bash
# 1. On the host, prepare the env file
cd infra/docker
cp prod.env.example .env
$EDITOR .env                       # set POSTGRES_PASSWORD, CITEVYN_ADMIN_API_KEY, CITEVYN_LLM_API_KEY

# 2. First-time cold start (creates db volume, runs migrations, seeds admin)
make deploy

# 3. Subsequent updates (rebuild + re-deploy, no data loss)
make refresh

# 4. Tail logs
make logs

# 5. Backup
make backup                        # writes infra/docker/backups/citevyn-<UTC>.dump
```

DNS for `CITEVYN_PUBLIC_HOST` must point at the host **before** the
first request hits :443 — Caddy's on-demand TLS will issue a
Let's Encrypt cert the first time the host is requested.

Full details: [`docs/RUNBOOK.md`](docs/RUNBOOK.md) and
[`docs/ADR/0002-deployment.md`](docs/ADR/0002-deployment.md).

---

## 8. HTTP API

| Endpoint                    | Auth   | Purpose                                       |
|-----------------------------|--------|-----------------------------------------------|
| `GET  /health`              | none   | DB-free liveness probe                        |
| `GET  /metrics`             | none   | Prometheus-format counters / histograms       |
| `POST /v1/ask`              | demo   | Citation-backed Q&A                            |
| `POST /v1/admin/ingest`     | admin  | Enqueue an ingestion job                      |
| `POST /v1/admin/promote`    | admin  | Promote an `index_version` to live            |
| `GET  /v1/admin/jobs`       | admin  | List recent ingestion jobs                    |
| `GET  /v1/admin/indexes`    | admin  | List `index_versions`                         |

Reference: [`docs/API_SPEC.md`](docs/API_SPEC.md). The request
shape, refusal envelope, and rate-limit headers are normative.

---

## 9. Security model

- **Bearer-token auth.** Two keys (`demo`, `admin`) — never shared
  in production. Tokens are read from env, never logged.
- **Production headers** (set by Caddy): HSTS, X-Frame-Options,
  X-Content-Type-Options, Referrer-Policy, Permissions-Policy,
  restrictive CSP. The API never sets cookies.
- **Rate limiting.** Sliding-window (Redis) with two quotas:
  `demo_user` (default 30/h) and `admin` (default 1000/h). The
  429 response includes `Retry-After`.
- **Containers run as non-root** (uid 1001). The api process has
  no shell, no package manager — minimal attack surface.
- **Secret hygiene.** `.env` and `infra/docker/.env` are
  git-ignored; the example files contain only placeholders.

Full threat model: [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

---

## 10. Local development

The single most useful command is `make demo`. It brings up the
docker-compose `db` + `redis` services, waits for Postgres to
accept connections, applies alembic migrations, and seeds the demo
catalog.

```bash
make demo          # one-shot stack bring-up
make test          # 361 tests, no DB needed
make smoke         # end-to-end curl against a real uvicorn
make verify        # lint + typecheck + test (the pre-merge gate)
make db-down       # tear down the stack (keeps volumes)
```

If you'd rather run uvicorn outside Docker (faster reloads):

```bash
cd backend
uv sync                       # resolves + creates .venv
uv run uvicorn app.main:app --reload --port 8000
```

For the worker:

```bash
cd backend
uv run citevyn-worker         # polls ingestion_jobs forever
```

`make test` excludes the `postgres` marker; `make test-pg` runs
the opt-in integration tests against a real Postgres if you set
`CITEVYN_PG_TEST_URL`.

---

## 11. Testing

- **Unit + integration** — `pytest` + `pytest-asyncio` against an
  in-memory SQLite engine; no external services required.
- **Rate-limit tests** — `fakeredis` mocks the Redis client so the
  sliding-window logic is exercised in-process.
- **Postgres tests** — opt-in via the `postgres` marker; require
  a live Postgres + pgvector. Run only in CI or pre-release.
- **Smoke** — `scripts/smoke.sh` boots a real uvicorn against
  SQLite, hits `/v1/ask` end-to-end, and tears down.

Test strategy: [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md).

---

## 12. CI

The repo runs four GitHub Actions jobs on every push to `main` and
on every PR:

| Job                     | What it does                                          |
|-------------------------|-------------------------------------------------------|
| `lint`                  | `ruff check` + `ruff format --check`                 |
| `typecheck`             | `pyright --strict`                                    |
| `tests`                 | `pytest -m "not postgres"` (sqlite)                  |
| `postgres-migrations`   | Boots a real Postgres, runs alembic upgrade head,    |
|                         | then runs the `postgres` marker tests                |
| `quality-gate`          | Reusable workflow from the `.github` meta-repo:     |
|                         | ruff + pyright + pytest + bandit + gitleaks +        |
|                         | semgrep + pip-audit. Runs on every PR.               |

Releases are cut via the `.github/workflows/release.yml` workflow
on version tags; see [§14 Release process](#14-release-process).

---

## 13. Release process

```bash
# 1. Bump the version in backend/pyproject.toml
$EDITOR backend/pyproject.toml        # version = "0.2.0"

# 2. Commit + tag
git commit -am "chore: cut v0.2.0"
git tag -s v0.2.0 -m "v0.2.0 — production-ready"
git push --follow-tags

# 3. CI builds images (citevyn/api:v0.2.0, citevyn/worker:v0.2.0)
#    and opens a draft release on GitHub.
```

Operator flow once the release is published:

```bash
VERSION=v0.2.0 make refresh          # pulls the new tag, rolls containers
```

Full template + changelog format: [`.github/RELEASE.md`](.github/RELEASE.md).

---

## 14. Observability

- **Structured logs** (JSON) with `request_id`, `user_role`,
  `route`, `status`, `latency_ms`. Propagated to the worker via
  the `X-Request-ID` header.
- **Metrics** at `/metrics` (Prometheus format). Counters cover
  asks, refusals, cache hits, embedding latency; histograms cover
  retrieval and answer latency.
- **Health** at `/health` (DB-free). DB-touching readiness is
  included as a separate `/ready` (worker only).
- **Sentry** — drop-in compatible via `SENTRY_DSN` env (not
  shipped by default; see `docs/OBSERVABILITY.md`).

---

## 15. Contributing

We welcome PRs. Before opening one, please read
[`CONTRIBUTING.md`](CONTRIBUTING.md) and the
[security policy](SECURITY.md).

- **Commits** — Conventional Commits (`feat:`, `fix:`, `chore:`).
  PR titles follow the same scheme.
- **Pre-merge gate** — `make verify` must be green on your
  machine. CI re-runs the same set.
- **ADRs** — Any non-trivial architecture decision gets a new
  file under `docs/ADR/` (next number, e.g. `0003-…`).
- **Tests** — New code = new test. Refactors that change
  observable behavior should update the relevant slice's smoke.

License: see [LICENSE](LICENSE).

---

## Appendix: documentation index

- [`docs/PRD.md`](docs/PRD.md) — product requirements
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system map
- [`docs/ADR/0001-core-architecture.md`](docs/ADR/0001-core-architecture.md)
- [`docs/ADR/0002-deployment.md`](docs/ADR/0002-deployment.md)
- [`docs/API_SPEC.md`](docs/API_SPEC.md) — HTTP contract
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — tables + relations
- [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)
- [`docs/OBSERVABILITY.md`](docs/OBSERVABILITY.md)
- [`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md)
- [`docs/RELEASE_PLAN.md`](docs/RELEASE_PLAN.md)
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — on-call playbook
- [`CHANGELOG`](CHANGELOG) (auto-generated by release workflow)