# ADR-0001: Core Architecture for CiteVyn

## Status

Accepted for MVP planning.

## Date

2026-06-07

## Context

CiteVyn is a trusted AI-tool usage assistant that answers from official documentation, not guesses.

The MVP needs to support Claude, Claude Code, Codex, and Gemini. It must provide citation-backed answers, exact lookup, contextual retrieval, follow-up support, FAQ caching, no-answer fallback, basic security, observability, and evaluation gates.

The architecture must remain realistic for MVP while allowing enterprise expansion later.

## Decision

Build a chat-first RAG architecture with:

1. FastAPI backend.
2. PostgreSQL with pgvector.
3. Redis cache.
4. Controlled official-doc ingestion.
5. Contextual heading-aware chunking.
6. Exact term index.
7. Hybrid retrieval.
8. Reranking.
9. Grounded answer generation.
10. Citation validation.
11. Domain guardrail.
12. Versioned indexes.
13. Golden evaluation suite.
14. Docker Compose deployment for MVP.

## Key Design Choices

### 1. Chat-First MVP

Voice is excluded from MVP to reduce cost, latency, and testing complexity.

### 2. Official Sources Only

The assistant will answer only from official documentation for supported product areas.

### 3. Hybrid Retrieval

Pure vector search is insufficient for flags, commands, config keys, model names, errors, and environment variables.

### 4. Exact Term Index

Exact lookup is a first-class path, not an afterthought.

### 5. Citation Required for Factual Answers

No citation means no factual answer.

### 6. No-Answer Fallback

If evidence is weak, the system must clearly say it cannot answer reliably.

### 7. Versioned Indexes

Candidate indexes must pass evaluation before promotion. The system keeps a last known good index.

### 8. Docker Compose First

MVP uses Docker Compose instead of Kubernetes to avoid over-engineering.

## Alternatives Considered

### Alternative 1: Single `/ask` Endpoint with Simple Vector Search

Rejected.

Reason:

- Weak exact lookup.
- Poor observability.
- Hard to separate cache, retrieval, and answer behavior.
- High hallucination risk.

### Alternative 2: Kubernetes from Day One

Rejected for MVP.

Reason:

- Higher operational burden.
- Unnecessary for controlled demo traffic.
- Slows early iteration.

### Alternative 3: Include ChatGPT in MVP

Rejected for MVP.

Reason:

- ChatGPT Help Center ingestion requires HTML crawling and broader product expectations.
- Better added after core RAG quality is proven.

### Alternative 4: Voice in MVP

Rejected.

Reason:

- Adds cost, latency, quality, and testing complexity.
- Does not help prove the core answer engine.

## Consequences

### Positive

1. MVP remains focused.
2. Retrieval quality is measurable.
3. Exact lookup is reliable.
4. Costs are controlled.
5. Enterprise expansion remains possible.
6. Rollback is safe through versioned indexes.

### Negative

1. MVP does not support ChatGPT.
2. MVP does not support voice.
3. MVP requires disciplined ingestion and evaluation work.
4. Users may expect broader AI-tool coverage than MVP supports.

## Implementation Notes

1. Keep product areas separate: `claude_api`, `claude_code`, `codex`, `gemini_api`.
2. Use source checksums in cache keys.
3. Do not promote candidate indexes automatically.
4. Trace every answer during MVP.
5. Require 50-question golden evaluation suite before demo release.

## Related Documents

- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/API_SPEC.md`
- `docs/DATA_MODEL.md`
- `docs/SECURITY_MODEL.md`
- `docs/OBSERVABILITY.md`
- `docs/TEST_STRATEGY.md`
- `docs/RELEASE_PLAN.md`
