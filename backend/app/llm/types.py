"""Value objects produced by every LLM client.

Kept dependency-free so the answer engine can import them without
pulling httpx into its surface.
"""

from __future__ import annotations

import enum
from typing import Literal

from pydantic import BaseModel, Field


class LLMProvider(enum.StrEnum):
    """Provider identifier embedded in :class:`LLMResult` for tracing."""

    stub = "stub"
    anthropic = "anthropic"
    # Gemini and the secondary multi-provider land in Slice 9b; the enum members are
    # declared so :class:`LLMResult.provider` already accepts them
    # before the corresponding client implementations are wired.
    gemini = "gemini"
    PROVIDER_ROUTER = "router"


class LLMResult(BaseModel):
    """Result returned by :meth:`LLMClient.complete`.

    The orchestrator (Slice 6) consumes ``text`` for the user-visible
    answer and the token counts for cost / observability; ``model`` and
    ``provider`` ride along in the audit trail.
    """

    text: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    model: str
    provider: Literal["stub", "anthropic", "gemini", "router"]
