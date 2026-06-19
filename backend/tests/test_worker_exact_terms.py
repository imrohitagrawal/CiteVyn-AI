"""Tests for :mod:`app.worker.exact_terms`."""

from __future__ import annotations

from app.models.enums import TermType
from app.worker.chunker import ChunkDraft
from app.worker.exact_terms import extract_terms


def _draft(text: str) -> ChunkDraft:
    """Build a one-line :class:`ChunkDraft` for ``text``."""
    return ChunkDraft(chunk_order=0, heading="H", text=text, pre_text=text)


def test_extracts_double_dash_flag() -> None:
    terms = extract_terms(_draft("Use the --model flag."))
    flag = next(t for t in terms if t.term_text == "--model")
    assert flag.term_type is TermType.flag


def test_extracts_env_var() -> None:
    terms = extract_terms(_draft("Set CLAUDE_API_KEY in the env."))
    env = next(t for t in terms if t.term_text == "CLAUDE_API_KEY")
    assert env.term_type is TermType.environment_variable


def test_extracts_http_header() -> None:
    terms = extract_terms(_draft("Pass it in the x-api-key header."))
    hdr = next(t for t in terms if t.term_text == "x-api-key")
    assert hdr.term_type is TermType.api_parameter


def test_extracts_slash_command() -> None:
    terms = extract_terms(_draft("Type /help to see commands."))
    cmd = next(t for t in terms if t.term_text == "/help")
    assert cmd.term_type is TermType.slash_command


def test_extracts_model_name() -> None:
    terms = extract_terms(_draft("Use claude-opus-4-7 or gemini-2-5-pro."))
    models = {t.term_text for t in terms if t.term_type is TermType.model_name}
    assert "claude-opus-4-7" in models
    assert "gemini-2-5-pro" in models


def test_extracts_error_message() -> None:
    terms = extract_terms(_draft('A "rate limit exceeded" error means...'))
    err = next(t for t in terms if t.term_text == '"rate limit exceeded"')
    assert err.term_type is TermType.error_message


def test_skips_english_words_as_env_vars() -> None:
    """``THE`` / ``AND`` etc. are not env vars."""
    terms = extract_terms(_draft("The api uses AND or for things."))
    assert all(t.term_text not in {"THE", "AND", "FOR", "OR"} for t in terms)


def test_dedupes_within_a_chunk() -> None:
    """Same term twice in a chunk is one row."""
    terms = extract_terms(_draft("--model and --model again"))
    flags = [t for t in terms if t.term_text == "--model"]
    assert len(flags) == 1


def test_empty_chunk_yields_no_terms() -> None:
    terms = extract_terms(_draft(""))
    assert terms == []


def test_filename_extracted() -> None:
    terms = extract_terms(_draft("Edit the .bashrc file."))
    fn = next((t for t in terms if t.term_text == ".bashrc"), None)
    assert fn is not None
    assert fn.term_type is TermType.file_name
