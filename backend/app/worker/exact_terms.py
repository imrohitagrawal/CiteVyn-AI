"""Exact-term extractor.

Pulls a small set of high-value strings (CLI flags, env
vars, header names, model names) out of a chunk so the
:class:`ExactTerm` table is populated for first-class
exact lookup.

Design notes
------------
* The MVP extractor is regex-only, no NLP. The patterns
  are deliberately narrow — false negatives are cheaper
  than false positives (a missed flag is just a worse
  recall, a spurious term clutters the lookup table).
* Each term is classified by its surface form. The
  classification is one-pass and does not use the
  :class:`TermType` enum's *semantic* meaning — the enum
  is named after the user's mental model
  ("I typed this flag"), not the worker's
  inference ("this looks like a flag").
* Deduplication: the same string may match multiple
  patterns (``CLAUDE_API_KEY`` looks like an env var AND
  like an API parameter). The extractor uses
  :func:`_dominant_type` to pick one. Future work could
  surface the alternates as separate rows; for MVP, one
  term per string is fine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.enums import TermType
from app.worker.chunker import ChunkDraft

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
#
# Each pattern is anchored to the start of the token. We
# don't use word boundaries alone because ``--model`` has
# the boundary inside the token.

_FLAG_RE = re.compile(r"--[a-z][a-z0-9-]{1,40}")
_SLASH_CMD_RE = re.compile(r"(?<!\w)/[a-z][a-z0-9-]{1,40}")
_ENV_VAR_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,40}\b")
_HEADER_RE = re.compile(r"\bx-[a-z][a-z0-9-]{2,30}-[a-z][a-z0-9-]{2,30}\b")
# ``file_name`` is the most ambiguous pattern — a file
# with a ``.ext`` extension. Two cases:
#
# 1. ``foo.json`` — a regular file. The pattern matches
#    the basename + extension.
# 2. ``.bashrc`` — a hidden file with no extension. The
#    pattern matches the dotfile name (no extension).
#
# Both are useful; the regex is a union of the two.
_FILE_NAME_RE = re.compile(
    r"(?:\b[a-z][a-z0-9_-]{1,40}\.[a-z0-9]{1,5}\b|\B\.[a-z][a-z0-9_-]{1,40}\b)"
)
# ``api_parameter`` covers things like ``max_tokens``,
# ``temperature``, ``top_p`` — single lowercase tokens.
# We restrict to the documented parameter range.
_API_PARAM_RE = re.compile(r"\b[a-z][a-z0-9_]{2,30}\b")
# ``model_name`` covers Claude / Gemini model names.
_MODEL_NAME_RE = re.compile(
    r"\bclaude-(?:opus|sonnet|haiku)-[0-9]+-[0-9]+|"
    r"\bgemini-[0-9]+-[0-9]+-(?:pro|flash)|"
    r"\bgpt-[0-9]+(?:o|pro|mini)?\b"
)
# ``error_message`` is a quoted, period-free phrase after
# the word "error". Deliberately narrow.
_ERROR_MSG_RE = re.compile(r'"[a-z][a-z0-9 _-]{4,60}"')

# Tokens that look like env vars but are actually just
# normal English (e.g. ``THE``, ``AND``). The first match
# wins; we filter via this allowlist.
_NON_TERMS = frozenset(
    {
        "THE", "AND", "FOR", "WITH", "FROM", "INTO",
        "EVERY", "EACH", "WHEN", "WHILE", "ALSO",
        "ALL", "ANY", "ARE", "NOT", "USE", "USED",
        "SET", "HAS", "HAVE", "THIS", "THAT",
    }
)


@dataclass(frozen=True)
class ExtractedTerm:
    """A term extracted from a chunk.

    The runner turns each one into an :class:`ExactTerm` row
    attached to the source document.
    """

    term_text: str
    term_type: TermType


def extract_terms(chunk: ChunkDraft) -> list[ExtractedTerm]:
    """Extract distinct terms from ``chunk``.

    The order is the order in :data:`_PATTERN_ORDER` — the
    first pattern to claim a token wins, so a string that
    matches both ``_FLAG_RE`` and ``_ENV_VAR_RE`` is kept
    as the flag. The dedup is per (text, type) — the same
    text appearing twice in a chunk is still one row.
    """
    text = chunk.pre_text
    seen: set[tuple[str, TermType]] = set()
    found: list[ExtractedTerm] = []
    for pattern, term_type in _PATTERN_ORDER:
        for match in pattern.finditer(text):
            term = match.group(0)
            if not _is_meaningful(term, term_type):
                continue
            key = (term, term_type)
            if key in seen:
                continue
            seen.add(key)
            found.append(ExtractedTerm(term_text=term, term_type=term_type))
    return found


_PATTERN_ORDER: tuple[tuple[re.Pattern[str], TermType], ...] = (
    (_FLAG_RE, TermType.flag),
    (_SLASH_CMD_RE, TermType.slash_command),
    (_ENV_VAR_RE, TermType.environment_variable),
    (_HEADER_RE, TermType.api_parameter),
    (_FILE_NAME_RE, TermType.file_name),
    (_ERROR_MSG_RE, TermType.error_message),
    (_MODEL_NAME_RE, TermType.model_name),
    (_API_PARAM_RE, TermType.config_key),
)


def _is_meaningful(term: str, term_type: TermType) -> bool:
    """Reject obvious non-terms (e.g. ``THE`` as an env var)."""
    if term_type is TermType.environment_variable and term in _NON_TERMS:
        return False
    return not (
        term_type is TermType.config_key and term.upper() in _NON_TERMS
    )


__all__ = [
    "ExtractedTerm",
    "extract_terms",
]
