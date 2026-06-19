from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Defaults exposed as module constants so tests can pin them.
# ---------------------------------------------------------------------------

DEFAULT_NO_ANSWER_FALLBACK: str = (
    "I do not have credible source material in this assistant to answer that. "
    "Try rephrasing or asking about a related topic covered by the indexed docs."
)

DEFAULT_UNSUPPORTED_REFUSAL: str = (
    "I can answer questions about Claude, Claude Code, Codex, and Gemini using "
    "indexed official documentation. I do not have credible source material in "
    "this assistant to answer that."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CITEVYN_",
        env_file=".env",
        extra="ignore",
    )

    # --- Application / transport ---
    app_name: str = "CiteVyn AI Backend"
    environment: str = "local"
    demo_api_key: str = Field(default="local-demo-key", min_length=1)
    request_id_header: str = "X-Request-ID"

    # --- Persistence (Slice 2+) ---
    database_url: str = Field(
        default="postgresql+psycopg://citevyn:citevyn@localhost:5432/citevyn",
        min_length=1,
    )
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1)
    index_session_ttl_seconds: int = Field(default=60 * 60 * 24, ge=1)
    pg_test_url: str | None = None

    # --- LLM (Slice 4+) ---
    llm_provider: str = "stub"  # "stub" or "anthropic"
    llm_model: str = "claude-opus-4-8"
    llm_max_tokens: int = Field(default=1024, ge=1)
    llm_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    anthropic_api_key: str | None = None
    anthropic_api_base: str = "https://api.anthropic.com"
    anthropic_api_version: str = "2023-06-01"
    anthropic_timeout_seconds: float = Field(default=30.0, gt=0.0)

    # --- Retrieval (Slice 4+) ---
    embedding_provider: str = "stub"
    embedding_model: str = "voyage-3"
    embedding_dim: int = Field(default=1024, ge=1)
    retrieval_top_k: int = Field(default=6, ge=1)
    retrieval_max_candidates: int = Field(default=20, ge=1)

    # --- Answer cache (Slice 5+) ---
    answer_policy_version: str = "v1"
    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=86_400, ge=1)

    # --- Response copy (Slice 4+) ---
    unsupported_refusal: str = DEFAULT_UNSUPPORTED_REFUSAL
    no_answer_fallback: str = DEFAULT_NO_ANSWER_FALLBACK


@lru_cache
def get_settings() -> Settings:
    return Settings()
