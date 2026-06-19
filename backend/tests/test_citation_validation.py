"""Citation validator tests.

The validator is pure (no DB, no network) so these tests build
:class:`EvidenceHit` instances by hand. They pin the contract the
LLM client from Slice 4 already honors:

* ``[n]`` markers must be 1-indexed and contiguous.
* Every ``[n]`` must reference an existing evidence bullet.
* Uncited evidence is reported as a warning, not a failure.
* The no-answer refusal short-circuits to ``valid=True`` with empty
  citation lists.
"""

from __future__ import annotations

import uuid

from app.llm.prompts import NO_ANSWER_REFUSAL
from app.llm.validation import validate_citations
from app.models import RetrievalType
from app.retrieval.types import EvidenceHit


def _evidence(*, count: int) -> list[EvidenceHit]:
    """Build ``count`` minimal evidence bullets."""
    hits: list[EvidenceHit] = []
    for i in range(count):
        hits.append(
            EvidenceHit(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                product_area="claude_api",
                source_name="docs.test",
                document_title="Doc",
                section_path="/x",
                heading="H",
                parent_heading=None,
                chunk_text=f"snippet {i + 1}",
                context_summary="summary",
                source_url="https://docs.test/x",
                score=1.0,
                retrieval_type=RetrievalType.hybrid,
                rank=i + 1,
            )
        )
    return hits


def test_valid_answer_with_one_citation() -> None:
    result = validate_citations(
        answer_text="The rate limit is 50 per minute [1].",
        evidence=_evidence(count=1),
    )
    assert result.valid is True
    assert result.cited_indices == [1]
    assert result.uncited_indices == []
    assert result.reason is None


def test_valid_answer_with_multiple_contiguous_citations() -> None:
    result = validate_citations(
        answer_text=(
            "Claude uses a permissions file [1] configured via the CLI [2] "
            "and supports streaming [3]."
        ),
        evidence=_evidence(count=3),
    )
    assert result.valid is True
    assert result.cited_indices == [1, 2, 3]
    assert result.uncited_indices == []
    assert result.reason is None


def test_invalid_citation_index_out_of_range() -> None:
    result = validate_citations(
        answer_text="Per the docs [5].",
        evidence=_evidence(count=2),
    )
    assert result.valid is False
    assert result.cited_indices == [5]
    assert result.reason is not None and "out of range" in result.reason


def test_invalid_citation_index_zero() -> None:
    """``[0]`` is a malformed marker; the contract requires 1-indexing."""
    result = validate_citations(
        answer_text="Per the docs [0].",
        evidence=_evidence(count=1),
    )
    assert result.valid is False
    assert result.cited_indices == [0]
    assert result.reason is not None and "out of range" in result.reason


def test_invalid_gap_in_citation_indices() -> None:
    """``[1]`` and ``[3]`` with no ``[2]`` is a hard failure."""
    result = validate_citations(
        answer_text="Per the docs [1] and followup [3].",
        evidence=_evidence(count=3),
    )
    assert result.valid is False
    assert result.cited_indices == [1, 3]
    assert result.reason is not None and "contiguous" in result.reason
    assert "missing" in result.reason and "2" in result.reason


def test_no_answer_refusal_passes_validation() -> None:
    """An exact no-answer refusal is valid with no citations reported,
    even when evidence was passed in (the orchestrator may have already
    decided to refuse)."""
    result = validate_citations(
        answer_text=NO_ANSWER_REFUSAL,
        evidence=_evidence(count=3),
    )
    assert result.valid is True
    assert result.cited_indices == []
    assert result.uncited_indices == []
    assert result.reason is None


def test_no_answer_refusal_with_trailing_punctuation_passes() -> None:
    """The validator accepts any string that contains the canonical
    no-answer substring so the LLM is free to wrap it with quotes or
    trailing punctuation."""
    result = validate_citations(
        answer_text=f'"{NO_ANSWER_REFUSAL}"',
        evidence=_evidence(count=2),
    )
    assert result.valid is True
    assert result.cited_indices == []
    assert result.uncited_indices == []


def test_uncited_evidence_is_reported_but_does_not_fail() -> None:
    """The model may legitimately not cite every retrieved bullet; we
    surface the unused index in ``uncited_indices`` but keep
    ``valid=True`` so the orchestrator can still serve the answer."""
    result = validate_citations(
        answer_text="Per the docs [1].",
        evidence=_evidence(count=3),
    )
    assert result.valid is True
    assert result.cited_indices == [1]
    assert result.uncited_indices == [2, 3]
    assert result.reason is None


def test_repeated_citation_is_deduplicated_in_cited_indices() -> None:
    """Repeated markers (e.g. ``[1] [1]``) collapse to one entry in
    ``cited_indices`` so the orchestrator's set arithmetic stays
    simple."""
    result = validate_citations(
        answer_text="Per the docs [1] and again [1].",
        evidence=_evidence(count=1),
    )
    assert result.valid is True
    assert result.cited_indices == [1]
    assert result.uncited_indices == []


def test_empty_evidence_and_empty_answer_is_valid() -> None:
    """With no evidence and an empty answer, there are no markers to
    validate and no missing-bullet warnings. (The orchestrator
    would still want a no-answer response, but the validator is
    strict about citations only.)"""
    result = validate_citations(answer_text="", evidence=[])
    assert result.valid is True
    assert result.cited_indices == []
    assert result.uncited_indices == []
    assert result.reason is None


def test_marker_with_text_outside_brackets_is_ignored() -> None:
    """Only ``[n]`` markers count. ``[abc]`` or ``[]`` are not
    citations and must not trigger out-of-range failures."""
    result = validate_citations(
        answer_text="Per the docs [1] (see also [v2] note).",
        evidence=_evidence(count=1),
    )
    assert result.valid is True
    assert result.cited_indices == [1]
