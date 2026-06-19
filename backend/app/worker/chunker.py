"""Contextual chunker.

Splits a :class:`ParsedDocument` into chunk-shaped drafts
the runner will persist as :class:`Chunk` rows. The MVP
chunker is heading-aware: one chunk per ``## H2`` section,
prepended with the document title so the retriever sees
context like "Claude API Reference — Rate limits" and not
just "Rate limits".

Design notes
------------
* One block == one chunk. The MVP fixtures are small enough
  that splitting a block across chunks would lose context.
  A production rollout with long doc pages may need to
  split blocks at sentence boundaries; the seam is here
  (replace :func:`chunk_document` with a smarter version)
  but the data shape (``ChunkDraft``) is what the DB schema
  expects.
* Each chunk carries the document title + section heading
  in its text. The retriever's reranker uses the heading
  signal to score chunks; prepending the title improves
  cross-section recall when two products share a heading
  ("Authentication" is in both Claude API and Gemini API).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.worker.allowlist import SourceSpec
from app.worker.parser import Block, ParsedDocument


@dataclass(frozen=True)
class ChunkDraft:
    """A pre-persistence chunk.

    The runner turns each :class:`ChunkDraft` into a
    :class:`Chunk` row, attaches it to a :class:`Document`,
    and pushes it through the embedder.
    """

    chunk_order: int
    heading: str
    text: str
    # Pre-computed for the exact-term extractor; saves a
    # re-scan in :func:`app.worker.exact_terms.extract_terms`.
    pre_text: str


def chunk_document(
    parsed: ParsedDocument,
    *,
    source: SourceSpec,
    title_fallback: str | None = None,
) -> list[ChunkDraft]:
    """Turn ``parsed`` into one :class:`ChunkDraft` per block.

    ``title_fallback`` is used when the document has no
    ``# H1`` line. The runner passes ``source.title`` so a
    empty-title parser result still produces titled chunks.
    """
    title = parsed.title or title_fallback or source.title
    drafts: list[ChunkDraft] = []
    for order, block in enumerate(parsed.blocks):
        drafts.append(_build_draft(order=order, title=title, block=block))
    return drafts


def _build_draft(
    *,
    order: int,
    title: str,
    block: Block,
) -> ChunkDraft:
    """Build one chunk draft from a section block.

    The text is ``"{title} — {heading}. {body}"`` — the
    "contextual" prefix. ``pre_text`` strips the prefix
    when the exact-term extractor only needs the body, so a
    flag like ``--model`` is not double-counted.
    """
    text = f"{title} — {block.heading}. {block.text}"
    pre_text = block.text
    return ChunkDraft(
        chunk_order=order,
        heading=block.heading,
        text=text,
        pre_text=pre_text,
    )


__all__ = [
    "ChunkDraft",
    "chunk_document",
]
