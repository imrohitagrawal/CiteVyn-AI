# Database ERD

## Purpose

Show the primary database entities and relationships for CiteVyn MVP.

## Scope

This ERD covers product, retrieval, cache, evaluation, ingestion, audit, and index-versioning data. It is optimized for architecture review, not final DDL.

## Saved File Path

`diagrams/05-data-model-erd.md`

## Mermaid Diagram

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : starts
    USERS ||--o{ AUDIT_EVENTS : performs

    SESSIONS ||--o{ MESSAGES : contains
    MESSAGES ||--o{ RETRIEVED_EVIDENCE : produces

    INDEX_VERSIONS ||--o{ DOCUMENTS : includes
    DOCUMENTS ||--o{ CHUNKS : contains
    DOCUMENTS ||--o{ EXACT_TERMS : defines
    CHUNKS ||--o{ EXACT_TERMS : contains
    CHUNKS ||--o{ RETRIEVED_EVIDENCE : retrieved_as

    INDEX_VERSIONS ||--o{ EVALUATION_RUNS : validated_by
    EVALUATION_RUNS ||--o{ EVALUATION_RESULTS : records
    EVALUATION_CASES ||--o{ EVALUATION_RESULTS : evaluated_in

    INGESTION_JOBS ||--o{ INDEX_VERSIONS : builds

    USERS {
        string user_id PK
        string role
        datetime created_at
    }

    SESSIONS {
        string session_id PK
        string user_id FK
        string channel
        string current_product_area
        text summary
        datetime created_at
        datetime expires_at
    }

    MESSAGES {
        string message_id PK
        string session_id FK
        string role
        text content
        text normalized_query
        string domain
        string intent
        datetime created_at
    }

    DOCUMENTS {
        string document_id PK
        string index_version FK
        string source_name
        string product_area
        string source_url
        string title
        string content_checksum
        datetime last_fetched_at
        datetime last_indexed_at
        string status
    }

    CHUNKS {
        string chunk_id PK
        string document_id FK
        string product_area
        string section_path
        string heading
        string parent_heading
        text chunk_text
        text context_summary
        string content_checksum
        int chunk_order
    }

    EXACT_TERMS {
        string term_id PK
        string term_text
        string term_type
        string product_area
        string document_id FK
        string chunk_id FK
    }

    RETRIEVED_EVIDENCE {
        string evidence_id PK
        string message_id FK
        string chunk_id FK
        int rank
        float score
        string retrieval_type
        boolean used_in_answer
    }

    ANSWER_CACHE {
        string cache_key PK
        text normalized_question
        string product_area
        text answer
        string source_version_hash
        string answer_policy_version
        string confidence
        datetime ttl_expires_at
        datetime created_at
        datetime last_used_at
    }

    EVALUATION_CASES {
        string case_id PK
        text question
        string expected_domain
        string expected_intent
        string expected_behavior
    }

    EVALUATION_RUNS {
        string run_id PK
        string suite_name
        string index_version FK
        datetime started_at
        datetime completed_at
        string status
    }

    EVALUATION_RESULTS {
        string result_id PK
        string run_id FK
        string case_id FK
        string status
        float score
        text failure_reason
    }

    INGESTION_JOBS {
        string job_id PK
        string source_name
        string status
        string stage
        datetime started_at
        datetime completed_at
        string error_type
        boolean retryable
    }

    INDEX_VERSIONS {
        string index_version PK
        string status
        string source_version_hash
        datetime created_at
        datetime promoted_at
    }

    AUDIT_EVENTS {
        string event_id PK
        string user_id FK
        string role
        string action
        string resource_type
        string resource_id
        datetime timestamp
    }
```

## Short Explanation

The model separates source documents, chunks, exact terms, conversations, retrieval evidence, cache, ingestion jobs, evaluation, audit events, and versioned indexes. This supports reliable retrieval, traceable answers, and safe index promotion.

## Key Assumptions

1. PostgreSQL stores metadata, sessions, traces, evaluations, audit events, and cache metadata.
2. pgvector stores or indexes embeddings associated with chunks.
3. Candidate indexes are versioned before promotion.
4. Exact terms are separate from chunks for reliable lookup.
5. Evaluation results are linked to index versions.

## Open Questions

1. Should embeddings be stored in the `CHUNKS` table or a separate embedding table?
2. Should `ANSWER_CACHE` citations be normalized into a separate cache-citation table later?
3. Should MVP model users as a real table or use demo-user identifiers only?
