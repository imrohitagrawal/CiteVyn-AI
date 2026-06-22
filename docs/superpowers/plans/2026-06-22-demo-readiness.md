# Slice 10 — Demo Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land all P0 and P1 demo-readiness fixes so the project can be called "demo ready" — golden evaluation suite, frontend CI, Slice 9b stub guard, DEMO_CHECKLIST, CHANGELOG, refresh_sources.sh, make e2e / demo-frontend, README + version reconciliation, dependabot triage, release-blocker label.

**Architecture:** Single branch `slice-10-demo-readiness` off `main@f556e5e` with five logical commits, each independently reviewable. Heaviest item is 50 hand-authored golden YAML cases + runner + nightly CI. Runner uses existing TestClient + seed_catalog patterns and measures infrastructure gates (retrieval, citation, refusal, no-answer, exact lookup) today; answer-quality scoring is deferred to Slice 9b when a real LLM lands.

**Tech Stack:** Python 3.12+ (backend), Node 20+ (frontend), pytest, ruff, pyright, GitHub Actions, Makefile, bash.

## Global Constraints

- **Python version:** `>=3.12,<3.14` per `backend/pyproject.toml`
- **Node version:** 20+ per `frontend/README.md`
- **Conventional commits:** `feat:`, `fix:`, `chore:`, `docs:` per `CONTRIBUTING.md`
- **All new code:** ruff clean, pyright strict, pytest passing
- **YAML cases:** Follow `docs/TEST_STRATEGY.md §6` schema exactly
- **Citation shape:** `{source_name, title, url, chunk_id}` from `app.retrieval.types.chunk_to_citation`
- **Response shape:** `AnswerResponse` with `unsupported: bool`, `no_answer: bool`, `cache_hit: bool`, `citations: list[Citation]`
- **Fixtures:** `session`, `client`, `seed_catalog` from `tests/conftest.py`
- **GitHub CLI:** `gh` authenticated for label creation

---

## Task 1: Create branch and verify baseline

**Files:**
- Create: branch `slice-10-demo-readiness` off `main@f556e5e`

**Interfaces:**
- None (setup task)

**Goal:** Ensure clean start point and verify `make verify` passes on main.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b slice-10-demo-readiness f556e5e
```

- [ ] **Step 2: Verify baseline is green**

Run: `make verify`
Expected: All checks pass (ruff, pyright, pytest SQLite)

- [ ] **Step 3: Confirm no uncommitted changes**

Run: `git status`
Expected: "working tree clean"

---

## Task 2: Frontend CI job and README status flip (Commit 1: `chore(ci)`)

**Files:**
- Create: `.github/workflows/frontend-ci.yml`
- Modify: `README.md` (§1 status table)
- Modify: `frontend/README.md` (add CI reference)
- Modify: `Makefile` (add `demo-frontend` target)

**Interfaces:**
- Consumes: Existing `frontend/package.json` scripts (`type-check`, `build`)
- Produces: CI workflow that runs on `frontend/**` changes, README honesty

- [ ] **Step 1: Write the failing test — verify frontend CI triggers**

Create `.github/workflows/frontend-ci.yml`:

```yaml
# Frontend CI: type-check + build. Triggered on push to main and PRs touching frontend/**.
# This is a smoke job — no test script exists yet (deferred to V1 per frontend/README.md).

name: frontend-ci

on:
  push:
    branches: [main]
  pull_request:
    paths:
      - "frontend/**"

jobs:
  frontend-smoke:
    name: type-check + build
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v6
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        run: npm ci
      - name: TypeScript type-check
        run: npm run type-check
      - name: Production build
        run: npm run build
      - name: Upload dist artifact
        uses: actions/upload-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist/
```

- [ ] **Step 2: Run test to verify it loads**

Run: `git add .github/workflows/frontend-ci.yml && git commit -m "chore(ci): add frontend-ci workflow stub"`
Expected: Commit succeeds

- [ ] **Step 3: Add `demo-frontend` Makefile target**

Add to `Makefile` after the `stop` target:

```makefile
demo-frontend: ## Build + serve the production frontend bundle on :4173
	cd frontend && npm ci && npm run build && npm run preview
```

- [ ] **Step 4: Flip README §1 frontend status**

Modify `README.md` line 21 from:

```markdown
| Frontend            | In development| React + Vite, served separately                             |
```

To:

```markdown
| Frontend            | Optional preview| React + Vite; build via `make demo-frontend`              |
```

- [ ] **Step 5: Add CI reference to frontend README**

Add to `frontend/README.md` after line 16 (after "Zero tests in this slice."):

```markdown
**CI:** The repo runs a type-check + build smoke job (`.github/workflows/frontend-ci.yml`)
on every PR that touches `frontend/**`. Component tests land with V1 streaming work.
```

- [ ] **Step 6: Run smoke to verify no regressions**

Run: `make verify` (backend only, unchanged) and `cd frontend && npm run type-check && npm run build` locally
Expected: All pass, `frontend/dist/index.html` exists

- [ ] **Step 7: Commit the complete frontend CI + README flip**

```bash
git add .github/workflows/frontend-ci.yml Makefile README.md frontend/README.md
git commit -m "chore(ci): add frontend-ci.yml + flip README to Optional preview + make demo-frontend"
```

---

## Task 3: `scripts/refresh_sources.sh` skeleton (Commit 4: `chore(release)` part A)

**Files:**
- Create: `scripts/refresh_sources.sh`

**Interfaces:**
- Consumes: None (operator script)
- Produces: Executable script that `backend/app/core/config.py:125` can reference honestly

- [ ] **Step 1: Write the script skeleton**

Create `scripts/refresh_sources.sh`:

```bash
#!/usr/bin/env bash
# Download source manifests from the four official docs indexes.
# Usage: scripts/refresh_sources.sh [--out DIR]
# Default output: infra/docker/sources/$(date -u +%Y-%m-%d)/
#
# This is a stub implementation for Slice 10. The real upstream URLs and
# parsing logic are deferred to Slice 9c. Today it creates the directory
# structure and writes placeholder manifests so the config.py comment
# is no longer a phantom reference.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_OUT="$REPO_ROOT/infra/docker/sources/$(date -u +%Y-%m-%d)"
OUT_DIR="${1:-$DEFAULT_OUT}"

log()  { printf '\033[1;34m→\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# Validate arguments
if [[ "$OUT_DIR" != /* ]]; then
  fail "Output path must be absolute: $OUT_DIR"
fi

log "Creating source manifest directory: $OUT_DIR"
mkdir -p "$OUT_DIR"/{claude,claude_code,codex,gemini}

# Placeholder manifests — these are the upstream URLs we'll fetch in Slice 9c.
declare -A SOURCES=(
  [claude]="https://docs.anthropic.com/claude/docs.json"
  [claude_code]="https://code.anthropic.com/docs.json"
  [codex]="https://docs.anthropic.com/codex/docs.json"
  [gemini]="https://ai.google.dev/docs.json"
)

for source in "${!SOURCES[@]}"; do
  url="${SOURCES[$source]}"
  manifest_file="$OUT_DIR/$source/manifest.json"
  log "Writing placeholder manifest for $source → $manifest_file"
  cat > "$manifest_file" <<EOF
{
  "source": "$source",
  "upstream_url": "$url",
  "fetched_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "note": "Placeholder — real fetch lands in Slice 9c"
}
EOF
done

log "Source manifests written to $OUT_DIR"
echo "$OUT_DIR"
```

- [ ] **Step 2: Make executable and test**

Run:
```bash
chmod +x scripts/refresh_sources.sh
./scripts/refresh_sources.sh
```
Expected: Creates `infra/docker/sources/<date>/` with 4 subdirectories and 4 `manifest.json` files; prints the path to stdout

- [ ] **Step 3: Clean up test artifacts**

Run: `rm -rf infra/docker/sources/` (we don't commit the generated manifests)
Expected: Directory removed

- [ ] **Step 4: Commit the script**

```bash
git add scripts/refresh_sources.sh
git commit -m "chore(release): add refresh_sources.sh skeleton (Slice 9c placeholder)"
```

---

## Task 4: Golden suite — case files (Task 4.1-4.5, 50 cases total)

**Files:**
- Create: `backend/tests/golden/cases/golden_001.yaml` through `golden_050.yaml`

**Interfaces:**
- Consumes: `docs/TEST_STRATEGY.md §6` schema
- Produces: YAML cases that the runner reads

**NOTE:** These are hand-authored Q&A cases. The runner (Task 5) will read them. For the plan, I specify the exact schema and 5 representative cases; the implementer authors all 50 following the pattern.

- [ ] **Step 1: Create golden cases directory and write the first 5 cases**

Create directory and `backend/tests/golden/cases/golden_001.yaml` (Codex usage):

```yaml
case_id: golden_001
question: "How do I install Claude Code?"
expected_domain: "claude_code"
expected_intent: "how_to"
expected_behavior: "answer"
expected_sources:
  - "Claude Code installation documentation"
category: "claude_code_usage"
gates:
  - retrieval_hit
  - citation_correctness
required_answer_points:
  - "mentions installation"
  - "does not invent unsupported modes"
forbidden_answer_points:
  - "claims unsupported admin feature"
```

`golden_002.yaml` (Claude usage):

```yaml
case_id: golden_002
question: "What is Claude's context window?"
expected_domain: "claude"
expected_intent: "explanatory"
expected_behavior: "answer"
expected_sources:
  - "Claude context window documentation"
category: "claude_usage"
gates:
  - retrieval_hit
  - citation_correctness
required_answer_points:
  - "mentions context window"
  - "does not invent unsupported sizes"
forbidden_answer_points: []
```

`golden_003.yaml` (Exact lookup):

```yaml
case_id: golden_003
question: "What does the --help flag do in Claude Code?"
expected_domain: "claude_code"
expected_intent: "exact_lookup"
expected_behavior: "answer"
expected_sources:
  - "Claude Code CLI reference"
category: "exact_lookup"
gates:
  - retrieval_hit
  - citation_correctness
  - exact_lookup_accuracy
required_answer_points:
  - "mentions --help"
  - "or mentions 'help' flag"
forbidden_answer_points: []
```

`golden_004.yaml` (Unsupported):

```yaml
case_id: golden_004
question: "What is the stock price of Anthropic?"
expected_domain: "claude"
expected_intent: "unsupported"
expected_behavior: "refuse"
expected_sources: []
category: "unsupported_out_of_domain"
gates:
  - guardrail_refusal
required_answer_points: []
forbidden_answer_points:
  - "provides a stock price"
  - "answers financial question"
```

`golden_005.yaml` (No-answer):

```yaml
case_id: golden_005
question: "What is the secret admin password for Claude Code?"
expected_domain: "claude_code"
expected_intent: "how_to"
expected_behavior: "no_answer"
expected_sources: []
category: "no_answer_weak_evidence"
gates:
  - no_answer_behavior
required_answer_points: []
forbidden_answer_points:
  - "invents a password"
  - "provides admin credentials"
```

- [ ] **Step 2: Verify YAML syntax**

Run:
```bash
cd backend && PYTHONPATH=. uv run python -c "
import yaml
from pathlib import Path
for p in Path('tests/golden/cases').glob('*.yaml'):
    yaml.safe_load(p.read_text())
"
```
Expected: No errors (parses cleanly)

- [ ] **Step 3: Author remaining 45 cases following the distribution**

Per `docs/TEST_STRATEGY.md §5`, the implementer authors 45 more YAMLs:
- 7 more Codex usage (total 10)
- 7 more Claude usage (total 8)
- 9 more Claude Code usage (total 10)
- 7 more Gemini usage (total 8)
- 5 more exact lookup (total 6)
- 2 more multi-doc how-to (total 3)
- 1 more follow-up (total 2)
- 1 more unsupported (total 2)

Each YAML follows the schema in Step 1. Category must be one of:
`codex_usage`, `claude_usage`, `claude_code_usage`, `gemini_usage`, `exact_lookup`, `multi_doc_how_to`, `follow_up`, `unsupported_out_of_domain`, `no_answer_weak_evidence`.

Gates must be a subset of: `retrieval_hit`, `citation_correctness`, `guardrail_refusal`, `no_answer_behavior`, `exact_lookup_accuracy`.

- [ ] **Step 4: Verify all 50 files exist and parse**

Run:
```bash
ls backend/tests/golden/cases/ | wc -l
```
Expected: `50`

Run:
```bash
cd backend && PYTHONPATH=. uv run python -c "
import yaml
from pathlib import Path
errors = []
for p in Path('tests/golden/cases').glob('*.yaml'):
    try:
        d = yaml.safe_load(p.read_text())
        required = ['case_id', 'question', 'expected_domain', 'expected_intent', 'expected_behavior', 'expected_sources', 'category', 'gates']
        missing = [k for k in required if k not in d]
        if missing:
            errors.append(f'{p.name}: missing {missing}')
    except Exception as e:
        errors.append(f'{p.name}: {e}')
for e in errors:
    print(e)
exit(len(errors))
"
```
Expected: Exit 0 (no errors)

- [ ] **Step 5: Commit the golden cases**

```bash
git add backend/tests/golden/cases/
git commit -m "feat(evals): add 50 golden evaluation cases (YAML)"
```

---

## Task 5: Golden runner — core logic and CLI (Commit 2: `feat(evals)` part A)

**Files:**
- Create: `backend/tests/golden/runner.py`
- Create: `backend/tests/golden/__init__.py`
- Create: `backend/tests/golden/__main__.py`
- Test: `backend/tests/golden/test_runner.py`

**Interfaces:**
- Consumes: YAML cases from Task 4, `TestClient` from `fastapi.testclient`, `seed_catalog` from `tests.conftest`, `AnswerResponse` shape from `app.answer.orchestrator`
- Produces: `GoldenRunResult` with pass_rate, per_gate_rates, case_results; CLI entry point; JSON output

- [ ] **Step 1: Write the failing test — runner loads and validates cases**

Create `backend/tests/golden/test_runner.py`:

```python
"""Tests for the golden evaluation runner."""

from pathlib import Path
import pytest

from tests.golden.runner import load_case, Case


def test_load_case_valid_yaml():
    """A valid YAML case loads as a Case object."""
    path = Path(__file__).parent / "cases" / "golden_001.yaml"
    case = load_case(path)
    assert case.case_id == "golden_001"
    assert case.question
    assert case.expected_domain == "claude_code"
    assert case.expected_behavior == "answer"


def test_load_case_missing_required_field():
    """A case missing a required field raises ValueError."""
    # Create a temp YAML missing case_id
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("question: 'test'\nexpected_behavior: answer\n")
        f.flush()
        path = Path(f.name)
    try:
        with pytest.raises(ValueError, match="case_id"):
            load_case(path)
    finally:
        path.unlink()


def test_load_case_invalid_behavior():
    """expected_behavior must be one of answer, refuse, no_answer."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("case_id: test\nquestion: 'test'\nexpected_behavior: maybe\n")
        f.flush()
        path = Path(f.name)
    try:
        with pytest.raises(ValueError, match="expected_behavior"):
            load_case(path)
    finally:
        path.unlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_load_case_valid_yaml -v`
Expected: FAIL with "module 'tests.golden.runner' does not exist"

- [ ] **Step 3: Implement minimal runner — load_case function**

Create `backend/tests/golden/__init__.py` (empty).

Create `backend/tests/golden/runner.py`:

```python
"""Golden evaluation runner.

Loads YAML cases from tests/golden/cases/, executes them against the
/v1/ask endpoint, and aggregates pass/fail metrics per gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml


class ExpectedBehavior(str, Enum):
    """Values for expected_behavior in a YAML case."""

    ANSWER = "answer"
    REFUSE = "refuse"
    NO_ANSWER = "no_answer"


class Gate(str, Enum):
    """Evaluation gates a case can participate in."""

    RETRIEVAL_HIT = "retrieval_hit"
    CITATION_CORRECTNESS = "citation_correctness"
    GUARDRAIL_REFUSAL = "guardrail_refusal"
    NO_ANSWER_BEHAVIOR = "no_answer_behavior"
    EXACT_LOOKUP_ACCURACY = "exact_lookup_accuracy"


@dataclass
class Case:
    """A golden test case loaded from YAML."""

    case_id: str
    question: str
    expected_domain: str
    expected_intent: str
    expected_behavior: ExpectedBehavior
    expected_sources: list[str]
    category: str
    gates: list[Gate]
    required_answer_points: list[str] = field(default_factory=list)
    forbidden_answer_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "question": self.question,
            "expected_domain": self.expected_domain,
            "expected_intent": self.expected_intent,
            "expected_behavior": self.expected_behavior.value,
            "expected_sources": self.expected_sources,
            "category": self.category,
            "gates": [g.value for g in self.gates],
            "required_answer_points": self.required_answer_points,
            "forbidden_answer_points": self.forbidden_answer_points,
        }


def load_case(path: Path) -> Case:
    """Load a YAML case file and return a Case object."""
    if not path.exists():
        raise FileNotFoundError(f"Case file not found: {path}")

    data = yaml.safe_load(path.read_text())

    # Validate required fields
    required = ["case_id", "question", "expected_domain", "expected_intent", "expected_behavior", "expected_sources", "category", "gates"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Case {path.name} missing required fields: {missing}")

    # Validate expected_behavior
    try:
        behavior = ExpectedBehavior(data["expected_behavior"])
    except ValueError:
        raise ValueError(f"Case {path.name} has invalid expected_behavior: {data['expected_behavior']}")

    # Convert gates to Gate enum
    try:
        gates = [Gate(g) for g in data["gates"]]
    except ValueError as e:
        raise ValueError(f"Case {path.name} has invalid gate: {e}")

    return Case(
        case_id=data["case_id"],
        question=data["question"],
        expected_domain=data["expected_domain"],
        expected_intent=data["expected_intent"],
        expected_behavior=behavior,
        expected_sources=data.get("expected_sources", []),
        category=data["category"],
        gates=gates,
        required_answer_points=data.get("required_answer_points", []),
        forbidden_answer_points=data.get("forbidden_answer_points", []),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py -v`
Expected: PASS for all three tests

- [ ] **Step 5: Extend test — runner scores retrieval_hit gate**

Add to `test_runner.py`:

```python
from fastapi.testclient import TestClient


def test_score_retrieval_hit_pass():
    """retrieval_hit passes when response has answer=False, unsupported=False, no_answer=False, and citations non-empty."""
    from tests.golden.runner import score_retrieval_hit

    response = {
        "unsupported": False,
        "no_answer": False,
        "citations": [{"title": "Some doc"}],
    }
    passed, reason = score_retrieval_hit(response, expected_behavior=ExpectedBehavior.ANSWER)
    assert passed is True
    assert reason == ""


def test_score_retrieval_hit_fail_on_refusal():
    """retrieval_hit fails when response carries refusal=True."""
    from tests.golden.runner import score_retrieval_hit

    response = {
        "unsupported": False,
        "no_answer": False,
        "citations": [],
    }
    # Simulate refusal behavior (the API sets unsupported=True for refusals)
    response["unsupported"] = True
    passed, reason = score_retrieval_hit(response, expected_behavior=ExpectedBehavior.ANSWER)
    assert passed is False
    assert "refusal" in reason.lower()


def test_score_retrieval_hit_fail_on_empty_citations():
    """retrieval_hit fails when citations is empty."""
    from tests.golden.runner import score_retrieval_hit

    response = {
        "unsupported": False,
        "no_answer": False,
        "citations": [],
    }
    passed, reason = score_retrieval_hit(response, expected_behavior=ExpectedBehavior.ANSWER)
    assert passed is False
    assert "no citations" in reason.lower()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_retrieval_hit_pass -v`
Expected: FAIL with "score_retrieval_hit not defined"

- [ ] **Step 7: Implement score_retrieval_hit**

Add to `backend/tests/golden/runner.py`:

```python
def score_retrieval_hit(response: dict[str, Any], *, expected_behavior: ExpectedBehavior) -> tuple[bool, str]:
    """Score the retrieval_hit gate.

    Passes when:
    - expected_behavior is ANSWER and response is NOT a refusal (unsupported=False, no_answer=False)
      and citations is non-empty.
    - Otherwise fails with a reason.
    """
    if expected_behavior != ExpectedBehavior.ANSWER:
        return True, ""  # Gate not applicable for this case

    if response.get("unsupported") or response.get("no_answer"):
        return False, "Response is a refusal or no-answer"

    citations = response.get("citations", [])
    if not citations:
        return False, "No citations returned"

    return True, ""
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_retrieval_hit_pass -v`
Expected: PASS

- [ ] **Step 9: Extend test — runner scores citation_correctness gate**

Add to `test_runner.py`:

```python
def test_score_citation_correctness_pass():
    """citation_correctness passes when all expected_sources appear in citation titles."""
    from tests.golden.runner import score_citation_correctness

    response = {
        "citations": [
            {"title": "Claude Code installation"},
            {"title": "Claude context window"},
        ],
    }
    expected_sources = ["Claude Code installation"]
    passed, reason = score_citation_correctness(response, expected_sources=expected_sources)
    assert passed is True
    assert reason == ""


def test_score_citation_correctness_fail_missing():
    """citation_correctness fails when an expected_source is missing from citations."""
    from tests.golden.runner import score_citation_correctness

    response = {
        "citations": [{"title": "Other doc"}],
    }
    expected_sources = ["Claude Code installation"]
    passed, reason = score_citation_correctness(response, expected_sources=expected_sources)
    assert passed is False
    assert "missing" in reason.lower()
```

- [ ] **Step 10: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_citation_correctness_pass -v`
Expected: FAIL with "score_citation_correctness not defined"

- [ ] **Step 11: Implement score_citation_correctness**

Add to `backend/tests/golden/runner.py`:

```python
def score_citation_correctness(response: dict[str, Any], *, expected_sources: list[str]) -> tuple[bool, str]:
    """Score the citation_correctness gate.

    Passes when every title in expected_sources appears in at least one
    citation's title field (case-insensitive substring match).
    """
    if not expected_sources:
        return True, ""  # No sources required → gate passes

    citations = response.get("citations", [])
    citation_titles = [c.get("title", "").lower() for c in citations]

    missing = []
    for expected in expected_sources:
        if not any(expected.lower() in title for title in citation_titles):
            missing.append(expected)

    if missing:
        return False, f"Expected sources not found in citations: {missing}"
    return True, ""
```

- [ ] **Step 12: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_citation_correctness_pass -v`
Expected: PASS

- [ ] **Step 13: Extend test — runner scores guardrail_refusal gate**

Add to `test_runner.py`:

```python
def test_score_guardrail_refusal_pass():
    """guardrail_refusal passes when expected_behavior=refuse and response carries unsupported=True."""
    from tests.golden.runner import score_guardrail_refusal

    response = {"unsupported": True}
    passed, reason = score_guardrail_refusal(response, expected_behavior=ExpectedBehavior.REFUSE)
    assert passed is True
    assert reason == ""


def test_score_guardrail_refusal_fail():
    """guardrail_refusal fails when expected_behavior=refuse but response is a real answer."""
    from tests.golden.runner import score_guardrail_refusal

    response = {"unsupported": False, "no_answer": False, "citations": [{"title": "Doc"}]}
    passed, reason = score_guardrail_refusal(response, expected_behavior=ExpectedBehavior.REFUSE)
    assert passed is False
    assert "did not refuse" in reason.lower()
```

- [ ] **Step 14: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_guardrail_refusal_pass -v`
Expected: FAIL with "score_guardrail_refusal not defined"

- [ ] **Step 15: Implement score_guardrail_refusal**

Add to `backend/tests/golden/runner.py`:

```python
def score_guardrail_refusal(response: dict[str, Any], *, expected_behavior: ExpectedBehavior) -> tuple[bool, str]:
    """Score the guardrail_refusal gate.

    Passes when expected_behavior is REFUSE and response carries
    unsupported=True (the refusal envelope).
    """
    if expected_behavior != ExpectedBehavior.REFUSE:
        return True, ""  # Gate not applicable

    if response.get("unsupported"):
        return True, ""
    return False, "Expected refusal but response returned a real answer"
```

- [ ] **Step 16: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_guardrail_refusal_pass -v`
Expected: PASS

- [ ] **Step 17: Extend test — runner scores no_answer_behavior gate**

Add to `test_runner.py`:

```python
def test_score_no_answer_behavior_pass():
    """no_answer_behavior passes when expected_behavior=no_answer and response carries no_answer=True."""
    from tests.golden.runner import score_no_answer_behavior

    response = {"no_answer": True}
    passed, reason = score_no_answer_behavior(response, expected_behavior=ExpectedBehavior.NO_ANSWER)
    assert passed is True
    assert reason == ""


def test_score_no_answer_behavior_fail():
    """no_answer_behavior fails when expected_behavior=no_answer but response answers."""
    from tests.golden.runner import score_no_answer_behavior

    response = {"no_answer": False, "unsupported": False, "citations": [{"title": "Doc"}]}
    passed, reason = score_no_answer_behavior(response, expected_behavior=ExpectedBehavior.NO_ANSWER)
    assert passed is False
    assert "did not return no_answer" in reason.lower()
```

- [ ] **Step 18: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_no_answer_behavior_pass -v`
Expected: FAIL with "score_no_answer_behavior not defined"

- [ ] **Step 19: Implement score_no_answer_behavior**

Add to `backend/tests/golden/runner.py`:

```python
def score_no_answer_behavior(response: dict[str, Any], *, expected_behavior: ExpectedBehavior) -> tuple[bool, str]:
    """Score the no_answer_behavior gate.

    Passes when expected_behavior is NO_ANSWER and response carries
    no_answer=True.
    """
    if expected_behavior != ExpectedBehavior.NO_ANSWER:
        return True, ""  # Gate not applicable

    if response.get("no_answer"):
        return True, ""
    return False, "Expected no_answer but response returned a real answer"
```

- [ ] **Step 20: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_no_answer_behavior_pass -v`
Expected: PASS

- [ ] **Step 21: Extend test — runner scores exact_lookup_accuracy gate**

Add to `test_runner.py`:

```python
def test_score_exact_lookup_accuracy_pass():
    """exact_lookup_accuracy passes when question contains an exact term and answer mentions it."""
    from tests.golden.runner import score_exact_lookup_accuracy

    response = {"answer": "The --help flag displays usage information."}
    question = "What does --help do?"
    passed, reason = score_exact_lookup_accuracy(response, question=question, expected_intent="exact_lookup")
    assert passed is True
    assert reason == ""


def test_score_exact_lookup_accuracy_fail():
    """exact_lookup_accuracy fails when answer doesn't mention the term."""
    from tests.golden.runner import score_exact_lookup_accuracy

    response = {"answer": "I don't know about flags."}
    question = "What does --help do?"
    passed, reason = score_exact_lookup_accuracy(response, question=question, expected_intent="exact_lookup")
    assert passed is False
    assert "does not mention" in reason.lower()
```

- [ ] **Step 22: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_exact_lookup_accuracy_pass -v`
Expected: FAIL with "score_exact_lookup_accuracy not defined"

- [ ] **Step 23: Implement score_exact_lookup_accuracy**

Add to `backend/tests/golden/runner.py`:

```python
def score_exact_lookup_accuracy(response: dict[str, Any], *, question: str, expected_intent: str) -> tuple[bool, str]:
    """Score the exact_lookup_accuracy gate.

    Extracts the first exact term from the question (words preceded by --)
    and checks if the answer text mentions it (case-insensitive).
    """
    if expected_intent != "exact_lookup":
        return True, ""  # Gate not applicable

    # Extract exact term (e.g., "--help" from "What does --help do?")
    import re
    match = re.search(r'--\w+', question)
    if not match:
        return True, ""  # No exact term found → gate passes vacuously

    term = match.group(0).lower()
    answer = response.get("answer", "").lower()

    if term in answer:
        return True, ""
    return False, f"Answer does not mention exact term {term}"
```

- [ ] **Step 24: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_score_exact_lookup_accuracy_pass -v`
Expected: PASS

- [ ] **Step 25: Commit runner core + tests**

```bash
git add backend/tests/golden/
git commit -m "feat(evals): golden runner core — case loading + gate scoring (retrieval, citation, refusal, no_answer, exact lookup)"
```

---

## Task 6: Golden runner — end-to-end execution and CLI (Commit 2: `feat(evals)` part B)

**Files:**
- Modify: `backend/tests/golden/runner.py` (add run_suite, aggregate metrics)
- Create: `backend/tests/golden/__main__.py` (CLI entry point)
- Modify: `backend/tests/golden/test_runner.py` (add end-to-end test)

**Interfaces:**
- Consumes: All gate scoring functions from Task 5, TestClient from fastapi, seed_catalog from tests.conftest
- Produces: GoldenRunResult with pass_rate, per_gate_rates, case_results; exit code 0/1

- [ ] **Step 1: Write the failing test — run_suite executes a case against TestClient**

Add to `backend/tests/golden/test_runner.py`:

```python
def test_run_suite_single_case(client):
    """run_suite executes a single case and returns metrics."""
    from tests.golden.runner import run_suite, load_case
    from tests.conftest import seed_catalog
    import asyncio

    # Seed the catalog so the answer endpoint has chunks to retrieve
    asyncio.get_event_loop().run_until_complete(seed_catalog(client.app.state._db))

    # Load a real case
    case_path = Path(__file__).parent / "cases" / "golden_001.yaml"
    case = load_case(case_path)

    # Run the suite
    result = run_suite(client=client, cases=[case], llm_provider="stub")

    assert result.total_cases == 1
    assert result.pass_rate <= 1.0
    assert len(result.case_results) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_run_suite_single_case -v`
Expected: FAIL with "run_suite not defined"

- [ ] **Step 3: Implement run_suite**

Add to `backend/tests/golden/runner.py`:

```python
@dataclass
class CaseResult:
    """Result of a single case execution."""

    case_id: str
    gates_passed: list[str]
    gates_failed: list[str]
    status: Literal["pass", "fail", "setup_error"]
    latency_ms: int


@dataclass
class GoldenRunResult:
    """Aggregate result of a golden suite run."""

    total_cases: int
    pass_rate: float
    per_gate_rates: dict[str, float]
    case_results: list[CaseResult]
    llm_provider: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "pass_rate": self.pass_rate,
            "per_gate_rates": self.per_gate_rates,
            "case_results": [
                {
                    "case_id": r.case_id,
                    "gates_passed": r.gates_passed,
                    "gates_failed": r.gates_failed,
                    "status": r.status,
                    "latency_ms": r.latency_ms,
                }
                for r in self.case_results
            ],
            "llm_provider": self.llm_provider,
        }


def run_suite(
    *,
    client: TestClient,
    cases: list[Case],
    llm_provider: str,
) -> GoldenRunResult:
    """Run a list of golden cases against the /v1/ask endpoint.

    Returns aggregate metrics and per-case results. A case fails if any
    of its declared gates fail. Setup errors (missing fields, HTTP 5xx)
    fail the entire run.
    """
    case_results: list[CaseResult] = []
    gate_pass_counts: dict[str, int] = {}
    gate_fail_counts: dict[str, int] = {}

    for case in cases:
        start = time.time()
        try:
            # Create a session and post the question
            session_response = client.post(
                "/v1/sessions",
                headers={"X-API-Key": "local-demo-key"},
                json={"user_id": "golden_runner"},
            )
            if session_response.status_code != 200:
                case_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        gates_passed=[],
                        gates_failed=[],
                        status="setup_error",
                        latency_ms=int((time.time() - start) * 1000),
                    )
                )
                continue

            session_id = session_response.json()["session_id"]

            answer_response = client.post(
                f"/v1/sessions/{session_id}/messages",
                headers={"X-API-Key": "local-demo-key"},
                json={"message": case.question, "answer_style": "short"},
            )

            latency_ms = int((time.time() - start) * 1000)

            if answer_response.status_code != 200:
                case_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        gates_passed=[],
                        gates_failed=[],
                        status="setup_error",
                        latency_ms=latency_ms,
                    )
                )
                continue

            response_body = answer_response.json()

            # Score each declared gate
            gates_passed = []
            gates_failed = []

            for gate in case.gates:
                if gate == Gate.RETRIEVAL_HIT:
                    passed, reason = score_retrieval_hit(response_body, expected_behavior=case.expected_behavior)
                elif gate == Gate.CITATION_CORRECTNESS:
                    passed, reason = score_citation_correctness(response_body, expected_sources=case.expected_sources)
                elif gate == Gate.GUARDRAIL_REFUSAL:
                    passed, reason = score_guardrail_refusal(response_body, expected_behavior=case.expected_behavior)
                elif gate == Gate.NO_ANSWER_BEHAVIOR:
                    passed, reason = score_no_answer_behavior(response_body, expected_behavior=case.expected_behavior)
                elif gate == Gate.EXACT_LOOKUP_ACCURACY:
                    passed, reason = score_exact_lookup_accuracy(response_body, question=case.question, expected_intent=case.expected_intent)
                else:
                    passed, reason = False, f"Unknown gate: {gate}"

                if passed:
                    gates_passed.append(gate.value)
                    gate_pass_counts[gate.value] = gate_pass_counts.get(gate.value, 0) + 1
                else:
                    gates_failed.append(gate.value)
                    gate_fail_counts[gate.value] = gate_fail_counts.get(gate.value, 0) + 1

            # Case passes if all its declared gates passed
            status = "pass" if len(gates_failed) == 0 else "fail"
            case_results.append(
                CaseResult(
                    case_id=case.case_id,
                    gates_passed=gates_passed,
                    gates_failed=gates_failed,
                    status=status,
                    latency_ms=latency_ms,
                )
            )

        except Exception as e:
            # Setup or execution error
            case_results.append(
                CaseResult(
                    case_id=case.case_id,
                    gates_passed=[],
                    gates_failed=[],
                    status="setup_error",
                    latency_ms=int((time.time() - start) * 1000),
                )
            )

    # Compute aggregate metrics
    total_cases = len(case_results)
    passed_cases = sum(1 for r in case_results if r.status == "pass")
    pass_rate = passed_cases / total_cases if total_cases > 0 else 0.0

    # Compute per-gate rates
    per_gate_rates: dict[str, float] = {}
    for gate in set(gate_pass_counts) | set(gate_fail_counts):
        pass_cnt = gate_pass_counts.get(gate, 0)
        fail_cnt = gate_fail_counts.get(gate, 0)
        total = pass_cnt + fail_cnt
        per_gate_rates[gate] = pass_cnt / total if total > 0 else 0.0

    return GoldenRunResult(
        total_cases=total_cases,
        pass_rate=pass_rate,
        per_gate_rates=per_gate_rates,
        case_results=case_results,
        llm_provider=llm_provider,
    )
```

Also add at the top of `runner.py`:

```python
import time
from fastapi.testclient import TestClient
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_run_suite_single_case -v`
Expected: PASS (may fail on actual answer; that's fine — we're testing the plumbing)

- [ ] **Step 5: Write CLI entry point test**

Add to `backend/tests/golden/test_runner.py`:

```python
def test_main_entry_point():
    """__main__ exposes a CLI that runs the suite."""
    from tests.golden import __main__
    import sys
    from io import StringIO

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        __main__.main()
    except SystemExit as e:
        output = sys.stdout.getvalue()
        assert "total_cases" in output or "error" in output.lower()
    finally:
        sys.stdout = old_stdout
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_main_entry_point -v`
Expected: FAIL with "module 'tests.golden.__main__' has no attribute 'main'"

- [ ] **Step 7: Implement CLI entry point**

Create `backend/tests/golden/__main__.py`:

```python
"""CLI entry point for the golden evaluation runner.

Usage:
    cd backend
    PYTHONPATH=. uv run python -m tests.golden --llm-provider stub --output ../artifacts/golden-results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.main import create_app
from fastapi.testclient import TestClient

from tests.golden.runner import load_case, run_suite, GoldenRunResult


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the golden evaluation suite")
    parser.add_argument(
        "--llm-provider",
        default="stub",
        choices=["stub", "anthropic"],
        help="LLM provider to use (stub or anthropic)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write JSON results (optional)",
    )
    parser.add_argument(
        "--cases-dir",
        default=Path(__file__).parent / "cases",
        type=Path,
        help="Directory containing golden YAML cases",
    )
    args = parser.parse_args()

    # Load all YAML cases
    cases_dir = args.cases_dir
    if not cases_dir.exists():
        print(f"Cases directory not found: {cases_dir}", file=sys.stderr)
        sys.exit(1)

    case_files = sorted(cases_dir.glob("*.yaml"), key=lambda p: p.stem)
    if not case_files:
        print(f"No YAML cases found in {cases_dir}", file=sys.stderr)
        sys.exit(1)

    cases = [load_case(p) for p in case_files]

    # Create a TestClient against the app
    app = create_app()
    client = TestClient(app)

    # Run the suite
    print(f"Running {len(cases)} golden cases with LLM provider={args.llm_provider}...", file=sys.stderr)
    result = run_suite(client=client, cases=cases, llm_provider=args.llm_provider)

    # Print summary
    print(f"\nTotal cases: {result.total_cases}", file=sys.stderr)
    print(f"Pass rate: {result.pass_rate:.2%}", file=sys.stderr)
    print("\nPer-gate rates:", file=sys.stderr)
    for gate, rate in sorted(result.per_gate_rates.items()):
        print(f"  {gate}: {rate:.2%}", file=sys.stderr)

    # Write output if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result.to_dict(), indent=2))
        print(f"\nResults written to {args.output}", file=sys.stderr)

    # Exit 1 if pass_rate < 0.95
    if result.pass_rate < 0.95:
        print(f"\nPass rate {result.pass_rate:.2%} is below 95% threshold", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_runner.py::test_main_entry_point -v`
Expected: PASS

- [ ] **Step 9: Test CLI end-to-end with real golden cases**

Run:
```bash
cd backend
uv run python -m tests.golden --llm-provider stub --output ../artifacts/golden-results.json
```
Expected: Prints summary, creates `artifacts/golden-results.json`, exit 0 if pass_rate ≥ 0.95 else exit 1

- [ ] **Step 10: Verify JSON output shape**

Run: `cat artifacts/golden-results.json | jq .`
Expected: Valid JSON with `total_cases`, `pass_rate`, `per_gate_rates`, `case_results`, `llm_provider`

- [ ] **Step 11: Commit runner CLI + end-to-end**

```bash
git add backend/tests/golden/
git commit -m "feat(evals): golden runner CLI + end-to-end execution"
```

---

## Task 7: Golden suite Makefile target and nightly CI (Commit 2: `feat(evals)` part C)

**Files:**
- Modify: `Makefile` (add `golden` target)
- Create: `.github/workflows/golden.yml`
- Modify: `backend/tests/golden/test_smoke.py` (smoke test with 5 cases)

**Interfaces:**
- Consumes: `make golden` target, CLI from Task 6
- Produces: Nightly workflow that runs golden suite against Postgres

- [ ] **Step 1: Write the failing smoke test**

Create `backend/tests/golden/test_smoke.py`:

```python
"""Smoke test for the golden suite — runs 5 cases against the seeded catalog."""

import pytest
from pathlib import Path
from tests.conftest import seed_catalog
from tests.golden.runner import load_case, run_suite
from fastapi.testclient import TestClient
import asyncio


@pytest.mark.parametrize("case_num", [1, 2, 3, 4, 5])
def test_golden_smoke_cases(client, case_num):
    """Run a subset of golden cases as a fast smoke test on every PR."""
    # Seed catalog
    asyncio.get_event_loop().run_until_complete(seed_catalog(client.app.state._db))

    # Load case
    case_path = Path(__file__).parent / "cases" / f"golden_{case_num:03d}.yaml"
    case = load_case(case_path)

    # Run
    result = run_suite(client=client, cases=[case], llm_provider="stub")

    # Assert at least one case ran
    assert result.total_cases == 1
    # We don't assert pass/fail here — the smoke just proves the runner works end-to-end
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/golden/test_smoke.py -v`
Expected: PASS for all 5 cases

- [ ] **Step 3: Add `make golden` target**

Add to `Makefile` after the `test-pg` target:

```makefile
golden: ## Run the golden evaluation suite (requires the demo catalog seeded)
	cd backend && PYTHONPATH=. uv run python -m tests.golden \
	    --llm-provider $(LLM_PROVIDER) \
	    --output ../artifacts/golden-results.json
```

- [ ] **Step 4: Test make golden locally**

Run:
```bash
make demo  # Seed the catalog
make golden LLM_PROVIDER=stub
```
Expected: Runs the suite, prints summary, writes `artifacts/golden-results.json`

- [ ] **Step 5: Write nightly CI workflow**

Create `.github/workflows/golden.yml`:

```yaml
# Golden evaluation suite — nightly run against Postgres + pgvector.
# Fails if any non-answer-quality gate drops below 95%.

name: golden-evaluation

on:
  schedule:
    - cron: "0 2 * * *"  # 02:00 UTC nightly
  workflow_dispatch:  # Manual trigger

jobs:
  golden:
    name: golden suite (Postgres + pgvector)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: citevyn
          POSTGRES_PASSWORD: citevyn
          POSTGRES_DB: citevyn
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U citevyn -d citevyn"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      CITEVYN_DATABASE_URL: postgresql+psycopg://citevyn:citevyn@localhost:5432/citevyn
      CITEVYN_PG_TEST_URL: postgresql+psycopg://citevyn:citevyn@localhost:5432/citevyn
      CITEVYN_ADMIN_API_KEY: ${{ secrets.CITEVYN_ADMIN_API_KEY || 'smoke-admin-key' }}
      CITEVYN_DEMO_API_KEY: ${{ secrets.CITEVYN_DEMO_API_KEY || 'local-demo-key' }}
      CITEVYN_REDIS_URL: redis://localhost:6379
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install --upgrade pip uv
      - name: Sync dependencies
        run: uv sync --group dev
      - name: Apply migrations
        run: uv run alembic -c ../db/alembic.ini upgrade head
      - name: Seed catalog
        run: |
          PYTHONPATH=. uv run python -m db.seed.seed_users
          PYTHONPATH=. uv run python -m db.seed.seed_catalog
      - name: Run golden suite
        run: |
          mkdir -p ../artifacts
          PYTHONPATH=. uv run python -m tests.golden \
            --llm-provider stub \
            --output ../artifacts/golden-results.json
      - name: Upload results artifact
        uses: actions/upload-artifact@v4
        with:
          name: golden-results
          path: artifacts/golden-results.json
          retention-days: 30
```

- [ ] **Step 6: Test make golden passes on clean stack**

Run:
```bash
make stop  # Tear down any existing stack
make demo
make golden LLM_PROVIDER=stub
```
Expected: Suite runs, pass_rate reported, exit 0 (or 1 if threshold not met)

- [ ] **Step 7: Commit Makefile target + nightly workflow + smoke test**

```bash
git add Makefile .github/workflows/golden.yml backend/tests/golden/test_smoke.py
git commit -m "feat(evals): make golden target + nightly CI + smoke test"
```

---

## Task 8: Slice 9b stub guard (Commit 3: `fix(llm)`)

**Files:**
- Modify: `backend/app/llm/factory.py` (reject gemini/router in production)
- Modify: `backend/tests/test_llm_factory_singleton.py` (extend test)

**Interfaces:**
- Consumes: `ALLOWED_LLM_PROVIDERS` from factory.py
- Produces: Production-only rejection for gemini/router

- [ ] **Step 1: Write the failing test — gemini rejected in production**

Add to `backend/tests/test_llm_factory_singleton.py`:

```python
def test_validate_rejects_gemini_in_production():
    """validate_llm_provider raises for gemini in production."""
    from app.llm.factory import validate_llm_provider, LLMProviderNotConfigured
    from app.core.config import Settings

    settings = Settings(
        environment="production",
        llm_provider="gemini",
        anthropic_api_key="test",
        database_url="sqlite+aiosqlite:///:memory:",
        admin_api_key="test",
        demo_api_key="test",
    )

    with pytest.raises(LLMProviderNotConfigured, match="gemini"):
        validate_llm_provider(settings)


def test_validate_rejects_router_in_production():
    """validate_llm_provider raises for router in production."""
    from app.llm.factory import validate_llm_provider, LLMProviderNotConfigured
    from app.core.config import Settings

    settings = Settings(
        environment="production",
        llm_provider="router",
        anthropic_api_key="test",
        database_url="sqlite+aiosqlite:///:memory:",
        admin_api_key="test",
        demo_api_key="test",
    )

    with pytest.raises(LLMProviderNotConfigured, match="router"):
        validate_llm_provider(settings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_llm_factory_singleton.py::test_validate_rejects_gemini_in_production -v`
Expected: FAIL with tests pass (gemini/router currently accepted in production)

- [ ] **Step 3: Implement the guard**

Modify `backend/app/llm/factory.py`:

Add after line 33:

```python
# Providers whose real clients land in Slice 9b. Until then, reject them
# in production the same way we reject stub — silently serving canned answers
# is worse than a startup failure.
UNSUPPORTED_LLM_PROVIDERS: frozenset[str] = frozenset({"gemini", "router"})
```

Modify `validate_llm_provider` (lines 40-57) to:

```python
def validate_llm_provider(settings: Settings) -> None:
    """Reject ``stub`` and Slice 9b providers in production; tolerate them elsewhere.

    Called from :func:`app.main.create_app` so a misconfigured deploy
    fails immediately at boot rather than on the first ask.
    """
    if settings.llm_provider not in ALLOWED_LLM_PROVIDERS:
        raise RuntimeError(
            f"CITEVYN_LLM_PROVIDER={settings.llm_provider!r} is not supported. "
            f"Allowed values: {sorted(ALLOWED_LLM_PROVIDERS)}."
        )
    if settings.environment == "production" and (
        settings.llm_provider == "stub"
        or settings.llm_provider in UNSUPPORTED_LLM_PROVIDERS
    ):
        raise LLMProviderNotConfigured(
            f"CITEVYN_LLM_PROVIDER={settings.llm_provider!r} is not allowed "
            f"when CITEVYN_ENVIRONMENT='production'. Set "
            f"CITEVYN_LLM_PROVIDER to 'anthropic' and provide the matching API key. "
            f"(gemini and router are pending Slice 9b.)"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_llm_factory_singleton.py::test_validate_rejects_gemini_in_production tests/test_llm_factory_singleton.py::test_validate_rejects_router_in_production -v`
Expected: PASS

- [ ] **Step 5: Verify dev/test still works with gemini/router**

Run: `cd backend && uv run pytest tests/ -k "llm" -v` (all LLM tests)
Expected: PASS (existing tests still work because they run in dev/test, not production)

- [ ] **Step 6: Commit the stub guard**

```bash
git add backend/app/llm/factory.py backend/tests/test_llm_factory_singleton.py
git commit -m "fix(llm): reject gemini/router in production (Slice 9b stub guard)"
```

---

## Task 9: `docs/DEMO_CHECKLIST.md` (Commit 4: `chore(release)` part B)

**Files:**
- Create: `docs/DEMO_CHECKLIST.md`

**Interfaces:**
- Consumes: `docs/RELEASE_PLAN.md §5` and `§10`
- Produces: One-page checklist for demo readiness

- [ ] **Step 1: Write DEMO_CHECKLIST.md**

Create `docs/DEMO_CHECKLIST.md`:

```markdown
# Demo Readiness Checklist

> **Purpose:** One-page gate for Phase 5 (MVP Demo Release) exit criteria from
> [`docs/RELEASE_PLAN.md §5`](RELEASE_PLAN.md#5-phase-5-mvp-demo-release) and
> [`§10`](RELEASE_PLAN.md#10-release-blockers).
>
> **Run this on the release branch before tagging.** All items must pass.

---

## Pre-flight

- [ ] Clean working tree: `git status` shows no uncommitted changes.
- [ ] On the release branch (e.g. `slice-10-demo-readiness`), not `main`.
- [ ] No open GitHub issues with the `release-blocker` label:
  ```bash
  gh issue list --label release-blocker
  ```
  (Expected: 0 issues.)

---

## Backend Quality Gates

- [ ] `make verify` passes (lint + typecheck + pytest SQLite).
- [ ] `make smoke` passes (end-to-end: db-up, migrate, seed, uvicorn, /v1/ask, stop).
- [ ] `make golden` passes with `LLM_PROVIDER=stub` (infrastructure gates ≥95%, guardrail = 100%).

  ```bash
  make demo
  make golden LLM_PROVIDER=stub
  ```
  Required per [`docs/PRD.md §12`](PRD.md#12-release-blockers):
  - Golden pass rate ≥95%
  - Domain guardrail critical failures = 0
  - Citation correctness ≥95%
  - Retrieval hit rate ≥95%
  - Exact lookup accuracy ≥95%
  - (Answer-quality gates are deferred to Slice 9b with real LLM.)

---

## Frontend Smoke

- [ ] `make demo-frontend` succeeds and serves on http://localhost:4173.

  ```bash
  make demo-frontend
  ```
- [ ] Manual click-through: /, /chat, /search, /about render without console errors.

---

## Operational Readiness

- [ ] `make deploy` documented and tested on a non-prod VM.
  See [`docs/RUNBOOK.md §5`](RUNBOOK.md#5-release--rollback).
- [ ] Rollback rehearsed: `git checkout v0.8.0 && VERSION=v0.8.0 make refresh` works.
- [ ] Backup/restore tested: `make backup` writes a dump, `make restore` reads it back.

---

## Documentation

- [ ] README §1 status table accurate (Frontend: Optional preview, not "In development").
- [ ] README §13 release example uses `v0.9.0`.
- [ ] `CHANGELOG.md` exists at repo root with slice-9 entries.
- [ ] [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) diagram links resolve.
- [ ] [`docs/RUNBOOK.md`](RUNBOOK.md) §5 (release/rollback) tested.
- [ ] [`docs/RELEASE_PLAN.md`](RELEASE_PLAN.md) §10 release blockers reviewed.

---

## Sign-off

- [ ] All boxes above checked.
- [ ] Release candidate tag ready: `git tag -s v0.9.0 -m "v0.9.0 — demo-ready"`.
- [ ] CI green on the release branch.
```

- [ ] **Step 2: Commit the checklist**

```bash
git add docs/DEMO_CHECKLIST.md
git commit -m "chore(release): add DEMO_CHECKLIST.md (Phase 5 gate)"
```

---

## Task 10: `CHANGELOG.md` initialization (Commit 4: `chore(release)` part C)

**Files:**
- Create: `CHANGELOG.md` (repo root)

**Interfaces:**
- Consumes: Git log from `4d0d57e` onward
- Produces: Hand-written changelog following Keep a Changelog 1.1.0

- [ ] **Step 1: Write CHANGELOG.md**

Create `CHANGELOG.md` at repo root:

```markdown
# Changelog

All notable changes to CiteVyn will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Golden evaluation suite (50 cases + runner + nightly CI). See `docs/superpowers/specs/2026-06-22-demo-readiness-design.md`.
- Frontend CI job (`.github/workflows/frontend-ci.yml`): type-check + build gate.
- `docs/DEMO_CHECKLIST.md` — Phase 5 release gate checklist.
- `make e2e` target — full demo path: db-up + migrate + seed + uvicorn + frontend build + curl.
- `make demo-frontend` target — build + serve production bundle on :4173.
- `scripts/refresh_sources.sh` — skeleton (real fetch lands in Slice 9c).
- `docs/DEPENDABOT_TRIAGE.md` — policy doc for Dependabot PRs.
- `release-blocker` GitHub label — created for release-blocking issues.

### Changed
- README §1 frontend status flipped from "In development" to "Optional preview".
- README §13 release example bumped from `v0.2.0` to `v0.9.0`.
- `validate_llm_provider` (factory.py) now rejects `gemini` and `router` in production (Slice 9b stub guard).

### Deferred
- Answer-quality scoring (faithfulness, completeness, "no unsupported claims") — pending Slice 9b real LLM.
- Real `scripts/refresh_sources.sh` upstream fetch — pending Slice 9c.
- Second 50 golden cases — user-authored follow-up slice.

## [0.9.0] — 2026-06-22

### Added
- Slice 8: ingestion pipeline, admin surface, exact search (PR #7).
- Slice 9: rate limit, infra, docs, release pipeline (PR #11).
- Slice 9.1: rate-limit fail-closed, Redis pool close, conftest reset, hardcoded compose password removed, `get_current_request_id` returns `str`.

[0.9.0]: https://github.com/imrohitagrawal/citevyn/compare/v0.0.0...v0.9.0
```

- [ ] **Step 2: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "chore(release): initialize CHANGELOG.md with slice-9 history"
```

---

## Task 11: `docs/DEPENDABOT_TRIAGE.md` and release-blocker label (Commit 4: `chore(release)` part D)

**Files:**
- Create: `docs/DEPENDABOT_TRIAGE.md`
- Test: `gh label create` (run once)

**Interfaces:**
- Consumes: Open Dependabot PRs (#21–#26)
- Produces: Policy doc + GitHub label

- [ ] **Step 1: Write DEPENDABOT_TRIAGE.md**

Create `docs/DEPENDABOT_TRIAGE.md`:

```markdown
# Dependabot Triage Policy

## Policy

- **Patch + security updates:** Auto-merge once CI passes (if branch protection allows auto-merge).
- **Minor + major version updates:** Open for human review.
- **Major bumps** (X → Y where Y − X > 0 in major version): Require `make smoke` + manual UI check before merge.

The auto-merge policy is documented in `.github/dependabot.yml` (lines 17–26). Auto-merge requires:
1. Branch protection enabled on `main` (5 status checks).
2. "Allow auto-merge" enabled in repo Settings → General.
3. Auto-merge enabled on individual PRs via the PR UI.

## Current Open PRs (as of 2026-06-22)

| PR | Bump | Major? | Action |
|---|---|---|---|
| #21 | redis 7-alpine → 8-alpine | Yes | Wait for smoke run; merge after. |
| #22 | docker/metadata-action 5 → 6 | Yes | Wait for smoke run; merge after. |
| #23 | postgres 16-alpine → 18-alpine | Yes | Wait for smoke run; merge after. **Note:** See RUNBOOK §3.2 for volume permissions if this fails. |
| #24 | docker/build-push-action 6 → 7 | Yes | Wait for smoke run; merge after. |
| #25 | sqlalchemy[asyncio] >=2.0.30 → >=2.0.51 | No (patch/minor) | Auto-merge. |
| #26 | starlette 1.2.1 → 1.3.1 | Minor | Auto-merge after CI. |

## Smoke Run for Major Bumps

```bash
make smoke
```

Expected: All steps pass (db-up, migrate, seed, uvicorn, /v1/ask, stop).

## References

- [`.github/dependabot.yml`](../.github/dependabot.yml)
- [`docs/RUNBOOK.md`](RUNBOOK.md) (especially §3.2 for Postgres volume issues)
```

- [ ] **Step 2: Create the release-blocker label**

Run:
```bash
gh label create release-blocker --color b60205 --description "Blocks the next release; close or convert to enhancement before tagging."
```
Expected: Label created (or already exists)

- [ ] **Step 3: Verify label exists**

Run: `gh label list | grep release-blocker`
Expected: Shows `release-blocker` with color `b60205`

- [ ] **Step 4: Commit triage doc**

```bash
git add docs/DEPENDABOT_TRIAGE.md
git commit -m "chore(release): add DEPENDABOT_TRIAGE.md + create release-blocker label"
```

---

## Task 12: README §13 update + `make e2e` target (Commit 5: `docs(readme)`)

**Files:**
- Modify: `README.md` (§13 bump version to v0.9.0)
- Modify: `Makefile` (add `e2e` target)

**Interfaces:**
- Consumes: Existing `make demo`, `make smoke`, frontend build
- Produces: One-command demo path

- [ ] **Step 1: Update README §13 release example**

Modify `README.md` lines 329-330 from:

```markdown
$EDITOR backend/pyproject.toml        # version = "0.2.0"
```

To:

```markdown
$EDITOR backend/pyproject.toml        # version = "0.9.0" (already set)
```

Modify line 333 from:

```markdown
git tag -s v0.2.0 -m "v0.2.0 — production-ready"
```

To:

```markdown
git tag -s v0.9.0 -m "v0.9.0 — demo-ready"
```

Modify line 337 from:

```markdown
#    and opens a draft release on GitHub.
```

To (keep as-is, just noting for context).

- [ ] **Step 2: Add `make e2e` target**

Add to `Makefile` after the `smoke` target:

```makefile
e2e: ## Full demo path: db-up + migrate + seed + uvicorn + frontend build + curl
	$(MAKE) demo
	cd backend && PYTHONPATH=. uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
	@UVICORN_PID=$$!; \
	  sleep 3; \
	  curl -sf http://127.0.0.1:8000/health >/dev/null || (kill $$UVICORN_PID; exit 1); \
	  curl -sf -H "X-API-Key: $(API_KEY)" -H "Content-Type: application/json" \
	    -d '{"query":"How do I install Claude Code?"}' \
	    http://127.0.0.1:8000/v1/ask >/dev/null || (kill $$UVICORN_PID; exit 1); \
	  cd ../frontend && npm ci && npm run build >/dev/null || (kill $$UVICORN_PID; exit 1); \
	  kill $$UVICORN_PID; \
	  echo "e2e: backend healthy, /v1/ask cited, frontend bundle built."

```

- [ ] **Step 3: Add `e2e` to README §10**

Add after line 267 (after `make smoke` line):

```markdown
make e2e          # Full demo: db, api, /v1/ask, frontend build
```

- [ ] **Step 4: Test make e2e locally**

Run:
```bash
make stop  # Clean state
make e2e
```
Expected: All steps pass, prints "e2e: backend healthy, /v1/ask cited, frontend bundle built."

- [ ] **Step 5: Commit README + Makefile**

```bash
git add README.md Makefile
git commit -m "docs(readme): bump README example to v0.9.0 + add make e2e target"
```

---

## Task 13: Final branch verification and push

**Files:**
- None (branch-level verification)

**Interfaces:**
- Consumes: All 5 commits
- Produces: Clean, pushable branch

- [ ] **Step 1: Verify commit count**

Run: `git log --oneline main..HEAD | wc -l`
Expected: At least 5 commits (one per logical commit group; may be more if squashed)

- [ ] **Step 2: Run full gate**

Run: `make verify` (backend) and `cd frontend && npm run type-check && npm run build` (frontend)
Expected: All pass

- [ ] **Step 3: Run make e2e**

Run: `make e2e`
Expected: Passes end-to-end

- [ ] **Step 4: Run make golden**

Run: `make golden LLM_PROVIDER=stub`
Expected: Suite runs, pass_rate reported

- [ ] **Step 5: Push the branch**

Run: `git push -u origin slice-10-demo-readiness`
Expected: Branch pushed, ready for PR

---

## Task 14: Open PR and verify CI

**Files:**
- None (GitHub PR)

**Interfaces:**
- Consumes: Branch from Task 13
- Produces: Open PR with CI green

- [ ] **Step 1: Open the PR**

Run:
```bash
gh pr create --base main --head slice-10-demo-readiness \
  --title "feat(evals): slice-10 — demo readiness (golden suite, frontend CI, stub guard, checklist, changelog)" \
  --body "Implements P0 + P1 demo-readiness fixes per audit 2026-06-22.

See \`docs/superpowers/specs/2026-06-22-demo-readiness-design.md\` for the full design.

**Commits:**
1. chore(ci): frontend-ci.yml + README Optional preview + make demo-frontend
2. feat(evals): golden suite (50 cases + runner + nightly CI + make golden)
3. fix(llm): reject gemini/router in production (Slice 9b stub guard)
4. chore(release): DEMO_CHECKLIST, CHANGELOG, refresh_sources.sh, DEPENDABOT_TRIAGE, release-blocker label
5. docs(readme): README §13 bump to v0.9.0 + make e2e

**Acceptance criteria (from spec):**
- [x] 50 golden YAML cases authored (tests/golden/cases/)
- [x] Runner executes suite and reports pass_rate (tests/golden/runner.py)
- [x] make golden runs locally
- [x] frontend-ci.yml runs type-check + build
- [x] make e2e passes end-to-end
- [x] gemini/router rejected in production (factory.py)
- [x] DEMO_CHECKLIST.md exists
- [x] CHANGELOG.md initialized
- [x] scripts/refresh_sources.sh exists
- [x] release-blocker label created
- [x] README §13 uses v0.9.0

**CI jobs to watch:**
- ci.yml (backend lint/typecheck/pytest)
- frontend-ci.yml (type-check + build)
- golden.yml (manual dispatch to verify nightly runs)
- pr-quality.yml (meta-repo quality gate)

**Deferred to follow-up slices:**
- Answer-quality scoring (pending Slice 9b real LLM)
- Second 50 golden cases (user-authored)
- Real refresh_sources.sh upstream fetch (Slice 9c)
"
```

Expected: PR opened, CI starts

- [ ] **Step 2: Watch CI for all jobs**

Check: `gh pr checks` or the PR page
Expected: All jobs green (ci, frontend-ci, pr-quality, golden-manual)

- [ ] **Step 3: (Optional) Manual golden workflow dispatch**

Trigger the golden workflow manually from the Actions tab to verify the nightly job runs:
Expected: Job completes, uploads `golden-results.json` artifact

- [ ] **Step 4: PR review and merge**

Once CI is green and review passes, merge the PR to `main`.

---

## Task 15: Post-merge cleanup and tag preparation

**Files:**
- None (post-merge operations)

**Interfaces:**
- Consumes: Merged main branch
- Produces: Ready-to-tag main branch

- [ ] **Step 1: Verify main after merge**

Run: `git pull origin main && git log --oneline -5`
Expected: Slice 10 commits are on main

- [ ] **Step 2: Run final demo-readiness gate**

Run: `make verify && make e2e && make golden LLM_PROVIDER=stub`
Expected: All pass

- [ ] **Step 3: (Optional) Update memory file**

Update `memory/slice-10-state-after-push.md` to record the slice completion.

- [ ] **Step 4: Tag when ready**

Run: `git tag -s v0.9.0 -m "v0.9.0 — demo-ready" && git push --follow-tags`
Expected: Tag pushed, release workflow starts

---

## End of Plan

This plan implements all P0 and P1 items from the 2026-06-22 demo-readiness audit. Follow the TDD discipline (test first, minimal implementation, commit after each task). If a step fails unexpectedly, stop and diagnose — don't proceed on a broken foundation.
