"""Answer generator.

Thin wrapper over the LLM client (:mod:`app.llm`) that embeds the
retrieved evidence in the user prompt. The evidence block convention
matches :mod:`app.llm.stub` so the deterministic stub and the
Anthropic client both interpret the prompt identically:

.. code-block:: text

    Question: <user question>
    EVIDENCE:
    [1] Source: <source_name> | Title: <title> | URL: <url> | Snippet: <text>
    [2] ...

When the evidence list is empty, the generator emits
``EVIDENCE: NONE`` so the LLM is contractually required to refuse
with the no-answer paragraph (see :mod:`app.llm.prompts`).
"""

from __future__ import annotations

from app.llm.prompts import SYSTEM_PROMPT
from app.llm.protocol import LLMClient
from app.llm.types import LLMResult
from app.retrieval.types import EvidenceHit

# Sentinel written to the user prompt when there is no evidence. The
# stub (and the Anthropic system prompt) treat this as "no bullets",
# which forces the no-answer refusal.
_NO_EVIDENCE_SENTINEL = "EVIDENCE: NONE"

# Max characters of each evidence snippet to embed in the prompt.
# The orchestrator never sees the original chunk_text beyond this
# cap; the full text is still persisted in ``retrieved_evidence`` via
# the chunk FK.
_SNIPPET_MAX_CHARS = 400


def _truncate_snippet(text: str, *, limit: int = _SNIPPET_MAX_CHARS) -> str:
    """Return ``text`` capped at ``limit`` characters, on a word boundary.

    Used so the embedded evidence block stays compact even when a
    chunk is long. The validator still runs against the LLM's
    citation markers, not against the embedded text, so the cap is
    only about prompt size.
    """
    if len(text) <= limit:
        return text
    trimmed = text[:limit]
    last_space = trimmed.rfind(" ")
    if last_space <= 0:
        return trimmed
    return trimmed[:last_space]


def _format_evidence(hit: EvidenceHit, *, index: int) -> str:
    """Render a single evidence bullet.

    The format matches the stub's expected convention: ``[n] Source: ...
    | Title: ... | URL: ... | Snippet: ...``. ``Snippet`` is the
    ``chunk_text`` of the hit, truncated to
    :data:`_SNIPPET_MAX_CHARS` so the prompt stays bounded.
    """
    snippet = _truncate_snippet(hit.chunk_text)
    return (
        f"[{index}] Source: {hit.source_name} | "
        f"Title: {hit.document_title} | "
        f"URL: {hit.source_url} | "
        f"Snippet: {snippet}"
    )


def build_user_prompt(question: str, evidence: list[EvidenceHit]) -> str:
    """Build the user prompt for the LLM client.

    Empty evidence emits the ``EVIDENCE: NONE`` sentinel so the
    contract in :mod:`app.llm.prompts` is honored.
    """
    if not evidence:
        return f"Question: {question.strip()}\n{_NO_EVIDENCE_SENTINEL}\n"
    body = "\n".join(_format_evidence(hit, index=i + 1) for i, hit in enumerate(evidence))
    return f"Question: {question.strip()}\nEVIDENCE:\n{body}\n"


class AnswerGenerator:
    """Embeds evidence in the user prompt and calls the LLM client.

    Stateless and safe to share across requests. The orchestrator
    constructs one per :class:`Orchestrator` and reuses it for every
    request that needs a generated answer.
    """

    def __init__(self, llm: LLMClient, *, max_tokens: int, temperature: float) -> None:
        self._llm = llm
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def generate(
        self,
        question: str,
        evidence: list[EvidenceHit],
    ) -> LLMResult:
        """Call the LLM with the evidence block embedded for ``question``.

        Returns the raw :class:`LLMResult`. The orchestrator runs the
        citation validator against ``result.text`` and the evidence
        list before deciding whether the answer is grounded.
        """
        user = build_user_prompt(question, evidence)
        return await self._llm.complete(
            system=SYSTEM_PROMPT,
            user=user,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )


__all__ = ["AnswerGenerator", "build_user_prompt"]
