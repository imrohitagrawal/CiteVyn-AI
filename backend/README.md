# CiteVyn Backend

Slice 1 provides the minimal FastAPI foundation only:

- health endpoints
- environment-based settings
- request ID middleware
- demo API key auth dependency
- structured log redaction helpers
- pytest, ruff, and pyright configuration

Slice 1 intentionally does not include database persistence, Docker Compose, ingestion,
vector search, embeddings, LLM generation, frontend, admin endpoints, feedback, or
evaluation.

## Local Commands

From the repository root, enter the backend project first:

```bash
cd backend
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

Running `uv run pytest` from the repository root will not find the backend
dependencies because the `pyproject.toml` for Slice 1 lives in `backend/`.

## Configuration

Set the demo API key with:

```bash
export CITEVYN_DEMO_API_KEY="local-demo-key"
```

If unset, local development and tests use `local-demo-key`.
