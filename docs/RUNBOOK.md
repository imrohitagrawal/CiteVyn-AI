# Runbook — on-call operations

> **Audience:** on-call engineers. **Goal:** diagnose and recover
> the production deployment in under 10 minutes. If a step here
> doesn't work, escalate — do not improvise.

All commands assume you are on the production host with the repo
checked out at `~/citevyn/`. Adjust paths if your layout
differs.

---

## 0. TL;DR

```bash
# Health
curl -fsS https://citevyn.example.com/health || echo DEGRADED

# Logs
make logs

# Restart one service
docker compose -f infra/docker/docker-compose.yml --profile prod restart api

# Roll back a release
git checkout v0.1.0 && VERSION=v0.1.0 make refresh
```

---

## 1. Service map

| Container           | Role               | Port (host) | Restart policy  |
|---------------------|--------------------|-------------|-----------------|
| `citevyn-caddy`     | TLS / reverse proxy| 80, 443     | `unless-stopped`|
| `citevyn-api`       | FastAPI app        | (internal)  | `unless-stopped`|
| `citevyn-worker`    | Ingestion worker   | (none)      | `unless-stopped`|
| `citevyn-db`        | Postgres + pgvector| (none)      | `unless-stopped`|
| `citevyn-redis`     | Cache / rate-limit | (none)      | `unless-stopped`|

The api and worker share the same image family but different
CMDs; the api listens on the docker network, the worker is
headless. Caddy is the only public entry point.

---

## 2. Health checks

### 2.1 First-line: /health

```bash
curl -fsS https://citevyn.example.com/health
```

Expected: `{"status":"ok"}` with HTTP 200. **No database call** —
this is a pure liveness probe. If this fails, the api process is
down or Caddy is down.

### 2.2 Second-line: container state

```bash
docker compose -f infra/docker/docker-compose.yml --profile prod ps
```

All five services should be `running` (the `backup` profile is
not running by design). Look for `(health: starting)` or
`(unhealthy)` flags.

### 2.3 Third-line: per-service logs

```bash
docker compose -f infra/docker/docker-compose.yml --profile prod logs --tail=200 api
docker compose -f infra/docker/docker-compose.yml --profile prod logs --tail=200 worker
docker compose -f infra/docker/docker-compose.yml --profile prod logs --tail=200 caddy
```

Look for: stack traces, repeated 500s, repeated 502s (Caddy
upstream timeouts).

---

## 3. Common scenarios

### 3.1 /health returns 502 from Caddy

**Symptom:** `curl` returns 502; Caddy logs say
`dial tcp: lookup api on …: no such host`.

**Diagnosis:** The api container is down or stuck restarting.

```bash
docker compose -f infra/docker/docker-compose.yml --profile prod ps api
docker compose -f infra/docker/docker-compose.yml --profile prod logs --tail=200 api
```

**Fix:**

```bash
docker compose -f infra/docker/docker-compose.yml --profile prod restart api
```

If the container is crash-looping, check the bottom of the log
for the traceback. Common causes:
- Missing env var (`CITEVYN_ADMIN_API_KEY`, `CITEVYN_DATABASE_URL`).
- Postgres not yet healthy (`depends_on: db: service_healthy`
  usually catches this; if it doesn't, see §3.2).

### 3.2 Postgres won't start

**Symptom:** `docker compose ps db` shows `(unhealthy)` or
restarting. Logs show `FATAL: could not write to file …` or
`permission denied on /var/lib/postgresql/data`.

**Diagnosis:** Volume permissions. The named volume
`citevyn_pgdata` was created by a previous Postgres image
running as a different uid (often uid 999 in the pgvector base
image, vs. uid 70 inside the `postgres:16-alpine` family).

**Fix:** the volume's first init must be from a
`pgvector/pgvector:pg16` container. Re-create the volume only
as a last resort — it drops the database.

```bash
docker compose -f infra/docker/docker-compose.yml --profile prod stop db
docker compose -f infra/docker/docker-compose.yml --profile prod rm -f db
docker volume ls | grep citevyn_pgdata
# If the volume was initialised by a different image:
docker volume rm citevyn_pgdata
docker compose -f infra/docker/docker-compose.yml --profile prod up -d db
```

**WARNING:** the last `rm` drops the entire database. Only run
if the most recent backup is current. See [§4 Backup & restore](#4-backup--restore).

### 3.3 Rate limit returning 429 unexpectedly

**Symptom:** legitimate users get HTTP 429. Logs show
`X-RateLimit-Remaining: 0` for non-spammy clients.

**Diagnosis:** The sliding-window limit
(`CITEVYN_RATE_LIMIT_DEMO_USER_PER_HOUR` /
`CITEVYN_RATE_LIMIT_ADMIN_PER_HOUR`) is too low for the current
traffic. Or the window clock is wrong (NTP drift).

**Fix:** raise the limit in `infra/docker/.env` and refresh:

```bash
$EDITOR infra/docker/.env      # bump CITEVYN_RATE_LIMIT_DEMO_USER_PER_HOUR
make refresh
```

If the issue is a single user hammering the endpoint, find
them in the api logs and `grep` for their `X-API-Key`:

```bash
docker compose logs api | grep "user_id=alice" | tail -50
```

The 429 response includes `Retry-After` (seconds). Once the
window slides, the user regains quota.

### 3.4 Worker's `ingestion_jobs` queue is stuck

**Symptom:** `GET /v1/admin/jobs` shows jobs in `running` state
for more than 5 minutes. New jobs queue up.

**Diagnosis:** The worker process is alive but the running job
is wedged (e.g. the LLM provider timed out and the worker is
waiting on a stale HTTP connection).

**Fix:** Send the worker a SIGTERM; the signal handler drains
the in-flight job and exits. Compose restarts it automatically.

```bash
docker compose -f infra/docker/docker-compose.yml --profile prod restart worker
```

The wedged job will be marked `failed` on next startup (or by
the next worker's poll if `restart: on-failure` is configured
on the job row).

### 3.5 Caddy won't issue the certificate

**Symptom:** `curl https://citevyn.example.com/health` returns
"connection reset" or a 522 from Caddy. Caddy logs say
"acme: error presenting challenge".

**Diagnosis:** The ACME HTTP-01 challenge (port 80) is
unreachable from Let's Encrypt. Common causes:
- DNS for `CITEVYN_PUBLIC_HOST` doesn't resolve to this host.
- A firewall is blocking port 80.
- Another web server (nginx, Apache) is already on port 80.

**Fix:**

```bash
# Verify DNS
dig +short citevyn.example.com

# Verify port 80 is reachable from the internet
nc -z citevyn.example.com 80

# Verify nothing else is on port 80
ss -lntp | grep ':80 '
```

Once DNS and port 80 are clean, force Caddy to re-attempt the
challenge:

```bash
docker compose -f infra/docker/docker-compose.yml --profile prod exec caddy \
    caddy reload --config /etc/caddy/Caddyfile
```

The next request on :443 will trigger a new ACME attempt.

### 3.6 Database volume full

**Symptom:** Postgres logs `No space left on device`. The api
starts returning 500s on the first query.

**Diagnosis:** The host disk is full. The named volume
`citevyn_pgdata` lives in `/var/lib/docker/volumes/` by default.

**Fix:**

```bash
# See docker volume usage
docker system df -v

# If a stale container is keeping a deleted file alive
docker ps -a
# … and remove it:  docker rm <id>

# Long-term: enable log rotation on the host
$EDITOR /etc/docker/daemon.json
# Add:
#   { "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
# Then:  sudo systemctl restart docker
```

---

## 4. Backup & restore

### 4.1 Backups (operator)

```bash
make backup
```

This invokes the `backup` profile — a one-shot `postgres:16-alpine`
container that runs `pg_dump --format=custom` against the live
database and writes to `./backups/citevyn-<UTC>.dump`. Keep at
least 7 days of dumps; the script does not rotate.

To schedule nightly backups, add a cron job on the host:

```cron
# /etc/cron.d/citevyn-backup
0 3 * * *  cd /opt/citevyn && make backup >> /var/log/citevyn/backup.log 2>&1
```

### 4.2 Restore

```bash
# Stop the api and worker so they don't try to write during restore
docker compose -f infra/docker/docker-compose.yml --profile prod stop api worker

# Restore. The dump file is read from the host bind-mount.
make restore FILE=infra/docker/backups/citevyn-20260620T030000Z.dump

# Restart api + worker
docker compose -f infra/docker/docker-compose.yml --profile prod up -d api worker
```

The `restore` target runs `pg_restore --clean --if-exists` inside
the backup container. It drops and recreates the affected
tables; pre-existing data outside the dump is **not** lost
(pg_restore only touches objects present in the dump).

---

## 5. Release / rollback

### 5.1 Cut a new release (maintainer)

```bash
# 1. Bump version
$EDITOR backend/pyproject.toml        # version = "0.2.0"

# 2. Tag + push
git commit -am "chore: cut v0.2.0"
git tag -s v0.2.0 -m "v0.2.0 — production-ready"
git push --follow-tags
```

CI builds `citevyn/api:v0.2.0` and `citevyn/worker:v0.2.0`.

### 5.2 Roll forward

```bash
VERSION=v0.2.0 make refresh
```

This rebuilds locally, runs migrations, and brings the new
images up. Brief 502s on :443 are expected (~10s).

### 5.3 Roll back

```bash
git checkout v0.1.0                 # source tree at the previous tag
VERSION=v0.1.0 make refresh
```

The compose file re-builds the images from the old source. Migrations
that were forward-only in `v0.2.0` will NOT be rolled back — for
those, restore a backup (see §4.2). For pure application rollbacks
(no schema change), `make refresh` after the `git checkout` is
sufficient.

---

## 6. Emergency contacts

- **On-call rotation:** see the GitHub repo's team settings.
- **Cloud provider support:** see `infra/docker/.env` (no
  cloud-specific keys are checked in; the LLM provider and the
  Postgres host are both cloud-managed).
- **Escalation:** open a GitHub issue with the `incident` label
  if the on-call cannot resolve within 30 minutes.

---

## 7. Post-incident

After any user-visible incident:

1. Write a post-mortem in `docs/postmortems/YYYY-MM-DD-<slug>.md`.
   The first section is the timeline; the rest is "what went
   well / poorly / where we got lucky".
2. Open follow-up issues for each action item. The label
   `postmortem-action` links them to the post-mortem.
3. Update this runbook if the playbook is now wrong.
