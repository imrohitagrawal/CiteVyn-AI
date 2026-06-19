"""Intent router classification tests."""

from __future__ import annotations

import pytest

from app.guardrails.domain import Domain
from app.routing.intent import (
    Intent,
    classify_intent,
    should_skip_retrieval,
)


def test_unsupported_domain_short_circuits_to_unsupported() -> None:
    assert classify_intent("anything", Domain.unsupported) is Intent.unsupported


def test_exact_lookup_recognized_via_flag() -> None:
    assert (
        classify_intent("What is the --model flag for codex?", Domain.codex) is Intent.exact_lookup
    )


def test_exact_lookup_recognized_via_env_var() -> None:
    assert classify_intent("Set OPENAI_API_KEY for me", Domain.codex) is Intent.exact_lookup


def test_how_to_recognized() -> None:
    assert (
        classify_intent("How do I configure Claude Code permissions?", Domain.claude_code)
        is Intent.how_to
    )


def test_faq_default_for_factual_questions() -> None:
    assert classify_intent("What is Claude?", Domain.claude_api) is Intent.faq


def test_clarify_for_short_fragments() -> None:
    assert classify_intent("hi", Domain.claude_api) is Intent.clarify


def test_should_skip_retrieval_for_unsupported_and_clarify() -> None:
    assert should_skip_retrieval(Intent.unsupported) is True
    assert should_skip_retrieval(Intent.clarify) is True
    assert should_skip_retrieval(Intent.faq) is False
    assert should_skip_retrieval(Intent.how_to) is False
    assert should_skip_retrieval(Intent.exact_lookup) is False
    assert should_skip_retrieval(Intent.no_answer) is False


@pytest.mark.parametrize("empty", ["", "   ", "\n\t"])
def test_empty_question_is_clarify_when_domain_supported(empty: str) -> None:
    assert classify_intent(empty, Domain.claude_api) is Intent.clarify
