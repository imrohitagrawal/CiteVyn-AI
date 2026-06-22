# Slice 10 — Demo Readiness Design

**Branch:** `slice-10-demo-readiness` (off `main`, current HEAD `f556e5e`)
**Date:** 2026-06-22
**Author:** Claude (Opus 4.8), reviewed by user
**Status:** Approved → implementation plan in progress

---

## 1. Purpose

Close all P0 and P1 demo-readiness gaps identified in the 2026-06-22
project audit so the project can be called "demo ready" — meaning a
reviewer can run one command per Phase 5 exit criterion and the gates
either pass with recorded numbers or are explicitly deferred with a
documented reason.

This is **not** a release cut. It is the work that has to land *before*
a release cut, so that cutting `v0.9.0` is a tag operation, not a
scramble.

## 2. Scope

In scope (this slice):

1. Golden evaluation suite — 50 cases authored + runner + nightly CI.
2. Frontend CI job — type-check + build gate.
3. Slice 9b stub guard — reject `gemini` / `router` in production.
4. `docs/DEMO_CHECKLIST.md` — Phase 5 gate as a one-page checklist.
5. `CHANGELOG.md` — initialize with the actual slice-9 history.
6. `scripts/refresh_sources.sh` — implement the stub Slice 9c comment.
7. `make e2e` and `make demo-frontend` — single-command demo paths.
8. README + version reconciliation — README §1 frontend status, README §13 release example, `pyproject.toml` stays at `0.9.0`.
9. `docs/DEPENDABOT_TRIAGE.md` — policy doc for the 6 open PRs.
10. `release-blocker` GitHub label — referenced by RUNBOOK.md and RELEASE.md, currently missing.

Out of scope (explicit deferrals):

- **Slice 9b** — real Gemini client + multi-provider router. Stub guard accepts this slice's failure mode.
- **Real LLM answer-quality scoring** — faithfulness, completeness, "no unsupported claims" against a real model. Recorded as "pending 9b" in the runner output and the changelog.
- **The second 50-case expansion** — user will author in a follow-up slice. The runner and CI plumbing support 100+ cases with no changes.
- **Cache invalidation by document version** (PRD §15 V2) — not a demo gate.
- **Streaming tokens / auth UX / markdown rendering** in the frontend — explicitly out per `frontend/README.md` and the V1 roadmap.

## 3. Architecture

Five logical commits on a single branch, each independently reviewable:

| # | Commit prefix | What it lands | Risk |
|---|---|---|---|
| 1 | `chore(ci)` | frontend-ci.yml, Makefile `demo-frontend`, README §1 status flip | Low — additive CI |
| 2 | `feat(evals)` | tests/golden/ (50 cases + runner + scoring + Makefile target + nightly workflow) | Medium — new test surface |
| 3 | `fix(llm)` | factory.py gemini/router production guard | Low — narrows an existing edge |
| 4 | `chore(release)` | DEMO_CHECKLIST.md, CHANGELOG.md, refresh_sources.sh, version bump consistency, dependabot triage doc, release-blocker label seed | Low — docs + shell |
| 5 | `docs(readme)` | README §13 update + `make e2e` target + cross-link | Low — docs + Makefile |

The ordering matters: commit 2 produces real numbers that commit 4
references in `DEMO_CHECKLIST.md`. Commits 3 and 5 are independent of
the others and can be reordered.

## 4. Components

### 4.1 Golden suite (`backend/tests/golden/`)

#### 4.1.1 Case distribution

Per `docs/TEST_STRATEGY.md §5`, exactly 50 cases authored in this
slice. The user will add another 50 in a follow-up slice; the runner
and scoring have no upper bound on case count.

| Category | Count | Source |
|---|---|---|
| Codex usage | 10 | PRD §5 / TEST_STRATEGY §5 |
| Claude usage | 8 | TEST_STRATEGY §5 |
| Claude Code usage | 10 | TEST_STRATEGY §5 |
| Gemini usage | 8 | TEST_STRATEGY §5 |
| Exact lookup | 6 | TEST_STRATEGY §5 |
| Multi-doc how-to | 3 | TEST_STRATEGY §5 |
| Follow-up questions | 2 | TEST_STRATEGY §5 |
| Unsupported / out-of-domain | 2 | TEST_STRATEGY §5 |
| No-answer / weak-evidence | 1 | TEST_STRATEGY §5 |
| **Total** | **50** | |

#### 4.1.2 Case schema (per `docs/TEST_STRATEGY.md §6`)

Each case is a YAML file in `tests/golden/cases/` named
`golden_<NNN>.yaml`. Required fields, all already specified by
`TEST_STRATEGY.md §6`:

- `case_id` — `golden_001` through `golden_050`.
- `question` — natural-language query, exactly what `POST /v1/ask` would receive.
- `expected_domain` — `claude` | `claude_code` | `codex` | `gemini`.
- `expected_intent` — `how_to` | `exact_lookup` | `explanatory` | `unsupported` | `no_answer`.
- `expected_behavior` — `answer` | `refuse` | `no_answer`.
- `expected_sources` — list of human-readable source titles. The runner matches them against the `source_title` field returned in citations.
- `required_answer_points` — list of substrings that must appear in the answer text (used only when a real LLM is wired; scored as `n/a` for stub runs).
- `forbidden_answer_points` — list of substrings that must NOT appear (e.g. unsupported admin features).

New fields this slice adds to the schema:

- `category` — one of the 9 categories above. Drives the aggregate metrics.
- `gates` — list of gate names this case participates in: `retrieval_hit`, `citation_correctness`, `guardrail_refusal`, `no_answer_behavior`, `exact_lookup_accuracy`. `answer_quality` is excluded unless a real LLM is configured.

#### 4.1.3 Runner (`tests/golden/runner.py`)

Public API:

```python
def run_suite(
    *,
    client: TestClient,
    cases: list[Path] | None = None,  # default: tests/golden/cases/*.yaml
    llm_provider: str,                # "stub" or "anthropic"
) -> GoldenRunResult: ...
```

Flow per case:

1. Parse YAML, validate required fields. Parse error → `setup_error`, fail the run.
2. `POST /v1/ask` with `{"query": question}`. Capture response, status, latency.
3. Score each gate the case declares:
   - `retrieval_hit` — `expected_behavior == "answer"` AND response is not a refusal AND at least one citation returned.
   - `citation_correctness` — `expected_sources` is a subset of returned citation `source_title`s.
   - `guardrail_refusal` — `expected_behavior == "refuse"` AND response carries `refusal: true`.
   - `no_answer_behavior` — `expected_behavior == "no_answer"` AND response carries the configured `no_answer_fallback` copy.
   - `exact_lookup_accuracy` — `expected_intent == "exact_lookup"` AND response includes the exact term (e.g. a CLI flag verbatim).
   - `answer_quality` — skipped unless `llm_provider != "stub"`. When run, scores `required_answer_points` (all present → pass) and `forbidden_answer_points` (none present → pass).

Aggregate metrics:

- `pass_rate` — fraction of non-setup-error cases where every declared gate passed. A case that declares no gates is a setup error (the case author forgot to opt in to a gate), so this only matters for cases that opted in.
- Per-gate rates — `retrieval_hit_rate`, `citation_correctness_rate`, `guardrail_refusal_rate`, `no_answer_behavior_rate`, `exact_lookup_accuracy_rate`, `answer_quality_rate` (when applicable). Each per-gate rate is computed over the cases that declare that gate.
- `case_results` — list of per-case dicts (`{case_id, gates_passed, gates_failed, status, latency_ms}`).

Exit code: `0` if all declared gate rates ≥ thresholds, else `1`.
Thresholds per `docs/PRD.md §12` / `docs/TEST_STRATEGY.md §4` / `docs/RELEASE_PLAN.md §10`:

- `retrieval_hit_rate >= 0.95`
- `citation_correctness_rate >= 0.95`
- `guardrail_refusal_rate == 1.00` (critical failures = 0)
- `no_answer_behavior_rate >= 0.95`
- `exact_lookup_accuracy_rate >= 0.95`
- `answer_quality_rate >= 0.95` (only enforced when `llm_provider != "stub"`)

#### 4.1.4 CLI entry point

`backend/tests/golden/__main__.py` exposes:

```bash
cd backend
PYTHONPATH=. uv run python -m tests.golden \
    --llm-provider stub \
    --output ../artifacts/golden-results.json
```

Used by the `make golden` target and the nightly workflow.

#### 4.1.5 `make golden` target

```makefile
golden: ## Run the golden evaluation suite (requires the demo catalog seeded)
	cd backend && PYTHONPATH=. uv run python -m tests.golden \
	    --llm-provider $(LLM_PROVIDER) \
	    --output ../artifacts/golden-results.json
```

`LLM_PROVIDER` defaults to `stub` so the local run is hermetic. CI overrides to `anthropic` if a key is available; otherwise records answer-quality as `n/a` and skips that gate's enforcement.

#### 4.1.6 `.github/workflows/golden.yml`

Nightly cron (02:00 UTC) + manual `workflow_dispatch`. Runs against a real Postgres service with pgvector (mirroring the existing `postgres-migrations` job), applies migrations, seeds the demo catalog, runs the runner, uploads `golden-results.json` as a workflow artifact, and fails the run if any non-answer-quality gate drops below threshold.

### 4.2 Frontend CI (`.github/workflows/frontend-ci.yml`)

Triggered on push to `main` and on PRs that touch `frontend/**`
(paths filter). Three steps:

1. `actions/setup-node@v6` with `node-version: 20`.
2. `npm ci` in `frontend/`.
3. `npm run type-check` then `npm run build`.

Uploads `frontend/dist/` as an artifact so reviewers can download a
rendered bundle. Caches `~/.npm` keyed on `frontend/package-lock.json`.

No `npm test` step — `frontend/package.json` has no test script
(`frontend/README.md` explicitly defers component tests to V1).

### 4.3 Slice 9b stub guard (`backend/app/llm/factory.py`)

Additive change. New constant:

```python
# Providers that are accepted by the enum + config validation but whose
# real client implementations land in Slice 9b. In production we reject
# them the same way we reject ``stub`` — silently serving canned answers
# is worse than a startup failure.
UNSUPPORTED_LLM_PROVIDERS: frozenset[str] = frozenset({"gemini", "router"})
```

Extended check in `validate_llm_provider`:

```python
if settings.environment == "production" and (
    settings.llm_provider == "stub"
    or settings.llm_provider in UNSUPPORTED_LLM_PROVIDERS
):
    raise LLMProviderNotConfigured(
        f"CITEVYN_LLM_PROVIDER={settings.llm_provider!r} is not allowed "
        f"when CITEVYN_ENVIRONMENT='production'. Set it to 'anthropic' "
        f"and provide CITEVYN_LLM_API_KEY. (gemini / router are pending Slice 9b.)"
    )
```

The factory branches (`factory.py:80-91`) stay — `gemini` and `router` still work in dev/test against the stub. Only production deploys fail.

### 4.4 `docs/DEMO_CHECKLIST.md`

One-page gate. Six sections, each is one or two commands to run, plus a checkbox for the result:

1. **Pre-flight** — clean tree, on the release branch, no open `release-blocker` issues.
2. **Backend quality gates** — `make verify` + `make smoke`. Both must pass.
3. **Golden evaluation** — `make golden`. All non-answer-quality gates ≥95%, guardrail at 100%.
4. **Frontend smoke** — `make demo-frontend` succeeds, manual click-through of `/`, `/chat`, `/search`, `/about` in the preview.
5. **Operational readiness** — `make deploy` documented, runbook reviewed, rollback rehearsed on a non-prod VM.
6. **Documentation** — README §1 status accurate, CHANGELOG entry exists, ARCHITECTURE diagram links resolve, RUNBOOK §5 (release/rollback) tested.

Sources for each gate: explicit links to `docs/RELEASE_PLAN.md §5` (Phase 5 exit criteria) and `§10` (Release Blockers).

### 4.5 `CHANGELOG.md` (repo root)

Hand-initialized with the actual history that has shipped since the
last tag (or since the beginning, since no `v*` tag exists). Format
follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
First three sections:

```markdown
# Changelog

All notable changes to CiteVyn will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Golden evaluation suite (50 cases + runner + nightly CI). See `docs/superpowers/specs/2026-06-22-demo-readiness-design.md`.
- Frontend CI job (type-check + build).
- `docs/DEMO_CHECKLIST.md` — Phase 5 release gate.
- `make e2e` and `make demo-frontend` — single-command demo paths.

### Changed
- README §1 frontend status flipped from "In development" to "Optional preview".
- `validate_llm_provider` now rejects `gemini` and `router` in production (Slice 9b stub guard).

### Deferred
- Answer-quality scoring (faithfulness, completeness) — pending Slice 9b real LLM.

## [0.9.0] — 2026-06-22

### Added
- Slice 8: ingestion pipeline, admin surface, exact search (PR #7).
- Slice 9: rate limit, infra, docs, release pipeline (PR #11).
- Slice 9.1: rate-limit fail-closed, Redis pool close, conftest reset, hardcoded compose password removed, `get_current_request_id` returns `str`.
```

After this lands, the release workflow appends subsequent entries on tag push.

### 4.6 `scripts/refresh_sources.sh`

A 30-line shell script, executable, that:

1. Accepts an optional `--out <dir>` argument (default `infra/docker/sources/$(date -u +%Y-%m-%d)`).
2. Downloads the source manifests from the four upstream docs indexes (Claude, Claude Code, Codex, Gemini) — URLs are documented inline as comments so they're trivially editable.
3. Writes the manifests under `$out/<source>/manifest.json`.
4. Prints `$out` to stdout so an operator can pipe it into `CITEVYN_FIXTURES_ROOT`.

The script is idempotent (re-running overwrites). It is **not** invoked
by the demo — it exists because `backend/app/core/config.py:125`
references it. The reference comment is preserved; the phantom-file
problem goes away.

### 4.7 `make e2e` and `make demo-frontend`

```makefile
e2e: ## Full demo path: db-up + migrate + seed + uvicorn + frontend build + curl
	$(MAKE) demo
	cd backend && PYTHONPATH=. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
	@UVICORN_PID=$$!; \
	  sleep 3; \
	  curl -sf http://127.0.0.1:8000/health >/dev/null || (kill $$UVICORN_PID; exit 1); \
	  curl -sf -H "X-API-Key: $(API_KEY)" -H "Content-Type: application/json" \
	    -d '{"query":"How do I install Claude Code?"}' \
	    http://127.0.0.1:8000/v1/ask >/dev/null || (kill $$UVICORN_PID; exit 1); \
	  cd ../frontend && npm ci && npm run build >/dev/null || (kill $$UVICORN_PID; exit 1); \
	  kill $$UVICORN_PID; \
	  echo "e2e: backend healthy, /v1/ask cited, frontend bundle built."

demo-frontend: ## Build + serve the production frontend bundle on :4173
	cd frontend && npm ci && npm run build && npm run preview
```

The `e2e` target re-uses the existing `make demo` so the DB plumbing is shared. The frontend build is silent on success — error messages from npm propagate naturally on failure.

### 4.8 README + version reconciliation

README changes, all small:

- **§1 status table** — `Frontend` row flipped from "In development" to "Optional preview" with a one-line note: "Build via `make demo-frontend`; not part of the Phase 5 demo script. The API + curl is the demo surface."
- **§13 release example** — `v0.2.0` → `v0.9.0`. Bump the in-line command from `git tag -s v0.2.0` to `git tag -s v0.9.0` and the message to `v0.9.0 — demo-ready`. `backend/pyproject.toml` is already at `0.9.0`; no change there.
- **§10 local development** — add `make e2e` and `make demo-frontend` to the listed targets.

### 4.9 `docs/DEPENDABOT_TRIAGE.md`

Policy doc. One-paragraph policy + a per-PR table for the 6 open Dependabot PRs (#21–#26):

- Policy: "Patch + security updates auto-merge once CI passes. Minor + major open for human review. Major bumps (X→Y where Y−X > 0 in major version) require `make smoke` + manual UI check before merge."
- Per-PR table:

| PR | Bump | Major? | Action |
|---|---|---|---|
| #21 | redis 7-alpine → 8-alpine | Yes | Wait for smoke run; merge after. |
| #22 | docker/metadata-action 5 → 6 | Yes | Wait for smoke run; merge after. |
| #23 | postgres 16-alpine → 18-alpine | Yes | Wait for smoke run; merge after. **Volume permissions: see RUNBOOK §3.2.** |
| #24 | docker/build-push-action 6 → 7 | Yes | Wait for smoke run; merge after. |
| #25 | sqlalchemy[asyncio] >=2.0.30 → >=2.0.51 | No (patch/minor) | Auto-merge. |
| #26 | starlette 1.2.1 → 1.3.1 | Minor | Auto-merge after CI. |

### 4.10 `release-blocker` GitHub label

The label is referenced by `docs/RUNBOOK.md §6` and `.github/RELEASE.md` but does not exist. The audit ran `gh label list` and confirmed the absence.

Action: `gh label create release-blocker --color b60205 --description "Blocks the next release; close or convert to enhancement before tagging."`

Done via `gh` CLI from a Makefile target so it's idempotent and documented. The label needs to exist on the remote repo before any issue uses it; doing it in this slice means future release-blocker issues have somewhere to land.

## 5. Data flow

The golden suite is the only item with a non-trivial data flow:

```
tests/golden/cases/*.yaml (50)
        │
        ▼
runner.py ── validates YAML schema
        │
        ▼
TestClient(POST /v1/ask) ── against seeded SQLite (local)
                         └ against Postgres+pgvector (CI)
        │
        ▼
response {refusal, citations[], answer, latency_ms}
        │
        ▼
scoring.py ── gate-by-gate evaluation
        │
        ▼
GoldenRunResult {pass_rate, per_gate_rates, case_results}
        │
        ▼
artifacts/golden-results.json ── written by CLI, uploaded by golden.yml
        │
        ▼
EvaluationRun row ── written by runner when EVAL_DB_URL is set
```

The runner is read-only against the existing `EvaluationCase` /
`EvaluationRun` tables — it does not modify any production state.

## 6. Error handling

| Failure | Runner behavior |
|---|---|
| YAML parse error | `setup_error`, fail run, exit 1. |
| Missing required field | `setup_error`, fail run, exit 1. |
| TestClient HTTP error (5xx) | `run_error`, fail run, exit 1. |
| `expected_behavior=answer` but response is `refusal` | Gate `retrieval_hit` fails; counts as `fail` for `pass_rate`. |
| `expected_behavior=refuse` but response is a real answer | Gate `guardrail_refusal` fails; counts as `fail`. |
| `expected_behavior=no_answer` but response is real | Gate `no_answer_behavior` fails. |
| Citations missing or wrong source | `citation_correctness` fails for that case. |
| LLM provider is `stub` and a case requires `answer_quality` | Gate reported as `n/a`; not counted toward pass rate; threshold not enforced. |

The runner never silently passes on partial data.

## 7. Testing

- `tests/golden/test_runner.py` — covers all scoring paths, gate math, exit code, JSON output shape. Uses a small in-memory case set so the test itself is fast.
- `tests/golden/test_smoke.py` — runs the runner against 5 cases from `tests/golden/cases/` and asserts exit 0 on a fresh seeded DB. Runs in the default `pytest` job (fast feedback on every PR).
- `tests/test_llm_factory_singleton.py` — extend the existing production-guard test to assert `gemini` and `router` raise `LLMProviderNotConfigured` when `environment == "production"`.
- The `make e2e` target is verified by running it once on this branch and capturing the output as part of the PR description.

## 8. Migration / rollout

This slice lands on `slice-10-demo-readiness`, which is opened off
`main` at `f556e5e` (the current HEAD — dependabot tightening was the
last commit). Five commits land on the branch.

The branch is merged to `main` once:

1. `make verify` is green on the branch.
2. `make golden` against the seeded local DB exits 0 (with `LLM_PROVIDER=stub`, so only the infrastructure gates are enforced).
3. `make e2e` exits 0.
4. The branch review (`.github/workflows/pr-quality.yml`) is clean.

After merge, `v0.9.0` can be cut from `main` by tagging — no
follow-up work needed before the tag.

## 9. Open questions deferred to follow-up slices

1. **Real LLM scoring** — gated on Slice 9b. The runner already supports it; only the env flag needs to flip.
2. **Second 50 cases** — user-authored follow-up slice. Runner and CI handle 100+ cases with no changes.
3. **Per-gate artifact dashboards** — the JSON output is uploaded but no one is rendering it. A future slice could add a small static-site renderer.
4. **Cache correctness gate** — listed in `docs/TEST_STRATEGY.md §4` but not in this slice's golden suite. Cache invalidation has its own integration tests (`test_cache_invalidation.py`); a golden gate would require constructing specific cache hit/miss scenarios, which is its own design exercise.

## 10. Acceptance criteria for this slice

- [ ] Branch `slice-10-demo-readiness` exists off `main@<HEAD>` and contains the 5 commits described in §3.
- [ ] `backend/tests/golden/cases/` contains 50 YAML files matching the schema in §4.1.2.
- [ ] `make golden` runs the full suite, writes `artifacts/golden-results.json`, and exits 0 with `LLM_PROVIDER=stub` on a fresh `make demo` stack.
- [ ] `make e2e` exits 0 on a clean machine.
- [ ] `.github/workflows/frontend-ci.yml` exists and is green on a synthetic PR that only changes a comment in `frontend/src/`.
- [ ] `.github/workflows/golden.yml` exists and is green on a manual dispatch with stub LLM.
- [ ] `gh label list` shows `release-blocker`.
- [ ] `docs/DEMO_CHECKLIST.md` exists and links to `docs/RELEASE_PLAN.md §5` and `§10`.
- [ ] `CHANGELOG.md` exists at the repo root with the entries from §4.5.
- [ ] `scripts/refresh_sources.sh` exists, is executable, and `--help` exits 0.
- [ ] `backend/app/llm/factory.py` rejects `gemini` and `router` in production. Existing tests still pass.
- [ ] README §1 frontend status flipped, §13 version bumped to `0.9.0`.
- [ ] `docs/DEPENDABOT_TRIAGE.md` exists with the table from §4.9.