from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

# Sensible default origins for local development. Production deploys
# MUST override ``CITEVYN_CORS_ALLOWED_ORIGINS`` to the approved
# frontend host. The default is intentionally a single localhost
# origin (per ``docs/SECURITY_MODEL.md §11``) — no wildcards.
DEFAULT_CORS_ALLOWED_ORIGINS: tuple[str, ...] = ("http://localhost:3000",)


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

    # --- Admin auth (Slice 8) ---
    admin_api_key: str = Field(default="local-admin-key", min_length=1)
    admin_api_key_header: str = "X-Admin-API-Key"

    # --- CORS (Slice 8) ---
    # ``NoDecode`` tells pydantic-settings NOT to JSON-decode the env
    # string — the field validator below splits the comma-separated
    # value into a list. Without ``NoDecode`` the env loader would
    # try to parse the whole string as a single JSON list and fail.
    cors_allowed_origins: Annotated[list[str], NoDecode] = list(DEFAULT_CORS_ALLOWED_ORIGINS)

    # --- Rate limiting (Slice 8) ---
    # Per-process sliding-window limits from ``docs/SECURITY_MODEL.md §6``:
    # demo_user 30 q/h, admin 100 q/h. The limiter is per-process only;
    # a Redis-backed implementation is a Slice 10+ concern.
    rate_limit_enabled: bool = True
    rate_limit_demo_user_per_hour: int = Field(default=30, ge=1)
    rate_limit_admin_per_hour: int = Field(default=100, ge=1)
    rate_limit_window_seconds: int = Field(default=3600, ge=1)

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

    # --- Worker (Slice 8) ---
    # Out-of-process ingestion worker (see ``app/worker/cli.py``). The
    # CLI entry point polls ``ingestion_jobs`` every
    # ``worker_poll_seconds`` and processes one job at a time.
    worker_poll_seconds: float = Field(default=2.0, gt=0.0)
    worker_max_runtime_seconds: int = Field(default=0, ge=0)  # 0 = unbounded
    worker_fetch_timeout_seconds: float = Field(default=20.0, gt=0.0)
    worker_max_chunks_per_doc: int = Field(default=500, ge=1)

    # --- Index promotion gate (Slice 8) ---
    # Per ``docs/RELEASE_PLAN.md §7`` the promotion gate rejects a
    # candidate index whose latest ``EvaluationRun.metrics.pass_rate``
    # is below this threshold. Default 0.95 matches the
    # "golden pass rate >= 95%" gate.
    index_promotion_min_pass_rate: float = Field(default=0.95, ge=0.0, le=1.0)

    # --- Worker source snapshot (Slice 8 step 6) ---
    # The ``source_version_hash`` is stamped on every
    # :class:`IngestionJob` and :class:`IndexVersion` row this
    # worker produces. The MVP default is a placeholder —
    # production replaces it with the SHA-256 of the source
    # feed the operator ingested.
    source_version_hash: str = "sha256:mvp-snapshot-1"

    # --- Response copy (Slice 4+) ---
    unsupported_refusal: str = DEFAULT_UNSUPPORTED_REFUSAL
    no_answer_fallback: str = DEFAULT_NO_ANSWER_FALLBACK

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept either a list (typed) or a comma-separated env string.

        Pydantic-settings reads ``CITEVYN_CORS_ALLOWED_ORIGINS`` as a
        single string even when the field type is ``list[str]``; this
        validator splits on ``,`` so the env-var path Just Works.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
