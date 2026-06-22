# CiteVyn Architecture

## 1. Architecture Goals

CiteVyn is designed as a production-shaped MVP that can answer questions about official AI-tool documentation without becoming a generic hallucinating chatbot.

Architecture goals:

1. Answer from official documentation only.
2. Require citations for factual answers.
3. Avoid sending every query to the LLM.
4. Support exact lookup for commands, flags, config keys, errors, model names, and environment variables.
5. Support contextual retrieval for multi-step and multi-document questions.
6. Support follow-up context without allowing context drift.
7. Cache safe answers before expensive generation.
8. Provide observability into retrieval, quality, cost, and failure modes.
9. Keep MVP simple enough to build with Docker Compose.
10. Keep architecture extensible for enterprise scale.

## 2. System Boundaries

### 2.1 Inside MVP Scope

1. Chat Q&A.
2. Official documentation ingestion.
3. Contextual chunking.
4. Hybrid retrieval.
5. Exact lookup.
6. Follow-up context.
7. FAQ/cache routing.
8. Short citation-backed answers.
9. Domain guardrail.
10. No-answer fallback.
11. Basic demo auth and rate limiting.
12. Basic observability.
13. Golden evaluation suite.

### 2.2 Outside MVP Scope

1. ChatGPT.
2. Cursor.
3. Voice input.
4. Voice output.
5. Private documents.
6. Enterprise RBAC.
7. Multi-tenant isolation.
8. Automated freshness.
9. Reviewer-agent workflow.
10. General web search.

## 3. Major Components

### 3.1 Web Chat UI

A simple web interface for asking questions and viewing answers, citations, confidence, and follow-up context.

### 3.2 API Gateway / Backend API

FastAPI service exposing session, message, exact lookup, ingestion, evaluation, and health endpoints.

### 3.3 Demo Auth and Rate Limiter

Provides visible MVP security through demo login or API key, role checks, and request throttling.

### 3.4 Domain Guardrail

Classifies whether the user query belongs to supported product areas:

- Claude API
- Claude Code
- Codex
- Gemini API

Unsupported queries are refused before retrieval and generation.

### 3.5 Intent Router

Routes queries into:

- FAQ cache
- Exact lookup
- Hybrid retrieval
- Clarification
- No-answer fallback

### 3.6 Session Manager

Maintains bounded conversation context and prevents cross-product context contamination.

### 3.7 Retrieval Engine

Uses hybrid retrieval:

1. Exact term index.
2. Keyword search.
3. Vector search.
4. Reranking.

### 3.8 Answer Generator

Generates short, grounded answers using retrieved evidence only.

### 3.9 Citation Validator

Checks that factual answer claims are supported by retrieved chunks.

### 3.10 Cache Layer

Caches FAQ answers, exact lookups, retrieval results, and eligible grounded answers.

### 3.11 Ingestion Worker

Fetches official docs, parses content, chunks documents, extracts exact terms, generates embeddings, and builds candidate index versions.

### 3.12 Evaluation Runner

Runs golden test suites before index promotion or release.

### 3.13 Observability Layer

Captures logs, traces, metrics, cost estimates, retrieval metadata, citation status, and alerts.

## 4. Request Flow

1. User submits question.
2. API authenticates request.
3. Rate limiter checks quota.
4. Domain guardrail classifies query.
5. Unsupported queries return scoped refusal.
6. Intent router checks FAQ/cache or exact lookup.
7. Retrieval engine fetches relevant chunks when needed.
8. Reranker ranks evidence.
9. Answer generator produces grounded answer.
10. Citation validator verifies support.
11. Confidence gate decides answer or no-answer.
12. Response is returned with citations.
13. Trace and metrics are recorded.

## 5. Data Flow

### 5.1 Ingestion Data Flow

```text
Official docs
 -> Fetcher
 -> Parser
 -> Contextual chunker
 -> Exact-term extractor
 -> Embedding generator
 -> Candidate index
 -> Evaluation runner
 -> Active index promotion
```

### 5.2 Query Data Flow

```text
User query
 -> Query normalization
 -> Domain guardrail
 -> Intent router
 -> Cache / exact lookup / retrieval
 -> Reranker
 -> Answer generator
 -> Citation validator
 -> Response
```

### 5.3 Cache Data Flow

Cache keys include:

```text
normalized_question
+ product_area
+ source_version_hash
+ answer_policy_version
```

Cached answers must include citations and must be invalidated when cited chunks change.

## 6. Auth/Authz Model

### 6.1 MVP Auth

MVP uses simple demo auth:

- Demo user login or demo API key.
- Admin API key for ingestion and evaluation.
- Anonymous access disabled.

### 6.2 MVP Authorization

MVP roles:

| Role | Ask Questions | Trigger Ingestion | Run Evaluation | View Logs |
|---|---:|---:|---:|---:|
| demo_user | Yes | No | No | No |
| admin | Yes | Yes | Yes | Yes |

### 6.3 Enterprise Auth/Authz

Enterprise should add:

1. SSO.
2. RBAC.
3. ABAC.
4. Tenant isolation.
5. Chunk-level ACL.
6. Audit exports.
7. Private source authorization.

## 7. Scalability Approach

### 7.1 MVP Scalability

1. Use Docker Compose.
2. Use PostgreSQL with pgvector.
3. Use Redis for cache.
4. Use Postgres full-text search initially.
5. Use background ingestion workers.
6. Use cache before LLM.
7. Avoid voice in MVP.
8. Use strict rate limits.

### 7.2 Enterprise Scalability

1. Separate retrieval service.
2. Dedicated vector store or managed search.
3. Horizontal worker scaling.
4. Multi-tenant index isolation.
5. Distributed tracing.
6. Queue-based ingestion.
7. Autoscaling.
8. Cost controls and per-tenant quotas.

## 8. Failure Modes

| Failure Mode | Risk | Mitigation |
|---|---|---|
| Unsupported query receives generic answer | Hallucination | Domain guardrail before retrieval |
| Citation does not support answer | False trust | Citation validator |
| Exact flag missed | Bad UX | Exact term index |
| Claude and Claude Code confused | Wrong answer | Product-area metadata |
| Cached answer stale | Outdated answer | Source checksum in cache key |
| Source ingestion fails | Stale index | Candidate index and last known good |
| Follow-up context drifts | Wrong answer | Bounded session context |
| Poor chunking | Weak retrieval | Heading-aware contextual chunking |
| Tests weakened | False quality | Test governance rule |

## 9. Trade-Offs

### 9.1 Docker Compose over Kubernetes

Chosen for MVP simplicity. Kubernetes is deferred until enterprise deployment needs justify it.

### 9.2 pgvector over Dedicated Vector DB

Chosen for operational simplicity. A dedicated vector store can be introduced later if scale demands.

### 9.3 Excluding Voice

Chosen to reduce MVP cost, latency, and testing complexity.

### 9.4 Excluding ChatGPT

Chosen because ChatGPT Help Center ingestion adds HTML crawling and broader user expectations. It is deferred to V1.

### 9.5 Conservative Cache

Chosen to reduce cost while protecting answer correctness through checksum-based invalidation.

## 10. Open Questions

1. Final source URL list.
2. Final generation model.
3. Final embedding model.
4. Reranker choice.
5. Cache TTL values.
6. Daily cost cap.
7. Production hosting target.
8. Golden dataset owner.
9. Test-change approval owner.

## 11. MVP Scope

```text
Claude
Claude Code
Codex
Gemini
Chat Q&A
Hybrid retrieval
Exact lookup
FAQ cache
Citations
No-answer guardrail
Basic security
Basic observability
50-question eval suite
```

## 12. Enterprise Scope

1. ChatGPT official docs.
2. Cursor official docs.
3. Voice output.
4. Voice input.
5. Feedback capture.
6. Reviewer-agent workflow.
7. Scheduled source refresh.
8. SSO.
9. RBAC and ABAC.
10. Tenant isolation.
11. Private source connectors.
12. Admin portal.
13. Audit exports.
14. Compliance controls.
15. Slack and Teams integration.
16. Browser extension.
17. Evaluation dashboard.
18. Cost controls.

## 13. Deferred Decisions

1. ChatGPT source ingestion.
2. Cursor source ingestion.
3. Voice provider.
4. Enterprise identity provider.
5. Dedicated vector database.
6. Kubernetes deployment.
7. Full audit retention policy.
8. Tenant-level data partitioning.
9. Reviewer-agent implementation.
10. Human review workflow.

## 14. Phased Implementation Plan

### Phase 0: Architecture Lock

- Finalize docs.
- Finalize ADR-0001.
- Finalize source list.
- Finalize golden dataset template.

### Phase 1: MVP Foundation

- Build FastAPI backend.
- Implement demo auth.
- Implement ingestion pipeline.
- Implement PostgreSQL + pgvector schema.
- Implement cache.
- Implement basic UI.

### Phase 2: Retrieval and Answer Quality

- Implement hybrid retrieval.
- Implement exact term index.
- Implement reranker.
- Implement citation validator.
- Implement no-answer fallback.

### Phase 3: Evaluation and Release

- Build 50-question golden dataset.
- Run quality gates.
- Add dashboards.
- Package demo release.

### Phase 4: V1 Expansion

- Add ChatGPT docs.
- Add voice output.
- Add feedback capture.
- Add scheduled refresh.

### Phase 5: Enterprise Expansion

- Add SSO/RBAC.
- Add tenant isolation.
- Add private source connectors.
- Add full audit and compliance controls.

## 15. Diagram Links

- [System Context](../diagrams/01-system-context.md)
- [Container Architecture](../diagrams/02-container-architecture.md)
- [Backend Component Architecture](../diagrams/03-backend-component-architecture.md)
- [Main Request Sequence](../diagrams/04-main-request-sequence.md)
- [Data Model ERD](../diagrams/05-data-model-erd.md)
- [Deployment Architecture](../diagrams/06-deployment-architecture.md)
- [Observability and Alerting Flow](../diagrams/07-observability-and-alerting-flow.md)
