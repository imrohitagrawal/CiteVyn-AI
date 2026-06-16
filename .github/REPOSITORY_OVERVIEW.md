# CiteVyn AI Repository Overview

## 📋 Project Summary

**CiteVyn AI** is a **trusted AI-tool usage assistant** that answers questions exclusively from official documentation with citations.

### Problem Statement
Users of Claude, Claude Code, Codex, and Gemini need reliable answers about tool configuration, commands, flags, and workflows. Official documentation is fragmented across vendors. Generic chatbots answer confidently without evidence and hallucinate.

### Solution
CiteVyn AI ingests **only official documentation**, retrieves relevant sources, generates short answers, and returns citations. No hallucinations.

### Target MVP Users
- Developers using Claude Code, Codex, or Gemini
- AI-tool users looking for official guidance
- Engineers comparing behavior across tools
- Technical learners wanting reliable, cited answers

---

## 🎯 Project Goals

**Core Goals:**
1. Answer from official documentation only
2. Require citations for all factual answers
3. Avoid hallucinated or unsupported answers
4. Support exact lookup (flags, commands, config keys, errors, env vars)
5. Support follow-up questions with bounded context
6. Cache safe answers before expensive LLM calls
7. Provide observability into retrieval, quality, cost
8. Build a 50-question golden evaluation suite

**Non-MVP Goals (Future):**
- ChatGPT, Cursor support
- Voice input/output
- Private documentation
- Enterprise RBAC
- Multi-tenant isolation
- General web search

---

## 📁 Repository Structure

```
citevyn-ai/
├── backend/                     # FastAPI service (Python)
│   ├── app/
│   │   ├── main.py             # App factory, router setup
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic settings
│   │   │   ├── logging.py       # Log redaction, formatting
│   │   │   ├── middleware.py    # Request ID middleware
│   │   │   └── security.py      # API key auth, demo auth
│   │   └── api/
│   │       └── routes/
│   │           └── health.py    # Health, dependencies, index
│   ├── tests/                   # pytest test suite
│   │   ├── test_health.py
│   │   ├── test_security.py
│   │   ├── test_request_id.py
│   │   ├── test_log_redaction.py
│   │   └── conftest.py
│   ├── pyproject.toml           # uv project config, dependencies
│   ├── uv.lock                  # Dependency lock file
│   └── README.md
│
├── docs/                        # Architecture & design
│   ├── PRD.md                   # Product requirements (11 sections)
│   ├── ARCHITECTURE.md          # System design, components
│   ├── API_SPEC.md              # API endpoints (planned)
│   ├── DATA_MODEL.md            # Data structures
│   ├── SECURITY_MODEL.md        # Auth, data protection
│   ├── TEST_STRATEGY.md         # Testing approach
│   ├── OBSERVABILITY.md         # Logging, metrics
│   ├── RELEASE_PLAN.md          # Timeline & milestones
│   └── ADR/
│       └── 0001-core-architecture.md
│
├── diagrams/                    # Architecture diagrams (Mermaid)
│   ├── 01-system-context.md     # External systems, trust boundaries
│   ├── 02-container-architecture.md  # Deployment containers
│   ├── 03-backend-component-architecture.md  # Internal services
│   ├── 04-main-request-sequence.md   # Q&A flow
│   ├── 05-data-model-erd.md     # Database schema
│   ├── 06-deployment-architecture.md # Prod topology
│   ├── 07-observability-and-alerting-flow.md
│   └── README.md
│
├── .github/                     # GitHub config + installed skills
│   ├── skills/                  # Engineering skills (10)
│   ├── agents/                  # Specialized agents (4)
│   ├── pm-skills/               # PM skills (68)
│   ├── ui-ux-skills/            # UI/UX skills (7)
│   ├── copilot-instructions.md  # Copilot guidelines
│   └── SKILL_CONFLICT_ANALYSIS.md
│
├── AGENTS.md                    # Project operating model
├── VALIDATION.md                # Architecture validation checklist
├── .gitignore
└── .git/

```

---

## 🔄 Git Workflow & Branches

### Current Branch
- **`agents/install-agent-skills-addon`** ← You are here
  - Latest: Installed UI/UX Pro Max skills + conflict analysis
  - Base: `main`

### Other Branches
- **`main`** (5 commits) — Base branch for production-ready changes
  - Slice 1 backend foundation
  - Architecture documentation
  - System diagrams

- **`slice-2-db-persistence`** (planned) — Next slice
  - Database setup, ORM models
  - Vector search integration
  - Ingestion pipeline

### Recent Commit History (Current Branch)
```
19faef4 Session checkpoint turn 4 (UI/UX skills conflict analysis)
1c3bd33 Session checkpoint turn 3 (UI/UX skills installed)
ba0d9b5 Session checkpoint turn 2 (PM skills installed)
3f5933c Session checkpoint turn 1 (Engineering skills installed)
ecacd9d Session checkpoint turn 0 (Branch start)
c9494d4 Install UI/UX Pro Max skills (173 files +23,547 lines)
0aaea8f Install 68 PM skills (129 files +11,287 lines)
33a7451 Install 10 engineering skills (15 files +3,781 lines)
51ec350 Add Slice 1 backend foundation
c5fed4c Add architecture documentation & diagrams
```

---

## 🏗️ Architecture & Components

### Slices Approach
The project uses **incremental slices** to build production-grade MVP:

**Slice 1** ✅ (COMPLETE)
- FastAPI foundation
- Health endpoints
- Request ID middleware
- Demo API key auth
- Log redaction
- Testing infrastructure (pytest, ruff, pyright)

**Slice 2** (PLANNED)
- Database persistence (PostgreSQL)
- Vector search (pgvector, Milvus, or Weaviate)
- Documentation ingestion pipeline
- Session management
- ORM models

**Slice 3** (PLANNED)
- Domain guardrail (product classifier)
- Intent router (FAQ cache, exact lookup, retrieval)
- Hybrid retrieval engine (BM25, vector, reranking)

**Slice 4** (PLANNED)
- LLM integration (generation, citations)
- Answer formatting
- Confidence scoring

**Slice 5** (PLANNED)
- Evaluation framework
- Golden evaluation suite (50 questions)
- Quality metrics

### Key Architectural Components

1. **Web Chat UI** — Simple web interface (not yet built)
2. **API Gateway** — FastAPI service with auth & rate limiting
3. **Demo Auth** — API key validation, role checks
4. **Domain Guardrail** — Query classifier (Claude API, Claude Code, Codex, Gemini)
5. **Intent Router** — Routes to: FAQ cache, exact lookup, hybrid retrieval, clarification
6. **Session Manager** — Bounded conversation context, prevents cross-product contamination
7. **Retrieval Engine** — Hybrid: exact term index + keyword + vector + reranking
8. **Answer Generator** — LLM-based generation with citations
9. **Observability** — Request tracing, metrics, cost tracking

### Supported Documentation Sources (MVP)
- Claude API docs
- Claude Code docs
- Codex docs
- Gemini API docs

---

## 💻 Backend Implementation

### Tech Stack
- **Framework**: FastAPI (Python 3.12+)
- **Package Manager**: uv (fast, deterministic)
- **Testing**: pytest
- **Linting**: ruff
- **Type Checking**: pyright (strict mode)
- **Logging**: Structured JSON with redaction

### Current Implementation Status

**Lines of Code (Slice 1)**
- Total: ~168 lines (core infrastructure only)
- config.py: 22 lines
- logging.py: 65 lines
- middleware.py: 50 lines
- security.py: 29 lines

**Test Suite (Slice 1)**
- Total: ~172 lines
- test_health.py: Tests /health endpoints
- test_security.py: Tests API key auth
- test_request_id.py: Tests request ID middleware
- test_log_redaction.py: Tests log redaction

**Key Features (Current)**
- Request ID middleware for tracing
- Log redaction for secrets
- Demo API key authentication
- Health check endpoints (3 variants):
  - `/health` — Basic status
  - `/health/dependencies` — External dependency status
  - `/health/index` — Vector index status
- Environment-based configuration
- Structured logging with JSON output

### Local Development
```bash
cd backend
uv sync              # Install deps
uv run pytest        # Run tests
uv run ruff check .  # Lint
uv run pyright       # Type check
```

---

## 📊 Installed Skills (This Session)

### Engineering Skills (10)
From `addyosmani/agent-skills`:
- test-driven-development
- code-review-and-quality
- spec-driven-development
- planning-and-task-breakdown
- incremental-implementation
- debugging-and-error-recovery
- documentation-and-adrs
- security-and-hardening
- performance-optimization
- ci-cd-and-automation

### PM Skills (68)
From `phuryn/pm-skills` (9 plugins):
- pm-toolkit (4)
- pm-product-discovery (13)
- pm-product-strategy (12)
- pm-market-research (7)
- pm-data-analytics (3)
- pm-marketing-growth (5)
- pm-go-to-market (6)
- pm-execution (16)
- pm-ai-shipping (2)

### UI/UX Skills (7)
From `nextlevelbuilder/ui-ux-pro-max-skill`:
- ui-ux-pro-max (design system generator)
- ui-styling (Tailwind + shadcn/ui)
- design-system (tokens, patterns)
- design (principles, deliverables)
- brand (logo, color psychology)
- slides (presentation design)
- banner-design (web banners)

**Total: 85 complementary skills** (NO CONFLICTS)

---

## 🎯 What's Happening

### Current Status
1. **Project initialized** with architecture documentation and Slice 1 backend
2. **Skills infrastructure** installed and integrated:
   - 10 engineering skills for development workflows
   - 68 PM skills for product/strategy
   - 7 UI/UX skills for design systems
3. **Conflict analysis** completed — all skills are complementary
4. **Next step**: Begin Slice 2 implementation (database + ingestion)

### Current Branch Purpose
The `agents/install-agent-skills-addon` branch is **work in progress** to:
- ✅ Install and test all skill repositories
- ✅ Integrate with GitHub Copilot
- ✅ Analyze conflicts and compatibility
- ⏭️ Ready to merge to `main` after approval

### Development Methodology
The project follows **Addy Osmani's AI engineering skills**:
- **Spec-driven**: Requirements documented before coding
- **Test-driven**: Tests drive implementation
- **Incremental slices**: Small, verifiable units
- **Quality gates**: Every PR passes lint, type check, tests, review
- **Architectural decisions**: Recorded in ADRs

---

## 📈 Project Roadmap

**Slice 1** ✅ DONE
- Minimal FastAPI foundation
- Health endpoints
- Testing infrastructure

**Slice 2** → NEXT
- Database (PostgreSQL)
- Vector search integration
- Documentation ingestion
- Session management

**Slice 3** → FUTURE
- Domain guardrail (classifier)
- Intent router
- Hybrid retrieval

**Slice 4** → FUTURE
- LLM generation
- Citation formatting
- Confidence scoring

**Slice 5** → FUTURE
- Evaluation framework
- Golden evaluation suite
- Quality metrics

---

## 🔐 Security Model

**Current (Slice 1)**
- Demo API key authentication
- Request ID tracking for audit trails
- Log redaction for secrets, tokens, passwords
- Environment-based configuration (no hardcoded secrets)

**Planned (Future)**
- OAuth/OIDC for production auth
- Role-based access control (RBAC)
- Rate limiting
- Data encryption at rest
- Secrets vault integration

---

## 📝 Key Documentation

All files in `docs/` are comprehensive:
- **PRD.md** — Full product requirements (11 sections)
- **ARCHITECTURE.md** — System design and components
- **API_SPEC.md** — API endpoints (not yet filled)
- **DATA_MODEL.md** — Database schema (planned for Slice 2)
- **SECURITY_MODEL.md** — Auth, data protection, secrets
- **TEST_STRATEGY.md** — Testing approach, coverage goals
- **OBSERVABILITY.md** — Logging, metrics, alerts
- **RELEASE_PLAN.md** — Timeline and milestones

**Diagrams** (Mermaid format, saved in `diagrams/`):
1. System Context
2. Container Architecture
3. Backend Components
4. Main Request Sequence
5. Data Model (ERD)
6. Deployment Architecture
7. Observability & Alerting Flow

---

## 🚀 Next Steps (Recommendations)

1. **Review & Merge** — Review the skills installation on this branch
2. **Approve Copilot Integration** — Enable access to 85+ skills
3. **Plan Slice 2** — Use PM skills for discovery & planning
4. **Design System** — Use UI/UX skills to define design
5. **Implement with TDD** — Use engineering skills for quality gates
6. **Build Incrementally** — Each slice is independently deployable

---

## 📞 Key Contacts & Resources

**Repository**: This worktree (agents/install-agent-skills-addon)
**Base Branch**: main
**Documentation**: docs/ directory
**Diagrams**: diagrams/ directory
**Backend**: backend/ directory
**Skills**: .github/ directory

---

## Summary Table

| Aspect | Status | Details |
|--------|--------|---------|
| **Project Stage** | Slice 1 Complete | Foundation ready, next: DB & ingestion |
| **Backend Code** | ~168 LOC | Health, auth, logging infrastructure |
| **Tests** | ~172 LOC | pytest with config + test suite |
| **Documentation** | Complete | 8 core docs + 7 architecture diagrams |
| **Skills** | 85 installed | 10 eng + 68 PM + 7 UI/UX (ZERO conflicts) |
| **Architecture** | Designed | 7 major components, production-ready |
| **Current Branch** | WIP | Installing & testing skills integration |
| **Next Action** | Slice 2 Planning | DB, ORM, vector search, ingestion |

