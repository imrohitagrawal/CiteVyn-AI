"""Anthropic Messages API client.

Speaks to ``{anthropic_api_base}/v1/messages``. The transport is
:mod:`httpx`; callers may inject a pre-built ``AsyncClient`` for
testing (e.g. via :class:`httpx.MockTransport`).

Errors
------

5xx responses and transport timeouts raise :class:`LLMUnavailable`.
4xx responses (bad request, auth failure) are not retried by this
client — they surface as :class:`LLMUnavailable` too because, from
the orchestrator's perspective, the provider is not currently
delivering the answer. The orchestrator can inspect the ``cause`` to
distinguish the two if needed.
"""

from __future__ import annotations

import json
from typing import Any, cast

import httpx

from app.llm.errors import LLMUnavailable
from app.llm.types import LLMProvider, LLMResult

# Status codes the orchestrator treats as "provider unavailable".
# 4xx other than 408/429 are configuration errors (bad prompt, bad
# key) — we still raise LLMUnavailable so the orchestrator can decide.
_UNAVAILABLE_STATUSES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})


def _extract_text(content_blocks: list[dict[str, Any]]) -> str:
    """Pull the first text block out of a Messages API content array.

    Defensive: the API can return a mix of text, tool_use, and
    thinking blocks. We return only text. If there is no text block
    we return the empty string.
    """
    for block in content_blocks:
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                return text
    return ""


class AnthropicLLMClient:
    """Real HTTP client for the Anthropic Messages API."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        api_base: str,
        api_version: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "CITEVYN_ANTHROPIC_API_KEY is required when CITEVYN_LLM_PROVIDER=anthropic"
            )
        self._model = model
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._api_version = api_version
        self._timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds,
        )

    async def aclose(self) -> None:
        """Close the underlying httpx client if we own it."""
        if self._owns_client:
            await self._http_client.aclose()

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResult:
        url = f"{self._api_base}/v1/messages"
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._api_version,
            "content-type": "application/json",
        }
        try:
            response = await self._http_client.post(
                url,
                json=payload,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(
                f"Anthropic request timed out after {self._timeout_seconds}s",
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            # Covers connection errors, protocol errors, etc.
            raise LLMUnavailable(
                f"Anthropic transport error: {exc.__class__.__name__}",
                cause=exc,
            ) from exc

        if response.status_code in _UNAVAILABLE_STATUSES:
            raise LLMUnavailable(
                f"Anthropic returned {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            # Other client errors (400/401/403) — still not retried by
            # this client. Orchestrator decides.
            raise LLMUnavailable(
                f"Anthropic returned {response.status_code}: {response.text[:200]}"
            )

        try:
            raw_data: Any = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(
                "Anthropic returned non-JSON body",
                cause=exc,
            ) from exc
        # The Messages API JSON shape is well documented but the wire
        # is not type-narrowed; cast to a dict and validate fields
        # defensively as we read them.
        data = cast(dict[str, Any], raw_data)

        content = data.get("content")
        if not isinstance(content, list):
            raise LLMUnavailable("Anthropic response missing 'content' array")
        text = _extract_text(cast(list[dict[str, Any]], content))

        usage_raw: Any = data.get("usage") or {}
        usage = cast(dict[str, Any], usage_raw)
        input_tokens = int(cast(int, usage.get("input_tokens", 0)))
        output_tokens = int(cast(int, usage.get("output_tokens", 0)))
        model = str(cast(str, data.get("model", self._model)))

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            provider=LLMProvider.anthropic.value,
        )
