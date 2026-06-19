"""LLM client protocol.

The answer engine (Slice 6) and tests depend on this protocol. Any
object that implements :meth:`complete` with the documented signature
satisfies it — no inheritance required.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.types import LLMResult


@runtime_checkable
class LLMClient(Protocol):
    """Async LLM completion seam.

    Implementations MUST be safe to instantiate once per process and
    reuse across requests. The orchestrator calls ``complete`` once
    per ``POST /v1/sessions/{id}/messages``.
    """

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResult: ...
