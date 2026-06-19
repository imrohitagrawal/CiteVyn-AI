"""Slice 6 answer engine.

Composes the Slice 4-5 seams (domain guardrail, intent router, hybrid
retrieval, LLM client, citation validator, answer cache) with the
session/message/evidence/audit persistence from Slice 2. The HTTP
route in Slice 7 sits on top of :class:`Orchestrator`.

* :mod:`app.answer.generate` — the answer generator. Embeds evidence
  in the user prompt and calls the LLM client.
* :mod:`app.answer.no_answer` — single source of truth for the
  no-answer response shape.
* :mod:`app.answer.orchestrator` — composes everything and persists
  the trace.
"""

from app.answer.generate import AnswerGenerator, build_user_prompt
from app.answer.no_answer import build_no_answer_response
from app.answer.orchestrator import (
    AnswerResponse,
    Citation,
    Orchestrator,
    OrchestratorError,
    RetrievalStrategy,
)

__all__ = [
    "AnswerGenerator",
    "AnswerResponse",
    "Citation",
    "Orchestrator",
    "OrchestratorError",
    "RetrievalStrategy",
    "build_no_answer_response",
    "build_user_prompt",
]
