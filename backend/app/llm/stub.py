"""Deterministic stub LLM client.

The stub is a test double. Same input yields byte-identical output so
the citation validator (Slice 5) and the orchestrator (Slice 6) can
write hermetic tests. It honors the same citation contract as the
Anthropic client but does no model inference.

Evidence-block convention
-------------------------

The orchestrator embeds the evidence in the user prompt as a block
shaped like:

.. code-block:: text

    EVIDENCE:
    [1] Source: docs.test | Title: Permissions | URL: https://... | Snippet: ...
    [2] Source: docs.test | Title: Permissions | URL: https://... | Snippet: ...

When no evidence is available the orchestrator emits ``EVIDENCE: NONE``
and the stub returns the no-answer paragraph.

Truncation
----------

The stub honors ``max_tokens`` by truncating the response to
``max_tokens * 4`` characters. 4 chars/token is a conservative upper
bound; the truncation point is the last whitespace at or before the
limit so we never split a citation marker.
"""

from __future__ import annotations

import re

from app.llm.prompts import NO_ANSWER_REFUSAL
from app.llm.types import LLMProvider, LLMResult

# Convention marker the orchestrator writes into the user prompt.
_EVIDENCE_MARKER = "EVIDENCE:"
_NO_EVIDENCE_SENTINEL = "EVIDENCE: NONE"
_EVIDENCE_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s", re.MULTILINE)

# Approximate chars per token. Conservative upper bound; the stub
# never exceeds this regardless of how the rest of the prompt looks.
_CHARS_PER_TOKEN = 4

# Stub answer template. The bracketed citation is the only one we
# emit when evidence is available; Slice 5 can validate mechanically.
# The template is two short sentences so a ``max_tokens`` budget can
# cleanly include [1] and drop the trailing sentence.
_CITED_ANSWER_TEMPLATE = (
    "Per the cited source [1], this is documented behavior. See the source for the exact details."
)


def _has_evidence(user: str) -> int:
    """Return the number of evidence bullets the orchestrator embedded.

    Zero (including the no-evidence sentinel) means the stub should
    produce a no-answer response.
    """
    if _NO_EVIDENCE_SENTINEL in user:
        return 0
    marker_idx = user.find(_EVIDENCE_MARKER)
    if marker_idx == -1:
        return 0
    tail = user[marker_idx + len(_EVIDENCE_MARKER) :]
    return len(_EVIDENCE_LINE_RE.findall(tail))


def _truncate_to_token_budget(text: str, max_tokens: int) -> str:
    """Trim ``text`` so it fits ``max_tokens * 4`` characters.

    Truncates at the last whitespace at or before the limit so we
    never split a citation marker in half.
    """
    if max_tokens <= 0:
        return ""
    limit = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= limit:
        return text
    trimmed = text[:limit]
    last_space = trimmed.rfind(" ")
    if last_space == -1:
        return trimmed
    return trimmed[:last_space]


class StubLLMClient:
    """Deterministic LLM stub for tests and offline development."""

    def __init__(self, *, model: str = "stub-deterministic-v1") -> None:
        self._model = model

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResult:
        # ``temperature`` is accepted to satisfy the protocol; the
        # stub ignores it so its output is fully determined by
        # ``user`` and ``max_tokens``.
        del temperature
        evidence_count = _has_evidence(user)
        raw = NO_ANSWER_REFUSAL if evidence_count == 0 else _CITED_ANSWER_TEMPLATE
        text = _truncate_to_token_budget(raw, max_tokens)
        # ``input_tokens`` mirrors what the orchestrator sent; the
        # stub does not run a real tokenizer. 4 chars/token is the
        # same convention used in ``_truncate_to_token_budget``.
        input_tokens = max(1, (len(system) + len(user)) // _CHARS_PER_TOKEN)
        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=max(1, len(text) // _CHARS_PER_TOKEN),
            model=self._model,
            provider=LLMProvider.stub.value,
        )
