"""Tests for the Slice 9a LLM client singleton + lifecycle."""

from __future__ import annotations

import pytest

from app.llm import factory as llm_factory
from app.llm.anthropic import AnthropicLLMClient
from app.llm.stub import StubLLMClient


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Drop the process-wide singleton before AND after each test."""
    llm_factory.reset_llm_client()
    yield
    llm_factory.reset_llm_client()


def test_get_llm_client_returns_singleton_when_settings_match() -> None:
    """A second call returns the same object — no second ``build_llm_client`` invocation."""
    from app.core.config import Settings

    settings = Settings(llm_provider="stub")
    first = llm_factory.get_llm_client(settings)
    second = llm_factory.get_llm_client(settings)
    assert first is second


def test_get_llm_client_returns_stub_by_default() -> None:
    """The default provider is ``stub`` and returns a :class:`StubLLMClient`."""
    from app.core.config import Settings

    settings = Settings(llm_provider="stub")
    client = llm_factory.get_llm_client(settings)
    assert isinstance(client, StubLLMClient)


def test_get_llm_client_builds_anthropic_when_configured() -> None:
    """Anthropic provider returns the real :class:`AnthropicLLMClient`."""
    from app.core.config import Settings

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        anthropic_api_base="https://api.anthropic.com",
        anthropic_api_version="2023-06-01",
        anthropic_timeout_seconds=5.0,
        llm_model="claude-sonnet-4-6",
    )
    client = llm_factory.get_llm_client(settings)
    assert isinstance(client, AnthropicLLMClient)


def test_anthropic_factory_raises_on_missing_api_key() -> None:
    """The Anthropic path raises eagerly on missing API key."""
    from app.core.config import Settings

    settings = Settings(llm_provider="anthropic", anthropic_api_key=None)
    with pytest.raises(RuntimeError, match="CITEVYN_ANTHROPIC_API_KEY is required"):
        llm_factory.build_llm_client(settings)


def test_shutdown_llm_client_closes_underlying_httpx() -> None:
    """``shutdown_llm_client`` calls ``aclose`` on the real Anthropic client."""
    from app.core.config import Settings

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        anthropic_api_base="https://api.anthropic.com",
        anthropic_api_version="2023-06-01",
        anthropic_timeout_seconds=5.0,
    )
    client = llm_factory.get_llm_client(settings)
    # Spy on aclose without monkey-patching the class globally
    closed = {"count": 0}

    async def fake_aclose() -> None:
        closed["count"] += 1

    client.aclose = fake_aclose  # type: ignore[method-assign]
    import asyncio

    asyncio.run(llm_factory.shutdown_llm_client())
    assert closed["count"] == 1


def test_shutdown_llm_client_is_noop_without_singleton() -> None:
    """Calling shutdown twice or without prior build is safe."""
    import asyncio

    asyncio.run(llm_factory.shutdown_llm_client())
    asyncio.run(llm_factory.shutdown_llm_client())


def test_validate_llm_provider_rejects_unknown_value() -> None:
    """An undeclared provider raises with a clear message."""
    from app.core.config import Settings

    settings = Settings(llm_provider="nope")
    with pytest.raises(RuntimeError, match="not supported"):
        llm_factory.validate_llm_provider(settings)


def test_validate_llm_provider_rejects_stub_in_production() -> None:
    """Production deploys cannot ship with the stub provider.

    The check is enforced at two altitudes (this slice moved the
    check into a :func:`Settings.model_validator` so it fires for any
    code path that constructs ``Settings``, and the runtime
    :func:`validate_llm_provider` is a defensive double-check wired
    into the FastAPI lifespan). We use ``model_construct`` to build
    a Settings instance that bypasses the model_validator so this
    test exercises the runtime guard explicitly.
    """
    from app.core.config import Settings

    settings = Settings.model_construct(
        environment="production",
        llm_provider="stub",
    )
    with pytest.raises(llm_factory.LLMProviderNotConfigured):
        llm_factory.validate_llm_provider(settings)


def test_settings_constructor_rejects_stub_in_production() -> None:
    """The Settings model_validator rejects stub-in-prod at parse time.

    Companion to the runtime check above — the model_validator is
    the canonical guard and fires for any caller (uvicorn, alembic,
    the worker, a one-off script). The runtime guard is wired into
    the FastAPI lifespan as a defensive double-check.
    """
    from app.core.config import Settings

    with pytest.raises(Exception, match="not allowed when.*production"):
        Settings(environment="production", llm_provider="stub")


def test_validate_llm_provider_accepts_stub_in_development() -> None:
    """Stub is fine in local / test environments."""
    from app.core.config import Settings

    for env in ("local", "development", "test", "ci"):
        settings = Settings(environment=env, llm_provider="stub")
        llm_factory.validate_llm_provider(settings)  # does not raise


def test_validate_llm_provider_accepts_real_provider_in_production() -> None:
    """Real providers pass the production guard.

    Uses ``model_construct`` to bypass the model_validator that
    also checks for the API key — we want this test to focus on
    the runtime provider check.
    """
    from app.core.config import Settings

    settings = Settings.model_construct(
        environment="production",
        llm_provider="anthropic",
        anthropic_api_key="sk-ant-test",
    )
    llm_factory.validate_llm_provider(settings)


def test_settings_constructor_rejects_missing_anthropic_key_in_production() -> None:
    """The model_validator requires the API key when provider is anthropic."""
    from app.core.config import Settings

    with pytest.raises(Exception, match="CITEVYN_ANTHROPIC_API_KEY"):
        Settings(environment="production", llm_provider="anthropic")


def test_settings_constructor_rejects_default_admin_key_in_production() -> None:
    """The model_validator rejects the public default admin key in prod.

    Pass an explicit non-stub LLM provider + API key so the
    LLM-in-production guard does not short-circuit this test (the
    LLM guard runs first because validators fire in declaration
    order).
    """
    from app.core.config import Settings

    with pytest.raises(Exception, match="CITEVYN_ADMIN_API_KEY"):
        Settings(
            environment="production",
            llm_provider="anthropic",
            anthropic_api_key="sk-ant-test",
            admin_api_key="local-admin-key",
        )


def test_settings_constructor_rejects_default_admin_key_in_production_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model_validator reads ``CITEVYN_ADMIN_API_KEY`` from the environment.

    The operator can trigger the rejection by leaving
    ``CITEVYN_ADMIN_API_KEY`` unset in production (so the
    ``local-admin-key`` default fires). This test pins the
    environment-driven path.
    """
    from app.core.config import Settings

    monkeypatch.setenv("CITEVYN_ENVIRONMENT", "production")
    monkeypatch.setenv("CITEVYN_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CITEVYN_ANTHROPIC_API_KEY", "sk-ant-test")
    # ``admin_api_key`` is unset → falls back to default 'local-admin-key'.
    monkeypatch.delenv("CITEVYN_ADMIN_API_KEY", raising=False)
    with pytest.raises(Exception, match="CITEVYN_ADMIN_API_KEY"):
        Settings()
