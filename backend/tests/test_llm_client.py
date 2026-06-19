"""Slice 4 LLM client tests.

Covers:

* :class:`StubLLMClient` emits a citation-valid answer when the
  orchestrator-formatted evidence block is present.
* :class:`StubLLMClient` emits the no-answer paragraph when the
  evidence block is empty.
* :class:`StubLLMClient` honors ``max_tokens`` by truncating.
* :func:`build_llm_client` selects the stub or anthropic client per
  ``Settings.llm_provider``.
* :class:`AnthropicLLMClient` raises :class:`LLMUnavailable` on 5xx,
  exercised via ``httpx.MockTransport`` (no network).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.llm.anthropic import AnthropicLLMClient
from app.llm.errors import LLMUnavailable
from app.llm.factory import build_llm_client
from app.llm.protocol import LLMClient
from app.llm.stub import StubLLMClient

# ``asyncio_mode=auto`` in pyproject.toml already runs async tests in
# the event loop; we only need to import pytest for the synchronous
# ``raises`` blocks below.


# ---------------------------------------------------------------------------
# StubLLMClient
# ---------------------------------------------------------------------------


async def test_stub_returns_citation_when_evidence_present() -> None:
    client = StubLLMClient()
    user = (
        "Question: How do I configure Claude Code permissions?\n"
        "EVIDENCE:\n"
        "[1] Source: docs.test | Title: Permissions | URL: https://docs.test/cc"
        " | Snippet: Claude Code uses a permissions file.\n"
    )
    result = await client.complete(
        system="sys",
        user=user,
        max_tokens=1024,
        temperature=0.0,
    )
    assert result.provider == "stub"
    assert result.text  # non-empty
    # Mechanical-shape check: at least one [n] citation marker.
    assert "[1]" in result.text
    # Stub is deterministic: same input → byte-identical text.
    again = await client.complete(
        system="sys",
        user=user,
        max_tokens=1024,
        temperature=0.0,
    )
    assert again.text == result.text


async def test_stub_returns_no_answer_when_evidence_empty() -> None:
    client = StubLLMClient()
    user = "Question: Tell me about Claude Code.\nEVIDENCE: NONE\n"
    result = await client.complete(
        system="sys",
        user=user,
        max_tokens=1024,
        temperature=0.0,
    )
    assert "[1]" not in result.text
    assert "do not have credible source material" in result.text.lower()


async def test_stub_returns_no_answer_when_marker_missing() -> None:
    """A bare user prompt with no ``EVIDENCE:`` marker is treated as
    evidence-empty. The orchestrator contract guarantees the marker
    is always present, but the stub is robust to misformed input."""
    client = StubLLMClient()
    result = await client.complete(
        system="sys",
        user="Just a question, no marker here.",
        max_tokens=1024,
        temperature=0.0,
    )
    assert "[1]" not in result.text
    assert "do not have credible source material" in result.text.lower()


async def test_stub_honors_max_tokens_by_truncating() -> None:
    """Truncation policy: ``max_tokens * 4`` characters, cut at the
    last whitespace at or before the limit. The cited template is two
    short sentences; at a tight budget the citation marker survives
    while the trailing sentence is dropped."""
    client = StubLLMClient()
    user = (
        "Question: Tell me everything.\nEVIDENCE:\n[1] Source: a | Title: b | URL: c | Snippet: d\n"
    )
    full = await client.complete(
        system="sys",
        user=user,
        max_tokens=1024,
        temperature=0.0,
    )
    truncated = await client.complete(
        system="sys",
        user=user,
        max_tokens=8,
        temperature=0.0,
    )
    # max_tokens=8 → at most 32 chars, trimmed at a word boundary.
    assert len(truncated.text) <= 32
    assert len(truncated.text) < len(full.text)
    # Citation marker survives at max_tokens=8; trailing sentence is
    # dropped by the word-boundary truncation.
    assert "[1]" in truncated.text
    assert "See the source" not in truncated.text
    # Token accounting is consistent with the truncation heuristic.
    assert truncated.output_tokens <= 8


# ---------------------------------------------------------------------------
# build_llm_client factory
# ---------------------------------------------------------------------------


def test_build_llm_client_returns_stub_by_default() -> None:
    settings = Settings()
    assert settings.llm_provider == "stub"
    client = build_llm_client(settings)
    assert isinstance(client, StubLLMClient)
    assert isinstance(client, LLMClient)


def test_build_llm_client_honors_provider_setting(monkeypatch) -> None:
    monkeypatch.setenv("CITEVYN_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CITEVYN_ANTHROPIC_API_KEY", "sk-test")
    get_settings.cache_clear()
    try:
        client = build_llm_client(get_settings())
        assert isinstance(client, AnthropicLLMClient)
    finally:
        get_settings.cache_clear()


def test_build_llm_client_anthropic_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("CITEVYN_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("CITEVYN_ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            build_llm_client(get_settings())
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# AnthropicLLMClient — transport errors via httpx.MockTransport
# ---------------------------------------------------------------------------


def _anthropic_client(handler) -> AnthropicLLMClient:
    """Build an AnthropicLLMClient whose HTTP transport is faked."""
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url="https://api.anthropic.com",
    )
    return AnthropicLLMClient(
        model="claude-opus-4-8",
        api_key="sk-test",
        api_base="https://api.anthropic.com",
        api_version="2023-06-01",
        timeout_seconds=5.0,
        http_client=http_client,
    )


async def test_anthropic_client_surfaces_llm_unavailable_on_5xx() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    client = _anthropic_client(handler)
    try:
        with pytest.raises(LLMUnavailable):
            await client.complete(
                system="sys",
                user="hi",
                max_tokens=64,
                temperature=0.0,
            )
    finally:
        await client.aclose()


async def test_anthropic_client_surfaces_llm_unavailable_on_429() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate_limited"})

    client = _anthropic_client(handler)
    try:
        with pytest.raises(LLMUnavailable):
            await client.complete(
                system="sys",
                user="hi",
                max_tokens=64,
                temperature=0.0,
            )
    finally:
        await client.aclose()


async def test_anthropic_client_surfaces_llm_unavailable_on_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    client = _anthropic_client(handler)
    try:
        with pytest.raises(LLMUnavailable) as info:
            await client.complete(
                system="sys",
                user="hi",
                max_tokens=64,
                temperature=0.0,
            )
        assert info.value.cause is not None
    finally:
        await client.aclose()


async def test_anthropic_client_parses_successful_response() -> None:
    """Happy path: a real-shape Messages response yields an
    :class:`LLMResult` with the expected text and token counts."""
    body = {
        "id": "msg_01",
        "model": "claude-opus-4-8",
        "content": [{"type": "text", "text": "Cited answer [1]."}],
        "usage": {"input_tokens": 17, "output_tokens": 5},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = _anthropic_client(handler)
    try:
        result = await client.complete(
            system="sys",
            user="hi",
            max_tokens=64,
            temperature=0.0,
        )
    finally:
        await client.aclose()
    assert result.provider == "anthropic"
    assert result.text == "Cited answer [1]."
    assert result.input_tokens == 17
    assert result.output_tokens == 5
    assert result.model == "claude-opus-4-8"


async def test_anthropic_client_sends_correct_request_shape() -> None:
    """Verify headers and body the orchestrator relies on."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = _anthropic_client(handler)
    try:
        await client.complete(
            system="be precise",
            user="what?",
            max_tokens=128,
            temperature=0.2,
        )
    finally:
        await client.aclose()

    headers = captured["headers"]
    assert headers["x-api-key"] == "sk-test"
    assert headers["anthropic-version"] == "2023-06-01"
    body = captured["body"]
    assert body["model"] == "claude-opus-4-8"
    assert body["system"] == "be precise"
    assert body["max_tokens"] == 128
    assert body["temperature"] == 0.2
    assert body["messages"] == [{"role": "user", "content": "what?"}]
