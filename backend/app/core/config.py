"""Centralized, environment-based application configuration.

All configuration flows through a single typed `Settings` object loaded from
environment variables (and a local `.env` file). Nothing in the app should read
`os.environ` directly — import `settings` from here instead.

Environments: local | development | production (see `Environment`).
The embedding dimension is intentionally optional/unset — it is finalized in
Phase 2 (see docs/02_DATABASE_DESIGN.md §6.1).
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LogFormat(str, Enum):
    JSON = "json"
    CONSOLE = "console"


class Settings(BaseSettings):
    """Strongly-typed application settings. Values come from env / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Runtime ----
    app_env: Environment = Environment.LOCAL
    app_name: str = "ai-financial-document-analyst"
    debug: bool = False
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE

    # ---- API ----
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"

    # ---- Database ----
    database_url: str = Field(
        default="postgresql+asyncpg://analyst:analyst@localhost:5432/financial_analyst"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://analyst:analyst@localhost:5432/financial_analyst"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ---- Redis / Celery ----
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ---- LLM / Embeddings ----
    gemini_api_key: str = ""
    gemini_llm_model: str = "gemini-2.5-pro"
    # Phase 2A: finalized. `gemini-embedding-001` (GA) returns 3072-dim vectors
    # natively; we request a Matryoshka-truncated 768-dim output (then re-normalize)
    # so the column stays within pgvector's 2000-dim HNSW/IVFFlat index limit for
    # Phase 2B. See ADR-013 in docs/06_IMPLEMENTATION_ROADMAP.md.
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # ---- Embedding generation (Phase 2A) ----
    # Gemini embedding task type for stored document chunks (RETRIEVAL_DOCUMENT).
    # The query-side task type (RETRIEVAL_QUERY) belongs to Phase 2B (search).
    embedding_task_type: str = "RETRIEVAL_DOCUMENT"
    # Re-normalize truncated (<3072) vectors to unit length — required because
    # Gemini only L2-normalizes the full-width 3072 output.
    embedding_normalize: bool = True
    # Chunks per Gemini batchEmbedContents call (one HTTP request per batch).
    embedding_batch_size: int = 100
    # Retry policy for transient provider errors (rate limits / 5xx).
    embedding_max_retries: int = 5
    embedding_retry_base_delay: float = 2.0   # seconds; exponential backoff base
    embedding_retry_max_delay: float = 60.0   # seconds; backoff ceiling
    embedding_request_timeout: float = 60.0   # seconds per API call
    # Cost estimation only (no billing) — USD per 1M input tokens for the model.
    embedding_price_per_1m_tokens: float = 0.15

    openrouter_api_key: str = ""
    openrouter_fallback_model: str = "openai/gpt-4o"

    # ---- Security (auth implemented in Phase 11) ----
    jwt_secret: str = "changeme"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ---- Uploads (Phase 1A) ----
    max_upload_size_mb: int = 50
    allowed_upload_extensions: str = ".pdf"
    allowed_upload_content_types: str = "application/pdf,application/x-pdf"

    # ---- Section detection (Phase 1B) ----
    # Path to the configurable section taxonomy. Empty → use the packaged default
    # (app/ingestion/section_detection/taxonomy.json).
    section_taxonomy_path: str = ""

    # ---- Chunking (Phase 1C) ----
    # Token-based, section-aware recursive chunking. See docs/05_RETRIEVAL_DESIGN.md §2.
    chunk_target_tokens: int = 700      # preferred chunk size
    chunk_max_tokens: int = 800         # hard upper bound
    chunk_min_tokens: int = 50          # below this → flagged as "too small"
    chunk_overlap_tokens: int = 75      # carried context between adjacent chunks
    # Tokenizer backend: "heuristic" (regex word/punct) | "char" (chars/4 estimate).
    # Pluggable so a real tokenizer (e.g. tiktoken) can be swapped in later.
    tokenizer: str = "heuristic"

    # ---- Object storage ----
    storage_backend: str = "local"
    storage_local_path: str = "./data/uploads"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # ---- Derived helpers ----
    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def allowed_upload_extensions_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_upload_extensions.split(",") if e.strip()}

    @property
    def allowed_upload_content_types_set(self) -> set[str]:
        return {c.strip().lower() for c in self.allowed_upload_content_types.split(",") if c.strip()}


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (import this, or the module-level `settings`)."""
    return Settings()


# Convenience singleton for direct import: `from app.core.config import settings`
settings = get_settings()
