"""Factory that builds an :class:`LLMClient` from :class:`Settings`.

Mirrors :func:`app.retrieval.vector.build_embedder` so the answer
engine can resolve both clients the same way.
"""

from __future__ import annotations

from app.core.config import Settings
from app.llm.anthropic import AnthropicLLMClient
from app.llm.protocol import LLMClient
from app.llm.stub import StubLLMClient


def build_llm_client(settings: Settings) -> LLMClient:
    """Return the LLM client selected by ``settings.llm_provider``.

    The factory never raises on missing API keys for the stub path;
    the anthropic path raises eagerly so a misconfigured production
    deploy fails at startup instead of on the first request.
    """
    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            api_base=settings.anthropic_api_base,
            api_version=settings.anthropic_api_version,
            timeout_seconds=settings.anthropic_timeout_seconds,
        )
    return StubLLMClient(model=f"stub-{settings.llm_model}")
