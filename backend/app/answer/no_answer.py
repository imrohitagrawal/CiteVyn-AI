"""No-answer fallback.

Single source of truth for the response shape when the orchestrator
cannot produce a grounded answer. The orchestrator short-circuits to
:func:`build_no_answer_response` whenever:

* the intent is ``unsupported`` (the guardrail refused the question),
* the intent is ``no_answer`` (the router never produces this from
  text; it is set by the orchestrator when retrieval yields zero
  evidence),
* the retrieval layer returns an empty evidence list,
* the LLM emits the no-answer refusal,
* the citation validator rejects the LLM's output.

The shape matches the orchestrator's response contract
(``docs/API_SPEC.md`` §5) but is built without touching the
database so it stays cheap to call on the hot path.
"""

from __future__ import annotations

from app.routing.intent import Intent

# Map from orchestrator exit-reason to the public ``no_answer`` flag.
# Every reason maps to True so clients see one consistent flag.
_NO_ANSWER_REASONS: frozenset[str] = frozenset(
    {"unsupported", "weak_evidence", "no_answer", "citation_validation_failed"}
)


def build_no_answer_response(
    *,
    request_id: str,
    domain_value: str,
    intent: Intent,
    reason: str,
    copy: str,
    message_id: str | None = None,
    retrieval_strategy: str = "none",
) -> dict[str, object]:
    """Build the canonical no-answer response shape.

    ``reason`` is one of the keys in :data:`_NO_ANSWER_REASONS` so the
    audit event can record why the orchestrator bailed. ``copy`` is
    the user-visible string (usually ``settings.unsupported_refusal``
    or ``settings.no_answer_fallback``). ``retrieval_strategy``
    defaults to ``"none"``; the citation-validation-failed path
    passes the strategy the retriever actually attempted so the
    observability layer can see the attempt.

    The function is pure and does not touch the database;
    persistence happens in the orchestrator.
    """
    if reason not in _NO_ANSWER_REASONS:
        # Defensive: the orchestrator should never ask for the
        # no-answer shape with an unrecognized reason. ``unsupported``
        # is the safe default.
        reason = "unsupported"
    unsupported = reason == "unsupported"
    # Only the unsupported reason flips ``unsupported: true``; the
    # other reasons ride the no-answer channel.
    return {
        "request_id": request_id,
        "message_id": message_id,
        "answer": copy,
        "citations": [],
        "domain": domain_value,
        "intent": intent.value,
        "confidence": "none",
        "cache_hit": False,
        "retrieval_strategy": retrieval_strategy,
        "unsupported": unsupported,
        "no_answer": True,
        "source_version_hash": "",
        "answer_policy_version": "",
    }


__all__ = ["build_no_answer_response"]
