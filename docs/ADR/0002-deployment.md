# ADR 0002 — Production deployment topology

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** maintainers

## Context

CiteVyn's API and worker (slices 1–8) need a production deployment
topology that:

1. Serves the FastAPI app over HTTPS with a publicly trusted cert.
2. Runs the worker as a separate, headless process.
3. Survives container restarts (Postgres volume, Redis in-memory).
4. Rebuilds deterministically from the same source tree that
   passes CI.
5. Operates without Kubernetes — the MVP deploys onto a single
   host (or VM) managed via `docker compose`.

The previous state (slice 1) had no Docker artefacts and the API
was assumed to run under a manual `uv run uvicorn` invocation.

## Decision

Adopt a **`docker compose` profile-based topology** with three
top-level artefacts:

1. **`Dockerfile.api`** — multi-stage build (`ghcr.io/astral-sh/uv`
   builder → `python:3.12-slim-bookworm` runtime) that produces
   the API image. Runs as non-root `appuser` (uid 1001). CMD is
   `uvicorn app.main:app --host 0.0.0.0 --port 8000
   --proxy-headers --forwarded-allow-ips=* --access-log`.
2. **`Dockerfile.worker`** — same builder/runtime split but
   slimmer (no uvicorn / fastapi deps); CMD is `citevyn-worker`
   (the script entry-point defined in `pyproject.toml`).
3. **`Caddyfile`** — TLS termination, ACME HTTP-01 on :80,
   on-demand Let's Encrypt, reverse proxy to `api:8000`,
   OWASP-aligned security headers (`Strict-Transport-Security`,
   `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
   `Referrer-Policy: strict-origin-when-cross-origin`,
   `Permissions-Policy`, restrictive `Content-Security-Policy`).

`docker-compose.yml` exposes three profiles:

- **(none)** — `db` + `redis` only (local dev).
- **`prod`** — adds `api`, `worker`, `caddy` (full stack).
- **`backup`** — one-shot `postgres:16-alpine` container that
  runs `pg_dump` and writes to a bind-mounted `./backups/` dir.

Production env is **`infra/docker/prod.env.example`** (copied to
`.env` on the host). Operator entry points live under
`infra/docker/scripts/`:

- `deploy.sh` — cold start (migrations + seed + bring-up).
- `refresh.sh` — rebuild + re-deploy without data loss.
- `backup.sh` — wraps the `backup` profile.

A top-level **`Makefile`** exposes the same operator commands as
targets (`make deploy`, `make refresh`, `make logs`, `make backup`,
`make restore FILE=…`).

## Rationale

- **`docker compose` over Kubernetes.** The MVP doesn't need
  pod-level orchestration, autoscaling, or service mesh.
  Compose is already the dev entry point; reusing it for prod
  keeps the mental model identical. A future slice can migrate
  to Kubernetes without changing the application code.
- **Caddy over nginx + certbot.** Caddy issues certificates
  automatically (no `certbot renew` cron, no rate-limit
  bookkeeping). The Caddyfile is ~70 lines; the equivalent nginx
  config + shell scripts would be ~250. Caddy v2 is production-
  stable (used at large scale for years).
- **Multi-stage builds.** The builder stage uses `uv` so
  dependency resolution is deterministic against `uv.lock`. The
  runtime stage is a slim Python image with the venv + source
  copied in. Build context is bounded by `.dockerignore`.
- **Non-root containers.** uid 1001 across both images; no
  package manager or shell in the runtime layer. Defence in
  depth against container-escape vulnerabilities.
- **Profile separation.** Local dev (`db` only) doesn't pay the
  cost of building 2 GB of images. Production (`--profile prod`)
  pulls + builds them on the host running the workload.
- **Explicit prod env example.** Reduces "what env vars does
  prod need?" to a single `cp prod.env.example .env` step.

## Consequences

### Positive

- Single-command deploy (`make deploy`) and refresh
  (`make refresh`).
- TLS, security headers, and rate limiting work out of the box.
- Deterministic builds (uv.lock is pinned).
- Container security baseline (non-root, slim base, minimal
  attack surface).
- Backups are a one-shot compose run; restores are a single
  `pg_restore` command.

### Negative / trade-offs

- **Single-host SPOF.** Postgres is on the same host as the
  app. HA requires moving Postgres to a managed service
  (RDS / Cloud SQL) — out of scope for the MVP.
- **Compose is not a scheduler.** A host crash requires manual
  `docker compose up -d`. For the MVP this is acceptable; a
  systemd unit (or Kubernetes) would automate it.
- **ACME rate limits.** Let's Encrypt has a 50 cert / week
  rate limit per domain. The on-demand TLS config can hit this
  in a misconfigured rollout that re-requests every minute.
  Mitigation: cache the issued cert in the `caddy_data` volume.
- **No zero-downtime deploy.** `docker compose up -d` cycles the
  containers one at a time, so :443 briefly 502s. Acceptable
  for the MVP; a blue/green deploy would require a load
  balancer in front.

### Follow-ups

- **Slice 10**: move Postgres to a managed service.
- **Slice 11**: add a blue/green deploy (compose + healthcheck +
  staggered bring-up).
- **Slice 12**: add Sentry SDK + log shipping (e.g. Loki).

## References

- [`infra/docker/Dockerfile.api`](../../infra/docker/Dockerfile.api)
- [`infra/docker/Dockerfile.worker`](../../infra/docker/Dockerfile.worker)
- [`infra/docker/Caddyfile`](../../infra/docker/Caddyfile)
- [`infra/docker/docker-compose.yml`](../../infra/docker/docker-compose.yml)
- [`infra/docker/prod.env.example`](../../infra/docker/prod.env.example)
- [`docs/RUNBOOK.md`](../RUNBOOK.md)
- [`docs/SECURITY_MODEL.md`](../SECURITY_MODEL.md)
- ADR 0001 — [Core architecture](0001-core-architecture.md)