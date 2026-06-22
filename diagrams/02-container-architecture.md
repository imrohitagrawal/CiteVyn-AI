# Container Architecture Diagram

## Purpose

Show the major deployable containers, data stores, external dependencies, and runtime boundaries for the CiteVyn MVP.

## Scope

This diagram covers the MVP container-level architecture. It does not show internal backend classes or functions.

## Saved File Path

`diagrams/02-container-architecture.md`

## Mermaid Diagram

```mermaid
flowchart TD
    browser[User Browser]
    adminBrowser[Admin Browser]

    subgraph edge["Client Boundary"]
        web[Web Chat UI]
    end

    subgraph app["Application Boundary"]
        api[Backend API]
        worker[Ingestion Worker]
        evaluator[Evaluation Runner]
    end

    subgraph data["Data Stores"]
        pg[PostgreSQL and pgvector]
        redis[Redis Cache]
    end

    subgraph observability["Observability"]
        logSink[Structured Logs]
        dashboard[Dashboard]
    end

    subgraph official["Official Sources"]
        codex[Codex Docs]
        claude[Claude Docs]
        claudeCode[Claude Code Docs]
        gemini[Gemini Docs]
    end

    subgraph ai["AI Model APIs"]
        llm[Generation Model]
        embed[Embedding Model]
    end

    browser --> web
    adminBrowser --> web
    web -->|HTTPS API calls| api

    api -->|Read and write metadata| pg
    api -->|Cache and rate limits| redis
    api -->|Generate answers| llm
    api -->|Embed queries| embed

    api -->|Start jobs| worker
    api -->|Start evals| evaluator

    worker -->|Fetch docs| codex
    worker -->|Fetch docs| claude
    worker -->|Fetch docs| claudeCode
    worker -->|Fetch docs| gemini
    worker -->|Store docs and chunks| pg
    worker -->|Create embeddings| embed

    evaluator -->|Read golden cases| pg
    evaluator -->|Evaluate responses| llm
    evaluator -->|Store results| pg

    api --> logSink
    worker --> logSink
    evaluator --> logSink
    logSink --> dashboard
    pg --> dashboard
```

## Short Explanation

The MVP uses a simple but production-shaped set of containers: web UI, backend API, ingestion worker, evaluation runner, PostgreSQL with pgvector, Redis, and observability. Official documentation fetching happens only through the ingestion worker. User requests flow through the backend API.

## Key Assumptions

1. Docker Compose is the default MVP deployment model.
2. PostgreSQL with pgvector is sufficient for MVP scale.
3. Redis supports both cache and rate-limit state.
4. Evaluation is separated from normal request handling.
5. Model providers remain external services in MVP.

## Open Questions

1. Should the evaluator run as a separate container or an admin job in the worker?
2. Should Redis be mandatory for all environments or optional for local development?
3. Will the frontend be React, Next.js, or a simpler static UI?
