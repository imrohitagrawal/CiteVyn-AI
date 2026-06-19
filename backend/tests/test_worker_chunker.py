"""Tests for :mod:`app.worker.chunker`."""

from __future__ import annotations

from app.worker.allowlist import SourceSpec
from app.worker.chunker import chunk_document
from app.worker.parser import parse_markdown


def _spec() -> SourceSpec:
    return SourceSpec(
        name="claude_api",
        product_area="claude_api",
        title="Claude API Reference",
        fetcher="local",
        location="tests/fixtures/sources/claude_api.md",
    )


def test_chunk_document_produces_one_draft_per_block() -> None:
    parsed = parse_markdown(
        "# T\n## A\nbody a\n## B\nbody b\n## C\nbody c\n"
    )
    drafts = chunk_document(parsed, source=_spec())
    assert len(drafts) == 3
    assert [d.heading for d in drafts] == ["A", "B", "C"]
    assert [d.chunk_order for d in drafts] == [0, 1, 2]


def test_chunk_document_prepends_title() -> None:
    """Each chunk's text starts with the document title + heading prefix."""
    parsed = parse_markdown("# T\n## H\nbody\n")
    drafts = chunk_document(parsed, source=_spec())
    assert drafts[0].text.startswith("T — H.")
    assert "body" in drafts[0].text


def test_chunk_document_uses_fallback_title_when_empty() -> None:
    """If the parse has no H1, the source's title is used."""
    parsed = parse_markdown("## H\nbody\n")
    drafts = chunk_document(parsed, source=_spec())
    assert drafts[0].text.startswith("Claude API Reference — H.")


def test_chunk_document_uses_explicit_title_fallback() -> None:
    """An explicit ``title_fallback`` wins over ``source.title``."""
    parsed = parse_markdown("## H\nbody\n")
    drafts = chunk_document(parsed, source=_spec(), title_fallback="Custom Title")
    assert drafts[0].text.startswith("Custom Title — H.")


def test_chunk_document_pre_text_is_body_only() -> None:
    """``pre_text`` is the body, not the title-prefixed text — the extractor needs the body."""
    parsed = parse_markdown("# T\n## H\nbody\n")
    drafts = chunk_document(parsed, source=_spec())
    assert drafts[0].pre_text == "body"
    assert "T" not in drafts[0].pre_text
