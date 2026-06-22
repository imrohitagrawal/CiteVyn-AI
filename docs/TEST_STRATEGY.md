# CiteVyn Test Strategy

## 1. Purpose

This document defines the MVP testing strategy for CiteVyn.

The system is not considered ready because the API works. It is ready only when retrieval, citations, no-answer behavior, and guardrails pass measurable gates.

## 2. Testing Principles

1. Tests must protect product quality, not implementation convenience.
2. Tests must not be weakened to make current code pass.
3. Factual answers require citations.
4. Unsupported questions must be refused.
5. Retrieval correctness must be measured separately from answer wording.
6. Exact lookup must be tested separately from semantic retrieval.
7. Follow-up context must not contaminate product areas.

## 3. Test Layers

### 3.1 Unit Tests

Cover:

1. Query normalization.
2. Domain classification.
3. Intent classification.
4. Cache key generation.
5. Exact term extraction.
6. Chunk metadata generation.
7. Citation formatting.
8. No-answer response generation.

### 3.2 Integration Tests

Cover:

1. Ingestion pipeline.
2. Database schema.
3. Vector search.
4. Keyword search.
5. Exact lookup.
6. Cache reads/writes.
7. API endpoints.
8. Admin endpoints.

### 3.3 Retrieval Tests

Each retrieval test should define:

1. Question.
2. Expected product area.
3. Expected document or chunk.
4. Forbidden chunks.
5. Expected retrieval strategy.

### 3.4 Answer Quality Tests

Evaluate:

1. Faithfulness.
2. Citation correctness.
3. Completeness.
4. Refusal correctness.
5. Step-by-step behavior.
6. No unsupported claims.

### 3.5 Security Tests

Cover:

1. Anonymous access blocked.
2. Admin endpoints protected.
3. Rate limiting.
4. Prompt injection attempts.
5. Secret redaction.
6. Source allowlist enforcement.

### 3.6 Deployment Tests

Cover:

1. Health endpoints.
2. Active index availability.
3. Last-known-good fallback.
4. Environment variable validation.
5. Cost-limit behavior.

## 4. MVP Release Gates

| Metric | Required Score |
|---|---:|
| Domain guardrail accuracy | 100% on critical unsupported cases |
| Retrieval hit rate | >=95% |
| Citation correctness | >=95% |
| Answer faithfulness | >=95% |
| No-answer correctness | >=95% |
| Exact lookup accuracy | >=95% |
| Follow-up context correctness | >=90% |
| Cache correctness | >=95% |
| End-to-end golden pass rate | >=95% |

## 5. Golden Dataset

Minimum 50 questions:

| Category | Count |
|---|---:|
| Codex usage | 10 |
| Claude usage | 8 |
| Claude Code usage | 10 |
| Gemini usage | 8 |
| Exact lookup | 6 |
| Multi-doc how-to | 3 |
| Follow-up questions | 2 |
| Unsupported/out-of-domain | 2 |
| No-answer/weak-evidence | 1 |

## 6. Golden Case Format

```yaml
case_id: golden_001
question: "How do I configure Claude Code permissions?"
expected_domain: "claude_code"
expected_intent: "how_to"
expected_behavior: "answer"
expected_sources:
  - "Claude Code permissions documentation"
required_answer_points:
  - "mentions permission configuration"
  - "does not invent unsupported modes"
forbidden_answer_points:
  - "claims unsupported admin feature"
```

## 7. Test Governance Rule

Tests must not be changed to make current implementation pass.

A test can change only when:

1. Official documentation changed.
2. Product scope changed.
3. Expected behavior was wrongly specified.
4. Test data became stale.
5. Product owner explicitly approves the change.

Every test change must include:

```text
old expectation
new expectation
reason
source evidence
approval note
impact on metrics
```

## 8. Required Negative Tests

1. Unsupported product question.
2. General AI opinion question.
3. Pricing question not in indexed docs.
4. Future roadmap question.
5. Prompt injection inside user query.
6. Prompt injection inside retrieved document.
7. Secret-looking input.
8. Ambiguous product reference.
9. No matching source evidence.
10. Exact flag that does not exist.

## 9. No-Answer Tests

The system must say:

> I could not find credible information in the indexed official documentation to answer this reliably.

when evidence is weak inside supported scope.

## 10. Unsupported Tests

The system must say:

> I can answer questions about Claude, Claude Code, Codex, and Gemini using indexed official documentation. I do not have credible source material in this assistant to answer that.

when the question is out of scope.

## 11. Open Questions

1. Who owns the final golden dataset?
2. Which evaluator model or rules will be used?
3. How will citation correctness be judged?
4. How often will regression tests run?
5. Will evaluation run on every candidate index?
