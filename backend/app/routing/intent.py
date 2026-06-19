"""Slice 4 intent router.

Decides whether the user question wants ``exact_lookup``, ``faq``,
``how_to``, ``clarify``, ``no_answer``, or ``unsupported``. Pure
function — no DB or LLM. The router is shallow: a few regex patterns
that can be replaced with a learned classifier without changing the
call site.
"""

from __future__ import annotations

import enum
import re

from app.guardrails.domain import Domain

# ``unsupported`` lives in the guardrail; the router short-circuits to
# ``Intent.unsupported`` whenever the domain is unsupported so the
# orchestrator can refuse cheaply.
#
# ``no_answer`` is set by the orchestrator when retrieval yields zero
# evidence; the router never produces it from text alone.

_HOW_TO_RE = re.compile(
    r"\b(?:how(?:\s+(?:do|can|should|to))?|configure|set\s+up|setup|install|enable|disable)\b",
    re.IGNORECASE,
)
_EXACT_LOOKUP_RE = re.compile(
    r"""
    (?:--[a-z][a-z0-9-]+)             # a CLI flag
    | (?:\b[A-Z][A-Z0-9_]{2,}=[^\s]+) # an env-var assignment (KEY=value)
    | (?:\$[A-Z][A-Z0-9_]{2,}\b)      # a shell-style env reference
    | (?:`[^`\n]+`)                   # a literal backtick-quoted term
    | (?:\b(?:env|environment\s+variable)\s+[`'\"]?[A-Z][A-Z0-9_]{2,})  # spoken env var
    """,
    re.VERBOSE | re.IGNORECASE,
)
# Bare env-var-shaped tokens (no '=' or '$' or backticks). Must be
# uppercase with at least one underscore, surrounded by word boundaries
# to avoid matching regular nouns.
_BARE_ENV_VAR_RE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]{2,}\b")
_CLARIFY_MAX_TOKENS = 2  # very short fragments are treated as clarification asks


class Intent(enum.StrEnum):
    faq = "faq"
    exact_lookup = "exact_lookup"
    how_to = "how_to"
    clarify = "clarify"
    no_answer = "no_answer"
    unsupported = "unsupported"


def classify_intent(question: str, domain: Domain) -> Intent:
    if domain is Domain.unsupported:
        return Intent.unsupported
    if not question or not question.strip():
        return Intent.clarify
    if _EXACT_LOOKUP_RE.search(question):
        return Intent.exact_lookup
    if _BARE_ENV_VAR_RE.search(question):
        return Intent.exact_lookup
    if _HOW_TO_RE.search(question):
        return Intent.how_to
    tokens = question.split()
    if len(tokens) <= _CLARIFY_MAX_TOKENS:
        return Intent.clarify
    return Intent.faq


def should_skip_retrieval(intent: Intent) -> bool:
    return intent in {Intent.unsupported, Intent.clarify}
