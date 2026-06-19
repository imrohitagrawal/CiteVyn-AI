"""Settings added for Slice 3 and Slice 4.

The defaults documented in ``docs/RELEASE_PLAN.md`` and
``docs/API_SPEC.md`` are pinned here so future changes are intentional.
"""

from __future__ import annotations

from app.core.config import (
    DEFAULT_NO_ANSWER_FALLBACK,
    DEFAULT_UNSUPPORTED_REFUSAL,
    Settings,
    get_settings,
)


def test_default_llm_provider_is_stub() -> None:
    settings = Settings()
    assert settings.llm_provider == "stub"
    assert settings.llm_model == "claude-opus-4-8"
    assert settings.llm_max_tokens == 1024
    assert 0.0 <= settings.llm_temperature <= 1.0


def test_default_embedding_dim_matches_migration() -> None:
    settings = Settings()
    assert settings.embedding_provider == "stub"
    assert settings.embedding_model == "voyage-3"
    assert settings.embedding_dim == 1024


def test_default_retrieval_and_cache_settings() -> None:
    settings = Settings()
    assert settings.retrieval_top_k == 6
    assert settings.retrieval_max_candidates == 20
    assert settings.answer_policy_version == "v1"
    assert settings.cache_ttl_seconds == 86_400
    assert settings.cache_enabled is True


def test_default_response_copy_matches_spec() -> None:
    settings = Settings()
    assert settings.unsupported_refusal == DEFAULT_UNSUPPORTED_REFUSAL
    assert settings.no_answer_fallback == DEFAULT_NO_ANSWER_FALLBACK
    assert "Claude" in settings.unsupported_refusal
    assert "Codex" in settings.unsupported_refusal


def test_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CITEVYN_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("CITEVYN_RETRIEVAL_TOP_K", "10")
    monkeypatch.setenv("CITEVYN_CACHE_ENABLED", "false")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.llm_provider == "anthropic"
        assert settings.retrieval_top_k == 10
        assert settings.cache_enabled is False
    finally:
        get_settings.cache_clear()
