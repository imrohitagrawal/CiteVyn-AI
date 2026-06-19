"""Mechanical citation validator.

Lives under :mod:`app.llm` (rather than :mod:`app.validation`) because
the validation logic is tightly coupled to the citation contract
documented in :mod:`app.llm.prompts` and the evidence-block convention
in :mod:`app.llm.stub`. Slice 6 consumes this; tests consume it
directly with arbitrary evidence.

Contract (matches ``docs/API_SPEC.md`` §5 + the LLM client prompt):

* ``[n]`` markers in ``answer_text`` must be 1-indexed and contiguous
  from 1 to ``len(evidence)``. Gaps, ``[0]``, or ``[N+1]`` all fail.
* Every ``[n]`` must reference an evidence bullet that exists.
* Uncited evidence bullets are reported as a warning, not a failure
  (the model may legitimately not cite every retrieved chunk).
* When ``answer_text`` is the no-answer refusal (exact match against
  :data:`app.llm.prompts.NO_ANSWER_REFUSAL`, or contains the canonical
  no-answer substring), the result is ``valid=True`` with empty
  ``cited_indices`` and ``uncited_indices``.
* Hard-fail cases are surfaced by the orchestrator (Slice 6) as a
  no-answer response carrying ``APIErrorCode.citation_validation_failed``
  in the error envelope — that code is mapped to HTTP 200 in
  :mod:`app.core.errors` because it is not a transport failure.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.llm.prompts import NO_ANSWER_REFUSAL
from app.retrieval.types import EvidenceHit

# Matches a citation marker like ``[1]``, ``[12]``. Captures the digits.
_CITATION_RE = re.compile(r"\[(\d+)\]")

# Substring of the refusal the model is contractually required to emit
# when there is no evidence. Used so trimmed responses still pass.
_NO_ANSWER_SUBSTRING = "do not have credible source material"


class CitationValidationResult(BaseModel):
    """Outcome of :func:`validate_citations`.

    ``valid`` is True only when every ``[n]`` in the answer references
    a real evidence bullet and the indices are contiguous from 1 to
    the number of evidence bullets the model actually cited. When
    ``answer_text`` is the no-answer refusal, ``valid`` is True with
    empty citation lists regardless of how many evidence bullets were
    passed in.
    """

    valid: bool
    cited_indices: list[int] = Field(default_factory=list[int])
    uncited_indices: list[int] = Field(default_factory=list[int])
    reason: str | None = None


def _is_no_answer_refusal(answer_text: str) -> bool:
    """Detect the no-answer refusal.

    Accepts both the exact constant and any string that contains the
    canonical no-answer substring (case-insensitive). The latter lets
    the LLM trim trailing punctuation without tripping the validator.
    """
    stripped = answer_text.strip()
    if stripped == NO_ANSWER_REFUSAL:
        return True
    return _NO_ANSWER_SUBSTRING in stripped.lower()


def validate_citations(
    *,
    answer_text: str,
    evidence: list[EvidenceHit],
) -> CitationValidationResult:
    """Check that ``answer_text`` references ``evidence`` correctly.

    Pure function — no DB, no network. Safe to call from any context
    with arbitrary evidence.
    """
    evidence_count = len(evidence)

    if _is_no_answer_refusal(answer_text):
        return CitationValidationResult(valid=True)

    raw_markers = _CITATION_RE.findall(answer_text)
    cited_indices = sorted({int(m) for m in raw_markers})

    # Hard-fail: any out-of-range marker (0 or > evidence_count).
    out_of_range = [n for n in cited_indices if n < 1 or n > evidence_count]
    if out_of_range:
        return CitationValidationResult(
            valid=False,
            cited_indices=cited_indices,
            reason=(
                f"citation index out of range: {out_of_range}; "
                f"evidence has {evidence_count} bullet(s)"
            ),
        )

    # Hard-fail: gap in the contiguous 1..N sequence.
    expected = set(range(1, max(cited_indices, default=0) + 1))
    missing = sorted(expected - set(cited_indices))
    if missing:
        return CitationValidationResult(
            valid=False,
            cited_indices=cited_indices,
            reason=f"citation indices must be contiguous from 1; missing {missing}",
        )

    # Warning only: bullets the model never cited.
    cited_set = set(cited_indices)
    uncited = [n for n in range(1, evidence_count + 1) if n not in cited_set]

    return CitationValidationResult(
        valid=True,
        cited_indices=cited_indices,
        uncited_indices=uncited,
    )
