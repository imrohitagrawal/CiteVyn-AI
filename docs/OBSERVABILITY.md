# CiteVyn Observability

## 1. Purpose

This document defines the observability model for CiteVyn.

Observability must answer:

1. Did the system retrieve the right evidence?
2. Did the answer use correct citations?
3. Did the system refuse unsupported questions correctly?
4. What did the query cost?
5. Where did latency occur?
6. Is the active index healthy?
7. Are quality gates passing?

## 2. Observability Principles

1. Every answer must be traceable.
2. Retrieval quality is as important as API latency.
3. Citation correctness must be measurable.
4. No-answer and unsupported rates must be visible.
5. Ingestion health must be visible.
6. Cost must be tracked from MVP.

## 3. Minimum Trace Fields

```text
request_id
session_id
user_id
question
domain
intent
cache_hit
retrieval_strategy
top_chunks
citations_returned
confidence
unsupported
no_answer
latency_ms
tokens_in
tokens_out
estimated_cost
```

## 4. Metrics

### 4.1 API Metrics

1. Request count.
2. Error count.
3. P50/P95/P99 latency.
4. Rate-limit count.
5. Auth failures.

### 4.2 Retrieval Metrics

1. Retrieval hit rate.
2. Empty retrieval rate.
3. Top-k chunk scores.
4. Reranker scores.
5. Exact lookup hit rate.
6. Unsupported query rate.
7. Weak-evidence rate.

### 4.3 Answer Quality Metrics

1. Citation correctness.
2. Answer faithfulness.
3. No-answer correctness.
4. Follow-up correctness.
5. Golden evaluation pass rate.
6. Failed golden cases by category.

### 4.4 Cost Metrics

1. Tokens in.
2. Tokens out.
3. Cost per query.
4. Daily cost.
5. Cache savings.
6. Cost-limit events.

### 4.5 Ingestion Metrics

1. Last successful ingestion time.
2. Current ingestion status.
3. Failed ingestion jobs.
4. Documents fetched.
5. Chunks generated.
6. Embeddings generated.
7. Candidate index version.
8. Active index version.

## 5. Logs

Use structured JSON logs.

Example:

```json
{
  "timestamp": "2026-06-07T10:00:00Z",
  "level": "INFO",
  "request_id": "req_123",
  "event": "answer_generated",
  "domain": "claude_code",
  "intent": "how_to",
  "cache_hit": false,
  "latency_ms": 1450,
  "citations_count": 2,
  "no_answer": false
}
```

## 6. Dashboards

Minimum dashboard panels:

1. Query volume.
2. Cache hit rate.
3. Unsupported question rate.
4. No-answer rate.
5. Retrieval hit rate.
6. Exact lookup hit rate.
7. Citation correctness.
8. Golden evaluation score.
9. P95 latency.
10. Daily estimated cost.
11. Ingestion status.
12. Active index version.

## 7. Alerts

### 7.1 Critical Alerts

1. Active index unavailable.
2. Domain guardrail critical failure.
3. Citation validator failure spike.
4. Daily hard cost limit reached.
5. Admin auth failure spike.
6. Ingestion failure for all sources.

### 7.2 Warning Alerts

1. No-answer rate unusually high.
2. Retrieval hit rate below threshold.
3. Cache hit rate unexpectedly low.
4. P95 latency above target.
5. Candidate index evaluation failed.

## 8. Trace Sampling

For MVP, trace all demo traffic.

For enterprise, use configurable trace sampling, but always trace:

1. Unsupported responses.
2. No-answer responses.
3. Failed citation validation.
4. Admin actions.
5. Ingestion jobs.
6. Evaluation runs.

## 9. Retention

MVP suggested retention:

| Data | Retention |
|---|---:|
| Request logs | 7 days |
| Audit events | 30 days |
| Evaluation results | 90 days |
| Ingestion job history | 90 days |
| Cached answers | TTL-based |

Enterprise retention should be configurable.

## 10. Open Questions

1. Which observability stack will be used?
2. Will tracing use OpenTelemetry from day one?
3. What is the exact P95 latency target?
4. What is the daily cost budget?
5. Who receives alerts?
