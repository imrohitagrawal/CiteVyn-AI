"""Golden regression runner for CiteVyn (Slice 10).

This package executes every YAML case under
``tests/golden/cases/`` against a live ``TestClient`` (in-memory
SQLite + the standard demo seed) and scores the outcomes.

Public API
----------
* :class:`GoldenCase`     — dataclass parsed from one YAML file.
* :class:`Check`          — one pass/fail assertion result.
* :class:`CaseResult`     — per-case tally of checks + captured
                            response payloads.
* :func:`run_case`        — execute one case, return a CaseResult.
* :func:`run_all`         — execute every case file in a directory.
* :func:`summarize`       — collapse a list of CaseResult into a
                            pass/fail summary suitable for CI.

The runner does NOT start uvicorn or touch Postgres; it reuses the
``in_memory_client`` / ``seeded_app`` fixtures from
:mod:`tests.conftest` to stay hermetic. That makes it safe to
invoke from a Makefile target, a nightly workflow, and a unit
test alike.
"""

from .cases import GoldenCase, filter_cases, load_cases
from .runner import run_all, run_case
from .scoring import CaseResult, Check, summarize

__all__ = [
    "GoldenCase",
    "CaseResult",
    "Check",
    "filter_cases",
    "load_cases",
    "run_all",
    "run_case",
    "summarize",
]
