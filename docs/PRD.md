# CiteVyn Product Requirements Document

## 1. Product Name

**CiteVyn**

## 2. Product Statement

**CiteVyn is a trusted AI-tool usage assistant that answers from official documentation, not guesses.**

## 3. MVP Positioning

CiteVyn MVP provides reliable, citation-backed answers for users of:

- Claude
- Claude Code
- Codex
- Gemini

The MVP uses official documentation only and avoids unsupported answers.

## 4. Problem Statement

AI-tool users increasingly rely on tools such as Claude, Claude Code, Codex, and Gemini, but official documentation is spread across multiple vendors, product surfaces, and documentation structures. Users frequently ask practical questions such as:

- How do I configure a tool?
- Which command, flag, model, or setting should I use?
- How do I perform a workflow under a specific constraint?
- What does an error or configuration option mean?
- Can I trust the answer?

A generic chatbot may answer confidently without reliable source evidence. CiteVyn solves this by answering only from indexed official documentation and returning citations.

## 5. Target Users

### MVP Users

- Developers using Claude Code, Codex, or Gemini.
- AI-tool users looking for official usage guidance.
- Engineers comparing official behavior across supported tools.
- Technical learners who want short, reliable answers with references.

### Non-MVP Users

- General ChatGPT users.
- Cursor users.
- Enterprise users with private documentation.
- Teams needing SSO, RBAC, or tenant isolation.
- Users expecting voice-based interaction.

## 6. Product Goals

1. Provide short, reliable answers from official documentation.
2. Support citations for all factual answers.
3. Avoid hallucinated or unsupported answers.
4. Support exact lookup for flags, commands, config keys, model names, errors, and environment variables.
5. Support follow-up questions with bounded session context.
6. Use cache before expensive LLM generation.
7. Provide observability into retrieval, answer quality, and cost.
8. Establish a 50-question golden evaluation suite before demo release.

## 7. Non-Goals for MVP

1. ChatGPT support.
2. Cursor support.
3. Voice input.
4. Voice output.
5. Private documentation ingestion.
6. Enterprise RBAC.
7. Multi-tenant isolation.
8. Automated reviewer-agent workflows.
9. General web search.
10. Slack, Teams, or browser-extension integration.

## 8. Supported MVP Sources

The MVP should support official documentation for:

| Product Area | Scope |
|---|---|
| Codex | OpenAI Codex official docs, preferably via `llms-full.txt` |
| Claude API | Anthropic Claude API documentation |
| Claude Code | Official Claude Code documentation |
| Gemini API | Google AI Gemini API documentation and developer-focused coding-agent docs where relevant |

## 9. Core User Journeys

### 9.1 Ask a Simple Usage Question

User asks:

> What is Claude Code?

Expected behavior:

1. Classify query as supported.
2. Retrieve official Claude Code documentation.
3. Generate a short answer.
4. Return citation.
5. Log trace.

### 9.2 Search an Exact Flag or Command

User asks:

> What does `--some-flag` do?

Expected behavior:

1. Detect exact lookup intent.
2. Search the exact term index first.
3. Fall back to keyword search if needed.
4. Return only source-supported answer.

### 9.3 Ask a Multi-Step How-To Question

User asks:

> How do I do X in Claude Code given constraint Y?

Expected behavior:

1. Classify product area.
2. Retrieve multiple relevant chunks.
3. Rerank evidence.
4. Generate concise steps with citations.
5. Avoid unsupported assumptions.

### 9.4 Ask a Follow-Up Question

User asks:

> What about Gemini?

Expected behavior:

1. Resolve context from previous session state.
2. Reclassify product area if needed.
3. Retrieve fresh evidence for Gemini.
4. Avoid carrying incorrect context across product areas.

### 9.5 Ask an Unsupported Question

User asks:

> What is the best laptop for AI coding?

Expected behavior:

Return:

> I can answer questions about Claude, Claude Code, Codex, and Gemini using indexed official documentation. I do not have credible source material in this assistant to answer that.

## 10. Functional Requirements

| ID | Requirement | MVP |
|---|---|---|
| FR-001 | Chat-based Q&A | Yes |
| FR-002 | Official documentation ingestion | Yes |
| FR-003 | Contextual chunking | Yes |
| FR-004 | Hybrid retrieval | Yes |
| FR-005 | Exact term lookup | Yes |
| FR-006 | Follow-up context | Yes |
| FR-007 | FAQ/cache routing | Yes |
| FR-008 | Citations on factual answers | Yes |
| FR-009 | No-answer fallback | Yes |
| FR-010 | Domain guardrail | Yes |
| FR-011 | Voice output | No |
| FR-012 | Voice input | No |
| FR-013 | Feedback capture | Deferred |
| FR-014 | Automated freshness | Deferred |
| FR-015 | Enterprise RBAC | Deferred |

## 11. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Reliability | Serve from last known good index when new indexing fails |
| Security | Demo auth, rate limiting, admin-only ingestion |
| Scalability | Cache before LLM; hybrid retrieval; avoid voice in MVP |
| Observability | Trace retrieval, citations, no-answer, latency, token usage, cost |
| Testability | 50-question golden dataset and multi-score release gates |
| Maintainability | Version-control-friendly docs, ADRs, clear component boundaries |

## 12. MVP Quality Gates

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

## 13. No-Answer Policy

For weak evidence inside supported scope:

> I could not find credible information in the indexed official documentation to answer this reliably.

For unsupported product/domain:

> I can answer questions about Claude, Claude Code, Codex, and Gemini using indexed official documentation. I do not have credible source material in this assistant to answer that.

For ambiguity:

> This could refer to more than one product area. Do you mean Claude API, Claude Code, Codex, or Gemini?

## 14. MVP Success Criteria

1. Users receive short answers with citations.
2. Unsupported questions are refused safely.
3. Exact lookup works for known flags, commands, and config keys.
4. Follow-up context works without cross-product contamination.
5. The golden evaluation suite passes release gates.
6. Ingestion failures do not corrupt the active index.
7. The demo has visible basic security and observability.

## 15. Enterprise Expansion

Enterprise scope should add:

1. ChatGPT official docs.
2. Cursor official docs.
3. Voice output and voice input.
4. Feedback capture.
5. Reviewer-agent workflow.
6. Scheduled source refresh.
7. SSO, RBAC, ABAC.
8. Tenant isolation.
9. Private source connectors.
10. Audit exports.
11. Compliance controls.
12. Slack and Teams integrations.
13. Browser extension.
14. Cost controls.
15. Multi-source governance.

## 16. Open Product Questions

1. Which exact source URLs are locked for MVP?
2. What is the final generation model?
3. What is the final embedding model?
4. What is the demo traffic expectation?
5. What is the final cost cap?
6. Who approves test modifications?
