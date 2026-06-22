# Changelog

All notable changes to CiteVyn are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- 50-case golden evaluation suite under `tests/golden/cases/` plus a
  runner module that boots the FastAPI app against the in-memory
  SQLite seed and exercises the full public surface. Exposed via
  `make golden` (full run) and `make golden-smoke` (3-case sanity).
- Production guard: `Settings._reject_stub_llm_in_production` now
  rejects the Slice 9b router placeholder (`CITEVYN_LLM_PROVIDER=""`)
  in addition to `"stub"`. Two new unit tests
  (`test_settings_constructor_rejects_empty_llm_provider_in_production`,
  `test_settings_constructor_accepts_empty_llm_provider_in_development`)
  pin the contract.
- `docs/DEMO_CHECKLIST.md` — single source of truth for what the demo
  must demonstrate and the gate the team uses to declare the build
  "demo-ready".
- `scripts/refresh_sources.sh` — operator script that runs
  `make refresh` and pipes the new docs index through the same path
  the prod worker uses. The script is idempotent and refuses to run
  with an unset `CITEVYN_REDIS_URL` so a partial refresh cannot leave
  the index in a half-built state.
- `docs/DEPENDABOT_TRIAGE.md` and the `release-blocker` repo label so
  dependabot PRs touching rate-limit, security, or DB-migration code
  cannot be auto-merged.
- Frontend CI (`.github/workflows/frontend-ci.yml`) that builds the
  Vite bundle, runs ESLint, type-checks, and uploads the build output
  as a workflow artifact.

### Changed
- `Makefile` now lists `golden` and `golden-smoke` in the developer
  workflow header. The `make demo` target resolves `demo-frontend` so
  the chat UI comes up alongside the API.
- `README.md` §13 ("Demo Build Status") flips from amber to green once
  the golden suite is green on the cut commit. The badge link now
  points at the latest nightly run.

### Fixed
- `runner.py` (golden): the in-memory cache and the rate limiter were
  leaking state between cases. The runner now builds a fresh
  `TestClient` per case (configurable via
  `fresh_client_per_case=False`) and pins
  `CITEVYN_RATE_LIMIT_ENABLED=false` for the run.
- The `runner.py` CLI was wired to `--report-path` but the argparse
  flag is `--report`. Make targets corrected.

## [0.9.1] — 2026-05-12

### Fixed
- Slice 9.1 follow-up: the `x-anthropic-billing-header` env var name
  was case-sensitive in code but lower-cased on Linux containers
  (imrohitagrawal/citevyn#11 follow-up, commit `4a01850`).

## [0.9.0] — 2026-04-30

### Added
- Slice 8: Redis-backed sliding-window rate limiter with a Lua
  `EVAL` script that does `ZREMRANGEBYSCORE` + a conditional
  `ZADD` + `EXPIRE` in a single round trip. Replaces the
  in-process limiter when `CITEVYN_REDIS_URL` is set.
- Slice 7: Server-Sent Events streaming on
  `POST /v1/sessions/:id/messages/stream`.

## [0.8.0] — 2026-04-02

### Added
- Slice 6: admin key + admin routes (`/v1/admin/products`, `/v1/admin/
  sources`, `/v1/admin/sources/refresh`).
- Slice 5: orchestrator + grounded answer shape with `request_id`,
  `domain`, `intent`, `confidence`, `retrieval_strategy`, and
  `citations[]`.

---

### Release procedure

1. Cut a release branch: `git switch -c release/vX.Y.Z`.
2. Update `version.txt` and `pyproject.toml`.
3. Add a fresh `[X.Y.Z]` section to this file, dated today.
4. Run `make lint && make typecheck && make test && make golden` and
   attach the `golden_report.json` to the PR.
5. Open the PR with the `release-blocker` label removed (re-add it
   after merge if a hot-fix is required).
6. On merge, tag: `git tag -a vX.Y.Z -m "vX.Y.Z — <one-liner>"`.
7. Push: `git push origin main --follow-tags`.
