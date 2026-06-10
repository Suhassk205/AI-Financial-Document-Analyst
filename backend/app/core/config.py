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
    gemini_embedding_model: str = ""
    # Deferred to Phase 2 — None until the embedding model is selected & tested.
    embedding_dim: int | None = None
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
