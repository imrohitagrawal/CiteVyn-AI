"""Tests for :mod:`app.worker.parser`."""

from __future__ import annotations

from app.worker.parser import parse_markdown


def test_parse_empty_returns_empty_document() -> None:
    parsed = parse_markdown("")
    assert parsed.title == ""
    assert parsed.blocks == []


def test_parse_extracts_title_from_h1() -> None:
    parsed = parse_markdown("# Hello World\n\n## Section\n\nbody text\n")
    assert parsed.title == "Hello World"


def test_parse_extracts_blocks_from_h2() -> None:
    raw = "# Title\n## Section A\nfirst body\n## Section B\nsecond body\n"
    parsed = parse_markdown(raw)
    assert len(parsed.blocks) == 2
    assert parsed.blocks[0].heading == "Section A"
    assert parsed.blocks[0].text == "first body"
    assert parsed.blocks[1].heading == "Section B"
    assert parsed.blocks[1].text == "second body"


def test_parse_joins_multiline_body() -> None:
    raw = "# T\n## H\nline one\nline two\nline three\n"
    parsed = parse_markdown(raw)
    assert parsed.blocks[0].text == "line one line two line three"


def test_parse_skips_pre_h1_body() -> None:
    """Text before the first H1 is dropped (no orphan block)."""
    raw = "preamble line\n# Title\n## H\nbody\n"
    parsed = parse_markdown(raw)
    assert parsed.title == "Title"
    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].text == "body"


def test_parse_no_h1_returns_empty_title() -> None:
    parsed = parse_markdown("## Only H2\nbody\n")
    assert parsed.title == ""
    assert len(parsed.blocks) == 1


def test_parse_full_claude_api_fixture() -> None:
    """The Claude API fixture parses to one H1 + three H2 blocks."""
    from pathlib import Path

    # Resolve relative to *this* test file so the test works
    # regardless of pytest's CWD (CI uses ``backend``, local
    # ``make`` invocations use the repo root).
    fixture = Path(__file__).resolve().parent / "fixtures" / "sources" / "claude_api.md"
    raw = fixture.read_text(encoding="utf-8")
    parsed = parse_markdown(raw)
    assert parsed.title == "Claude API Reference"
    assert [b.heading for b in parsed.blocks] == [
        "Rate limits",
        "Authentication",
        "Models",
    ]


def test_parse_skips_blank_lines() -> None:
    """Blank lines do not produce empty blocks or break body joining."""
    raw = "# T\n\n## H\n\nbody\n\n"
    parsed = parse_markdown(raw)
    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].text == "body"
