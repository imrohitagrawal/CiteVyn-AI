"""No-answer fallback tests.

Pins the contract for :func:`app.answer.no_answer.build_no_answer_response`:

* Every reason flag maps to ``no_answer: true``.
* Only ``reason="unsupported"`` flips the ``unsupported`` flag; the
  other reasons ride the no-answer channel.
* Confidence is always ``"none"`` and citations are always ``[]`` —
  the no-answer path never cites a chunk.
* The retrieval strategy is always ``"none"`` because no retrieval
  outcome is available.
* The function is pure — it does not touch the database.
* Unknown reasons fall back to ``"unsupported"`` defensively so a
  caller cannot accidentally mint a new public flag.
"""

from __future__ import annotations

import pytest

from app.answer.no_answer import build_no_answer_response
from app.routing.intent import Intent


def test_unsupported_reason_flips_unsupported_flag() -> None:
    response = build_no_answer_response(
        request_id="req_1",
        domain_value="unsupported",
        intent=Intent.unsupported,
        reason="unsupported",
        copy="refusal copy",
    )
    assert response["unsupported"] is True
    assert response["no_answer"] is True
    assert response["intent"] == "unsupported"
    assert response["domain"] == "unsupported"


@pytest.mark.parametrize("reason", ["weak_evidence", "no_answer", "citation_validation_failed"])
def test_other_reasons_keep_unsupported_false(reason: str) -> None:
    response = build_no_answer_response(
        request_id="req_1",
        domain_value="claude_api",
        intent=Intent.faq,
        reason=reason,
        copy="refusal copy",
    )
    assert response["unsupported"] is False
    assert response["no_answer"] is True
    assert response["domain"] == "claude_api"
    assert response["intent"] == "faq"


def test_response_carries_no_citations_and_no_confidence() -> None:
    response = build_no_answer_response(
        request_id="req_1",
        domain_value="claude_code",
        intent=Intent.how_to,
        reason="weak_evidence",
        copy="copy",
    )
    assert response["citations"] == []
    assert response["confidence"] == "none"
    assert response["cache_hit"] is False
    assert response["retrieval_strategy"] == "none"
    assert response["source_version_hash"] == ""
    assert response["answer_policy_version"] == ""


def test_message_id_is_threaded_through() -> None:
    response = build_no_answer_response(
        request_id="req_1",
        domain_value="claude_api",
        intent=Intent.faq,
        reason="weak_evidence",
        copy="copy",
        message_id="msg_42",
    )
    assert response["message_id"] == "msg_42"


def test_message_id_defaults_to_none() -> None:
    response = build_no_answer_response(
        request_id="req_1",
        domain_value="claude_api",
        intent=Intent.faq,
        reason="no_answer",
        copy="copy",
    )
    assert response["message_id"] is None


def test_unknown_reason_falls_back_to_unsupported() -> None:
    """An unrecognized reason must not mint a new public flag — the
    response flips to the supported ``unsupported`` reason so a
    downstream caller cannot tell the difference between a real
    unsupported refusal and a misconfigured orchestrator."""
    response = build_no_answer_response(
        request_id="req_1",
        domain_value="claude_api",
        intent=Intent.faq,
        reason="not-a-real-reason",
        copy="copy",
    )
    assert response["unsupported"] is True
    assert response["no_answer"] is True


def test_response_does_not_touch_the_database() -> None:
    """The function must be pure. We call it without any session
    and assert the returned shape is a plain dict (no SQLAlchemy
    state attached)."""
    response = build_no_answer_response(
        request_id="req_1",
        domain_value="claude_api",
        intent=Intent.faq,
        reason="weak_evidence",
        copy="copy",
    )
    assert isinstance(response, dict)
    # No SQLAlchemy ``_sa_instance_state`` attribute on any value.
    for value in response.values():
        assert not hasattr(value, "_sa_instance_state")
