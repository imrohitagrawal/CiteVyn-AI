"""Domain guardrail classification tests."""

from __future__ import annotations

import pytest

from app.guardrails.domain import (
    ALLOWED_DOMAINS,
    Domain,
    classify_domain,
    is_unsupported,
)


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What model should I use for the Claude API?", Domain.claude_api),
        ("claude api rate limits", Domain.claude_api),
        ("How do I configure Claude Code permissions?", Domain.claude_code),
        ("claude-code settings", Domain.claude_code),
        ("What is the --model flag for codex?", Domain.codex),
        ("codex --help output", Domain.codex),
        ("Gemini API rate limits", Domain.gemini_api),
        ("gemini-api streaming", Domain.gemini_api),
        ("gemini usage", Domain.gemini_api),
    ],
)
def test_classify_domain_positive(question: str, expected: Domain) -> None:
    assert classify_domain(question) is expected


@pytest.mark.parametrize(
    "question",
    [
        "Who won the World Cup?",
        "Explain quantum entanglement",
        "Python list comprehension",
        "What is the weather today?",
        "Recipes for chocolate cake",
    ],
)
def test_classify_domain_unsupported(question: str) -> None:
    assert classify_domain(question) is Domain.unsupported


def test_classify_domain_empty_returns_unsupported() -> None:
    assert classify_domain("") is Domain.unsupported
    assert classify_domain("   ") is Domain.unsupported
    assert classify_domain("\n\t") is Domain.unsupported


def test_classify_domain_prefers_claude_code_over_claude_api() -> None:
    """A question that mentions both ``Claude`` and ``Claude Code`` should
    resolve to ``claude_code`` (more specific match wins)."""
    assert (
        classify_domain("How do I configure Claude Code for the Claude API?") is Domain.claude_code
    )


def test_allowed_domains_contains_all_supported() -> None:
    assert Domain.claude_api in ALLOWED_DOMAINS
    assert Domain.claude_code in ALLOWED_DOMAINS
    assert Domain.codex in ALLOWED_DOMAINS
    assert Domain.gemini_api in ALLOWED_DOMAINS
    assert Domain.unsupported not in ALLOWED_DOMAINS


def test_is_unsupported_helper() -> None:
    assert is_unsupported(Domain.unsupported) is True
    assert is_unsupported(Domain.claude_api) is False
