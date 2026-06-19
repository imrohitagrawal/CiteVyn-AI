"""Slice 4 LLM client package.

Provides the LLM seam used by the answer engine (Slice 6):

* :class:`LLMClient` — protocol the answer engine depends on.
* :class:`LLMResult` — value object every client returns.
* :class:`StubLLMClient` — deterministic test double that emits
  citation-valid answers from the evidence block embedded in the user
  prompt.
* :class:`AnthropicLLMClient` — production HTTP client against the
  Anthropic ``/v1/messages`` endpoint.
* :func:`build_llm_client` — factory keyed off ``Settings.llm_provider``.
* :func:`validate_citations` — mechanical validator the orchestrator
  runs against the LLM output (Slice 5).

The clients are pure — no caching, no retrieval, no domain check. The
orchestrator composes them with those concerns.
"""

from app.llm.anthropic import AnthropicLLMClient
from app.llm.errors import LLMUnavailable
from app.llm.factory import build_llm_client
from app.llm.protocol import LLMClient
from app.llm.stub import StubLLMClient
from app.llm.types import LLMProvider, LLMResult
from app.llm.validation import CitationValidationResult, validate_citations

__all__ = [
    "AnthropicLLMClient",
    "CitationValidationResult",
    "LLMClient",
    "LLMProvider",
    "LLMResult",
    "LLMUnavailable",
    "StubLLMClient",
    "build_llm_client",
    "validate_citations",
]
