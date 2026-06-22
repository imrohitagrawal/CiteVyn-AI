# CiteVyn Data Model

## 1. Purpose

This document defines the MVP data model for CiteVyn.

The model supports:

1. Official documentation ingestion.
2. Contextual chunks.
3. Exact term lookup.
4. Sessions and messages.
5. Retrieval evidence.
6. Answer cache.
7. Evaluation runs.
8. Audit events.
9. Index versioning.

## 2. Core Entities

```text
documents
chunks
exact_terms
sessions
messages
retrieved_evidence
answer_cache
evaluation_cases
evaluation_runs
audit_events
index_versions
ingestion_jobs
```

## 3. documents

Represents an official documentation page or file.

| Field | Type | Notes |
|---|---|---|
| document_id | UUID | Primary key |
| source_name | text | codex, claude_api, claude_code, gemini_api |
| product_area | text | Product area classification |
| source_url | text | Official source URL |
| title | text | Document title |
| content_checksum | text | Hash of normalized content |
| last_fetched_at | timestamp | Last fetch time |
| last_indexed_at | timestamp | Last successful index time |
| status | text | active, failed, deprecated |

## 4. chunks

Represents a contextual retrievable unit.

| Field | Type | Notes |
|---|---|---|
| chunk_id | UUID | Primary key |
| document_id | UUID | FK to documents |
| product_area | text | Product area |
| section_path | text | Hierarchical heading path |
| heading | text | Current heading |
| parent_heading | text | Parent heading |
| chunk_text | text | Chunk content |
| context_summary | text | Small surrounding context |
| exact_terms | jsonb | Extracted terms |
| embedding_id | UUID | FK or reference to embedding |
| chunk_order | integer | Order within document |
| content_checksum | text | Hash for invalidation |

## 5. exact_terms

Supports exact lookup for flags, commands, config keys, and similar terms.

| Field | Type | Notes |
|---|---|---|
| term_id | UUID | Primary key |
| term_text | text | Exact term |
| term_type | text | flag, command, config_key, etc. |
| product_area | text | Product area |
| document_id | UUID | FK to documents |
| chunk_id | UUID | FK to chunks |

Term types:

```text
flag
command
config_key
model_name
api_parameter
error_message
environment_variable
file_name
slash_command
```

## 6. sessions

Stores bounded conversation sessions.

| Field | Type | Notes |
|---|---|---|
| session_id | UUID | Primary key |
| user_id | text | Demo user ID |
| channel | text | chat |
| summary | text | Bounded session summary |
| current_product_area | text | Last resolved product area |
| created_at | timestamp | Created time |
| expires_at | timestamp | Expiration time |

## 7. messages

Stores user and assistant messages.

| Field | Type | Notes |
|---|---|---|
| message_id | UUID | Primary key |
| session_id | UUID | FK to sessions |
| role | text | user or assistant |
| content | text | Message text |
| normalized_query | text | Normalized form |
| domain | text | Product/domain classification |
| intent | text | faq, exact_lookup, how_to, etc. |
| created_at | timestamp | Created time |

## 8. retrieved_evidence

Stores retrieval trace.

| Field | Type | Notes |
|---|---|---|
| evidence_id | UUID | Primary key |
| message_id | UUID | FK to messages |
| chunk_id | UUID | FK to chunks |
| rank | integer | Rank after reranking |
| score | numeric | Retrieval/rerank score |
| retrieval_type | text | exact, keyword, vector, hybrid |
| used_in_answer | boolean | Whether cited or used |

## 9. answer_cache

Stores safe cached answers.

| Field | Type | Notes |
|---|---|---|
| cache_key | text | Primary key |
| normalized_question | text | Normalized question |
| product_area | text | Product area |
| answer | text | Cached answer |
| citations | jsonb | Required citations |
| source_version_hash | text | Index/source version |
| answer_policy_version | text | Policy version |
| confidence | text | high, medium, low |
| ttl_expires_at | timestamp | Expiration |
| created_at | timestamp | Created time |
| last_used_at | timestamp | Last hit |

## 10. evaluation_cases

Stores golden test cases.

| Field | Type | Notes |
|---|---|---|
| case_id | UUID | Primary key |
| question | text | Test question |
| expected_domain | text | Expected product area |
| expected_intent | text | Expected intent |
| expected_sources | jsonb | Expected docs/chunks |
| required_answer_points | jsonb | Must include |
| forbidden_answer_points | jsonb | Must not include |
| expected_behavior | text | answer, no_answer, unsupported, clarify |

## 11. evaluation_runs

Stores evaluation results.

| Field | Type | Notes |
|---|---|---|
| run_id | UUID | Primary key |
| suite_name | text | mvp_golden_50 |
| index_version | text | Candidate index |
| started_at | timestamp | Start time |
| completed_at | timestamp | End time |
| status | text | running, passed, failed |
| metrics | jsonb | Score details |
| failure_summary | jsonb | Failed cases |

## 12. audit_events

Stores security and operational audit events.

| Field | Type | Notes |
|---|---|---|
| event_id | UUID | Primary key |
| user_id | text | Actor |
| role | text | demo_user or admin |
| action | text | ask_question, trigger_ingestion, promote_index |
| resource_type | text | session, message, index, job |
| resource_id | text | Resource ID |
| timestamp | timestamp | Event time |
| metadata | jsonb | Redacted metadata |

## 13. ingestion_jobs

Stores ingestion pipeline status.

| Field | Type | Notes |
|---|---|---|
| job_id | UUID | Primary key |
| source_name | text | codex, claude_api, etc. |
| status | text | pending, running, completed, failed |
| stage | text | fetching, parsing, chunking, embedding, indexing |
| started_at | timestamp | Start time |
| completed_at | timestamp | End time |
| error_type | text | Optional |
| error_message | text | Sanitized |
| retryable | boolean | Retry flag |

## 14. index_versions

Supports candidate index and rollback.

| Field | Type | Notes |
|---|---|---|
| index_version | text | Primary key |
| status | text | candidate, active, previous_good, failed |
| source_version_hash | text | Combined source hash |
| created_at | timestamp | Created time |
| promoted_at | timestamp | Promotion time |
| evaluation_run_id | UUID | FK to evaluation_runs |

## 15. Indexing Recommendations

1. Index `documents.source_name`.
2. Index `documents.product_area`.
3. Index `chunks.product_area`.
4. Full-text index `chunks.chunk_text`.
5. Vector index embeddings.
6. Unique index on `exact_terms.term_text + product_area + chunk_id`.
7. Index `answer_cache.cache_key`.
8. Index `messages.session_id`.
9. Index `retrieved_evidence.message_id`.
