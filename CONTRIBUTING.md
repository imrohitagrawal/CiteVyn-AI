# Contributing to CiteVyn

Thanks for your interest in CiteVyn! This document covers the
mechanics of contributing. The product vision lives in
[`docs/PRD.md`](docs/PRD.md); architectural decisions in
[`docs/ADR/`](docs/ADR/).

## Code of conduct

Be respectful. We follow the
[Contributor Covenant](https://www.contributor-covenant.org/)
spirit. Disagreements are fine; personal attacks are not.

## How to contribute

### 1. Pick an issue or open one

- **Bugs** — open a GitHub issue with a reproducer, expected vs
  actual, and your environment. The `area:api`, `area:worker`,
  `area:infra`, and `area:docs` labels help triage.
- **Features** — open a GitHub issue with the user problem, the
  proposed solution, and any alternatives you considered. Large
  features need an ADR before code lands.
- **Documentation** — typos and clarity improvements are always
  welcome. Open a PR directly.

### 2. Local setup

```bash
git clone https://github.com/imrohitagrawal/citevyn.git
cd citevyn
make demo                      # brings up db + redis, runs migrations, seeds
cd backend && uv sync          # resolves the python environment
make verify                    # runs lint + typecheck + test
```

### 3. Pre-merge gate

Before opening a PR, **all of these must be green on your machine**:

```bash
make verify                    # ruff + pyright + pytest
```

CI re-runs the same set on every push plus the
`postgres-migrations` job. A PR with a red gate will not be
reviewed.

### 4. Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/).
PR titles follow the same scheme:

```
feat: add per-route rate-limit quotas
fix(worker): drain in-flight job on SIGTERM
docs: clarify refusal envelope semantics
chore: bump fastapi to 0.118
```

Scope is optional; use the module name when the change is local
(`api`, `worker`, `ingestion`, `retrieval`, `infra`, `docs`).

### 5. Branch + PR workflow

- Branch from `main`. Naming: `slice-N-short-description` or
  `fix/short-description`.
- One logical change per PR. Squash commits if you have fixup
  noise.
- Reference the issue in the PR body (`Closes #123`).
- A maintainer will review within **3 business days**. Reviewers
  may request changes; the review is a conversation, not a gate.

### 6. Architectural changes

Anything that touches:

- the HTTP contract (`backend/app/api/`),
- the storage model (`db/`, `backend/app/db/`),
- cross-service wiring (auth, rate-limit, ingestion), or
- the deployment topology (Dockerfile, compose, Caddy),

…must come with an **ADR** under `docs/ADR/`. The next number is
`0003` (after `0001-core-architecture.md` and
`0002-deployment.md`).

## Testing guidelines

- **New code = new test.** No exceptions. Aim for a unit test
  per public function and an integration test per route.
- **Test names** — `test_<unit>_<scenario>_<expected>`. Example:
  `test_ask_endpoint_with_refused_query_returns_envelope`.
- **Mark external-service tests** with `pytest.mark.postgres`
  (already declared in `pyproject.toml`).
- **Don't disable lint to make a test pass.** If ruff or pyright
  flags it, the test has a real problem.

## Project-specific conventions

- **Async everywhere** — the API is fully `async/await`. Mixing
  blocking calls in a request handler blocks the event loop. If
  you need a blocking lib, wrap it in `asyncio.to_thread`.
- **No `Any`** in `app/` — pyright is in strict mode. Use a real
  type or a `Protocol`; if a third-party lib forces your hand,
  add a `# pyright: ignore[reportExplicitAny]` next to the
  offending line, with a comment explaining why.
- **Settings are env-driven** — never read `os.environ` outside
  `app/core/config.py`. New knobs go in `Settings`, with a default
  that's safe in production.
- **No global mutable state** — except the `Settings` singleton
  and the lazy-initialised LLM client / Redis client. The latter
  two are released on the FastAPI `lifespan` shutdown event.

## Release process

Maintainers only. See [§13 of the README](README.md#13-release-process)
and [`.github/RELEASE.md`](.github/RELEASE.md).

## License

By contributing, you agree that your contributions will be
licensed under the [MIT License](LICENSE).