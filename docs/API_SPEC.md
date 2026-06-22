# CiteVyn API Specification

## 1. Purpose

This document defines the MVP API surface for CiteVyn.

The API supports:

1. Session creation.
2. Chat-based questions.
3. Exact lookup.
4. Feedback placeholder.
5. Admin ingestion.
6. Internal evaluation.
7. Health checks.

## 2. API Principles

1. Keep public APIs simple.
2. Keep ingestion and evaluation admin-only.
3. Return citations for factual answers.
4. Return explicit no-answer and unsupported flags.
5. Include trace identifiers in responses.
6. Avoid leaking internal IDs except where useful for debugging or citation traceability.

## 3. Authentication

### MVP

Use demo auth:

```http
Authorization: Bearer <demo-token>
```

Admin endpoints require:

```http
X-Admin-API-Key: <admin-key>
```

## 4. Common Response Fields

Most API responses should include:

```json
{
  "request_id": "req_123",
  "status": "success"
}
```

Error responses:

```json
{
  "request_id": "req_123",
  "status": "error",
  "error": {
    "code": "unsupported_domain",
    "message": "I can answer questions about Claude, Claude Code, Codex, and Gemini using indexed official documentation."
  }
}
```

## 5. Create Session

```http
POST /v1/sessions
```

### Request

```json
{
  "user_id": "demo_user",
  "channel": "chat"
}
```

### Response

```json
{
  "request_id": "req_001",
  "session_id": "sess_001",
  "expires_at": "2026-06-07T12:00:00Z"
}
```

## 6. Ask Question

```http
POST /v1/sessions/{session_id}/messages
```

### Request

```json
{
  "message": "How do I configure Claude Code permissions?",
  "answer_style": "short"
}
```

Allowed `answer_style` values:

```text
short
step_by_step
```

### Response

```json
{
  "request_id": "req_002",
  "message_id": "msg_001",
  "answer": "Short citation-backed answer.",
  "citations": [
    {
      "source_name": "Claude Code Docs",
      "title": "Permissions",
      "url": "https://example.com/docs",
      "chunk_id": "chunk_123"
    }
  ],
  "domain": "claude_code",
  "intent": "how_to",
  "confidence": "high",
  "cache_hit": false,
  "retrieval_strategy": "hybrid_reranked",
  "unsupported": false,
  "no_answer": false
}
```

### Unsupported Response

```json
{
  "request_id": "req_003",
  "message_id": "msg_002",
  "answer": "I can answer questions about Claude, Claude Code, Codex, and Gemini using indexed official documentation. I do not have credible source material in this assistant to answer that.",
  "citations": [],
  "domain": "unsupported",
  "intent": "unsupported",
  "confidence": "none",
  "cache_hit": false,
  "retrieval_strategy": "none",
  "unsupported": true,
  "no_answer": true
}
```

## 7. Exact Lookup

```http
GET /v1/search/exact?q=--some-flag
```

### Response

```json
{
  "request_id": "req_004",
  "query": "--some-flag",
  "matches": [
    {
      "term": "--some-flag",
      "term_type": "flag",
      "product_area": "codex",
      "document_title": "CLI Reference",
      "source_url": "https://example.com/cli",
      "chunk_id": "chunk_456",
      "snippet": "Relevant official documentation snippet."
    }
  ]
}
```

## 8. Feedback Placeholder

Not active in MVP, but the contract exists for V1.

```http
POST /v1/feedback
```

### Request

```json
{
  "session_id": "sess_001",
  "message_id": "msg_001",
  "rating": "incorrect",
  "comment": "The citation does not support the answer."
}
```

### Response

```json
{
  "request_id": "req_005",
  "status": "accepted"
}
```

## 9. Admin: Trigger Ingestion

```http
POST /internal/v1/ingestion/jobs
```

Admin-only.

### Request

```json
{
  "source_name": "codex",
  "mode": "full"
}
```

### Response

```json
{
  "request_id": "req_006",
  "job_id": "ing_001",
  "status": "pending"
}
```

## 10. Admin: Get Ingestion Job

```http
GET /internal/v1/ingestion/jobs/{job_id}
```

### Response

```json
{
  "request_id": "req_007",
  "job_id": "ing_001",
  "source_name": "codex",
  "status": "completed",
  "stage": "indexing",
  "started_at": "2026-06-07T10:00:00Z",
  "completed_at": "2026-06-07T10:05:00Z",
  "errors": []
}
```

## 11. Admin: Latest Ingestion Status

```http
GET /internal/v1/ingestion/latest
```

## 12. Admin: Run Evaluation

```http
POST /internal/v1/evaluations/run
```

### Request

```json
{
  "index_version": "index_v12",
  "suite": "mvp_golden_50"
}
```

### Response

```json
{
  "request_id": "req_008",
  "evaluation_run_id": "eval_001",
  "status": "running"
}
```

## 13. Admin: Promote Index

```http
POST /internal/v1/indexes/{index_version}/promote
```

Promotion is allowed only if required evaluation gates pass.

## 14. Health Checks

```http
GET /health
GET /health/index
GET /health/dependencies
```

### `/health/index` Response

```json
{
  "active_index": "index_v12",
  "previous_good_index": "index_v11",
  "last_successful_ingestion": "2026-06-07T10:05:00Z",
  "status": "healthy"
}
```

## 15. Error Codes

| Code | Meaning |
|---|---|
| unsupported_domain | Query outside supported scope |
| weak_evidence | Not enough source evidence |
| citation_validation_failed | Answer not supported by citations |
| rate_limited | User exceeded rate limit |
| auth_required | Missing or invalid auth |
| ingestion_failed | Ingestion job failed |
| evaluation_failed | Evaluation gate failed |
| index_unavailable | Active index unavailable |
| cost_limit_reached | Demo daily cost cap reached |
