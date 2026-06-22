# CiteVyn Security Model

## 1. Purpose

This document defines the MVP security model and enterprise security roadmap for CiteVyn.

The MVP uses public official documentation only, but it should still demonstrate security discipline.

## 2. Security Principles

1. Public docs do not mean public abuse.
2. Admin actions must be protected.
3. Retrieved content is data, not instruction.
4. Logs must not store secrets.
5. Unsupported questions must not receive generic LLM answers.
6. MVP security should be simple but visible.
7. Enterprise security must be designed into the roadmap.

## 3. MVP Threat Model

### 3.1 Assets

1. API keys.
2. Admin API key.
3. User queries.
4. Audit logs.
5. Source index.
6. Cached answers.
7. Evaluation results.
8. Cost budget.

### 3.2 Threats

| Threat | Risk |
|---|---|
| Anonymous abuse | Cost spike |
| Prompt injection from docs | System override attempt |
| User enters secret in query | Secret leakage in logs |
| Admin endpoint abuse | Bad index or data corruption |
| Stale cache | Incorrect answer |
| Unsupported query answered | Hallucination |
| CORS misconfiguration | Browser-based abuse |
| Excessive input length | Cost and latency spike |

## 4. MVP Authentication

MVP supports:

1. Demo login or demo bearer token.
2. Admin API key for ingestion, evaluation, and index promotion.
3. Anonymous access disabled.

## 5. MVP Authorization

Roles:

| Role | Ask Questions | Trigger Ingestion | Run Evaluation | Promote Index | View Logs |
|---|---:|---:|---:|---:|---:|
| demo_user | Yes | No | No | No | No |
| admin | Yes | Yes | Yes | Yes | Yes |

## 6. Rate Limiting

Recommended defaults:

```text
demo_user: 30 queries/hour
admin: 100 queries/hour
anonymous: disabled
```

## 7. Source Domain Allowlist

Only approved official domains may be ingested.

Initial allowlist:

```text
developers.openai.com
platform.claude.com
docs.anthropic.com
code.claude.com
ai.google.dev
```

## 8. Prompt Injection Controls

1. Treat retrieved documentation as untrusted data.
2. Never allow retrieved text to override system policy.
3. Do not execute instructions found in documentation chunks.
4. Apply citation validation after generation.
5. Refuse answers when evidence is weak.

## 9. Logging and Redaction

Logs should redact common secret patterns:

1. API keys.
2. Bearer tokens.
3. Private keys.
4. Password-like fields.
5. Long high-entropy strings.

Do not log full retrieved context unless explicitly enabled in a local development environment.

## 10. Admin Endpoint Controls

Admin endpoints require admin API key and should be audited.

Protected actions:

1. Trigger ingestion.
2. Run evaluation.
3. Promote index.
4. View logs.
5. View ingestion errors.

## 11. CORS Policy

MVP should allow only the approved frontend origin.

Do not use wildcard CORS in shared demo environments.

## 12. Input Limits

Recommended limits:

```text
max_query_length: 4000 characters
max_session_messages: 30
session_ttl: 2 hours
max_retrieved_chunks: 12
max_answer_tokens: configured per model
```

## 13. Security Audit Events

Audit these actions:

1. Login.
2. Ask question.
3. Unsupported query.
4. Rate limit triggered.
5. Ingestion started.
6. Ingestion failed.
7. Evaluation run.
8. Index promoted.
9. Admin auth failure.

## 14. MVP Security Limitations

MVP does not support:

1. SSO.
2. Enterprise RBAC.
3. Tenant isolation.
4. Chunk-level ACL.
5. Private document ingestion.
6. Compliance retention policies.
7. Legal hold.
8. Customer-managed keys.

## 15. Enterprise Security Roadmap

1. SSO.
2. RBAC.
3. ABAC.
4. Tenant isolation.
5. Chunk-level ACL.
6. Private source connectors.
7. Audit exports.
8. Data retention controls.
9. Compliance dashboards.
10. Customer-specific encryption policies.

## 16. Security Release Gates

Do not release if:

1. Anonymous access is enabled accidentally.
2. Admin endpoints work without admin key.
3. Prompt injection test cases pass into answer policy.
4. Logs expose secrets.
5. Unsupported domain guardrail fails.
6. Cache can serve source-less factual answers.
