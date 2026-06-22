# CiteVyn Release Plan

## 1. Purpose

This document defines the release plan for CiteVyn MVP and the roadmap to enterprise readiness.

## 2. Release Principles

1. Release only after quality gates pass.
2. Do not deploy a candidate index directly.
3. Always keep a last known good index.
4. Keep MVP small and credible.
5. Defer enterprise features until answer quality is proven.
6. Exclude voice from MVP.

## 3. MVP Release Scope

MVP includes:

1. Claude.
2. Claude Code.
3. Codex.
4. Gemini.
5. Chat Q&A.
6. Official documentation ingestion.
7. Contextual chunking.
8. Hybrid retrieval.
9. Exact lookup.
10. FAQ/cache routing.
11. Citations.
12. No-answer guardrail.
13. Basic security.
14. Basic observability.
15. 50-question evaluation suite.

## 4. MVP Non-Goals

1. ChatGPT.
2. Cursor.
3. Voice.
4. Private docs.
5. Enterprise RBAC.
6. Tenant isolation.
7. Reviewer workflow.
8. Automated freshness.
9. General web search.

## 5. Phased Release Plan

### Phase 0: Architecture and Planning

Exit criteria:

1. Architecture package approved.
2. ADR-0001 approved.
3. Source list locked.
4. Golden dataset template approved.
5. Demo cost limit defined.

### Phase 1: Foundation Build

Scope:

1. FastAPI backend.
2. PostgreSQL + pgvector.
3. Redis cache.
4. Demo auth.
5. Admin API key.
6. Basic frontend.
7. Health endpoints.

Exit criteria:

1. Services run with Docker Compose.
2. Health endpoints pass.
3. Auth and rate limits work.
4. Admin endpoints are protected.

### Phase 2: Ingestion and Indexing

Scope:

1. Source fetchers.
2. Parsers.
3. Contextual chunker.
4. Exact term extractor.
5. Embedding generation.
6. Candidate index creation.
7. Ingestion job status.

Exit criteria:

1. All MVP sources ingest successfully.
2. Failed ingestion is visible.
3. Candidate index is not promoted automatically.
4. Last known good index exists.

### Phase 3: Retrieval and Answer Engine

Scope:

1. Domain guardrail.
2. Intent router.
3. Exact lookup.
4. Keyword search.
5. Vector search.
6. Reranker.
7. Answer generator.
8. Citation validator.
9. No-answer fallback.

Exit criteria:

1. Exact lookup works.
2. Unsupported questions are refused.
3. Factual answers include citations.
4. No-answer behavior works.

### Phase 4: Evaluation and Observability

Scope:

1. 50-question golden suite.
2. Evaluation runner.
3. Quality metrics.
4. Structured logs.
5. Basic dashboard.
6. Alert thresholds.

Exit criteria:

1. Golden pass rate >=95%.
2. Domain guardrail critical failures = 0.
3. Citation correctness >=95%.
4. Retrieval hit rate >=95%.
5. P95 latency is acceptable for demo.

### Phase 5: MVP Demo Release

Scope:

1. Package demo.
2. Deploy locally or on single VM.
3. Run release checklist.
4. Record known limitations.
5. Prepare next-phase backlog.

Exit criteria:

1. Release gates pass.
2. No critical security gaps.
3. No stale diagram links.
4. Rollback tested.
5. Demo script ready.

## 6. Deployment Strategy

MVP deployment:

```text
Docker Compose
FastAPI
PostgreSQL + pgvector
Redis
React or Next.js frontend
Background worker
Structured logs
```

Optional cloud demo:

```text
Single VM
Docker Compose
Reverse proxy
TLS
Environment-based secrets
```

## 7. Index Promotion Strategy

```text
Fetch docs
 -> Build candidate index
 -> Run ingestion validation
 -> Run golden evaluation
 -> Promote if gates pass
 -> Otherwise keep active index
```

Promotion gates:

1. Golden pass rate >=95%.
2. Citation correctness >=95%.
3. Retrieval hit rate >=95%.
4. Domain guardrail critical failures = 0.
5. Ingestion errors = 0.

## 8. Rollback Strategy

1. Keep previous good index.
2. Do not overwrite active index during candidate build.
3. Promote indexes explicitly.
4. Revert by promoting previous good index.
5. Continue serving from last known good index if candidate fails.

## 9. Cost Controls

MVP defaults:

```text
soft daily limit: $5
hard daily limit: $10
```

On soft limit:

1. Prefer cache.
2. Log warnings.
3. Optionally disable expensive reranking.

On hard limit:

1. Stop LLM generation.
2. Allow cached answers.
3. Allow exact lookup.
4. Return controlled limit message.

## 10. Release Blockers

Do not release if:

1. Golden pass rate is below 95%.
2. Domain guardrail fails critical unsupported tests.
3. Citation validator fails.
4. Exact lookup fails for known commands or flags.
5. No-answer behavior fails.
6. Cache serves answer without citations.
7. Admin endpoints are unprotected.
8. Ingestion failures are hidden.
9. Rollback is not tested.

## 11. V1 Roadmap

1. ChatGPT official docs.
2. Voice output.
3. Feedback capture.
4. Scheduled source refresh.
5. Evaluation dashboard.
6. Better reranking.

## 12. V2 Roadmap

1. Cursor docs.
2. Voice input.
3. Reviewer-agent workflow.
4. Automated freshness.
5. Cache invalidation by document version.
6. Browser extension.

## 13. Enterprise Roadmap

1. SSO.
2. RBAC and ABAC.
3. Tenant isolation.
4. Private source connectors.
5. Admin portal.
6. Audit exports.
7. Compliance controls.
8. Slack and Teams integrations.
9. Cost controls.
10. Multi-source governance.
