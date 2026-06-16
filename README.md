# CiteVyn AI

**Production-grade MVP: Citation-backed Q&A system** answering questions about Claude, Codex, and Gemini using official documentation.

- 🎯 **Mission**: Trustworthy AI answers backed by official sources (no hallucinations)
- 🏗️ **Architecture**: 5-layer system (UI → API → Logic → Data → Observability)
- 📦 **Slices**: Incremental, independently deployable phases
- 🛠️ **Tech Stack**: FastAPI, PostgreSQL, Vector Search, Claude API, Tailwind + shadcn
- 🤖 **Copilot Skills**: 85 AI skills integrated for engineering, PM, and design workflows

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Git
- GitHub account (for Copilot skills)

### Setup

1. **Clone repository**
   ```bash
   git clone https://github.com/imrohitagrawal/CiteVyn-AI.git
   cd CiteVyn-AI
   ```

2. **Install Copilot skills** (one-time setup)
   ```bash
   ./scripts/install-skills.sh
   ```
   This installs 85 AI skills across 3 domains (engineering, PM, UI/UX).
   
   See `scripts/README.md` for details.

3. **Setup backend**
   ```bash
   cd backend
   uv sync           # Install dependencies
   uv run pytest     # Run tests
   ```

4. **Start development server** (optional)
   ```bash
   uv run uvicorn app.main:app --reload
   ```

## 📚 Documentation

### Quick Reference
- **`.github/SKILLS_MANIFEST.md`** — Complete skills reference (85 skills, 0 conflicts)
- **`.github/REPOSITORY_OVERVIEW.md`** — Project architecture and roadmap
- **`.github/copilot-instructions.md`** — Copilot Chat guidelines

### Project Documentation
- **`docs/PRD.md`** — Product requirements and user journeys
- **`docs/ARCHITECTURE.md`** — System design with 7 components, 5 layers
- **`diagrams/`** — Mermaid diagrams for architecture
- **`backend/README.md`** — Backend setup and API docs

### Development
- **`scripts/`** — Automation scripts (skills installation)
- **`.github/agents/`** — 4 custom Copilot agents
- **`VALIDATION.md`** — Quality gates and validation rules
- **`AGENTS.md`** — Development operating model and engineering rules

## 🛠️ Copilot Skills

### What Are Skills?
Skills are AI agents that enhance GitHub Copilot Chat with specialized knowledge for:
- **Engineering** (10 skills) — TDD, security, code review, CI/CD, performance
- **PM** (68 skills) — Product discovery, strategy, go-to-market
- **UI/UX** (7 skills) — Design systems, branding, components

### Installation
```bash
./scripts/install-skills.sh  # Installs all 85 skills
```

### Usage Examples

**Engineering Workflows:**
```bash
@code-reviewer Review this PR for security vulnerabilities
@test-engineer Write tests for authentication feature
/spec Create specification for Slice 2 database design
```

**PM Workflows:**
```bash
/discover What are user pain points in citation systems?
/strategy Define go-to-market strategy for CiteVyn AI
/write-prd Create product requirements document
```

**UI/UX Workflows:**
```bash
/design-system Generate design tokens for Tailwind CSS
/brand Define brand guidelines and visual identity
```

## 📊 Project Status

### ✅ Slice 1: Completed
- FastAPI foundation (~168 LOC)
- Health check endpoints
- Request ID tracking
- Log redaction for secrets
- Test suite (~172 LOC)
- 100% test coverage

### 🔄 Slice 2: Ready to Start
- Database schema (PostgreSQL)
- ORM models (SQLAlchemy)
- Vector search integration
- Document ingestion pipeline

### 📋 Roadmap
- **Slice 3:** Guardrails + Intent router + Retrieval
- **Slice 4:** LLM generation + Citation tracking
- **Slice 5:** Evaluation framework + Quality metrics

## 🧪 Testing

```bash
cd backend

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test
uv run pytest tests/test_health.py
```

## 🔒 Security

### Built-in Security
- ✅ API key authentication (demo mode)
- ✅ Request ID tracking
- ✅ Log redaction for secrets
- ✅ Error handling (no stack traces in production)
- ✅ Input validation (Pydantic models)

### Production Checklist
- [ ] Replace demo API key with OAuth/OIDC
- [ ] Enable HTTPS
- [ ] Configure rate limiting
- [ ] Set up secrets vault (HashiCorp Vault, AWS Secrets Manager)
- [ ] Enable query logging and monitoring
- [ ] Configure database backups

See `docs/ARCHITECTURE.md` for security model details.

## 📈 Architecture

```
┌─────────────────────────────────────────────────────────┐
│ 1. Web UI (Chat Interface)                              │
├─────────────────────────────────────────────────────────┤
│ 2. API Gateway (FastAPI + Request Tracking)             │
├─────────────────────────────────────────────────────────┤
│ 3. Business Logic (Guardrail → Router → Retrieval)     │
├─────────────────────────────────────────────────────────┤
│ 4. Data (PostgreSQL + Vector Search + Document Store)  │
├─────────────────────────────────────────────────────────┤
│ 5. Observability (Logging, Metrics, Evaluation)         │
└─────────────────────────────────────────────────────────┘
```

See `docs/ARCHITECTURE.md` for full architecture details and diagrams.

## 🔧 Configuration

### Environment Variables (Backend)

Create `.env` file in `backend/` (not committed):

```bash
# FastAPI
ENVIRONMENT=development
DEBUG=true

# API Auth (demo)
DEMO_API_KEY=your-secret-key-here

# Database (Slice 2)
DATABASE_URL=postgresql://user:pass@localhost/citevyn_db

# Vector Search
VECTOR_SEARCH_URL=http://localhost:6333

# Claude API (Slice 4)
CLAUDE_API_KEY=sk-ant-...

# Observability
LOG_LEVEL=INFO
SENTRY_DSN=https://...
```

See `backend/README.md` for full configuration details.

## 🎯 Engineering Standards

This project follows production-grade engineering practices:

1. **Spec-driven** — Requirements documented first
2. **Test-driven** — Tests drive implementation (TDD)
3. **Quality-gated** — Lint, type check, tests, review before merge
4. **Incrementally deployed** — Each slice independently valuable
5. **Production-shaped** — Not a prototype, production-ready from day 1

See `AGENTS.md` for development operating model.

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes following `VALIDATION.md`
3. Run tests: `uv run pytest`
4. Run linting: `uv run ruff check backend/app`
5. Type check: `uv run pyright backend/app`
6. Create PR with description
7. Request Copilot review: Use `/review` in PR description
8. Merge after approval

## 📞 Support

- **Questions?** Check `.github/REPOSITORY_OVERVIEW.md`
- **Stuck on setup?** See `backend/README.md`
- **Need skills reference?** See `.github/SKILLS_MANIFEST.md`
- **Architecture questions?** See `docs/ARCHITECTURE.md`

## 📄 License

MIT License — See `LICENSE` file (when added)

## 🎉 Next Steps

1. ✅ **Skills installed** — `./scripts/install-skills.sh`
2. 🔄 **Backend setup** — `cd backend && uv sync`
3. 📋 **Plan Slice 2** — Use PM `/discover` and `/strategy` skills
4. 🎨 **Design system** — Use UI/UX `/design-system` skill
5. 🧪 **Build Slice 2** — Database + vector search + ingestion (with TDD)

---

**Version:** 0.1.0 (Slice 1 Complete)  
**Last Updated:** 2026-06-17  
**Repository:** https://github.com/imrohitagrawal/CiteVyn-AI
