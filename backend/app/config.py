"""Runtime configuration. Everything is env-driven; secrets never live in the repo."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Local default uses the docker-compose Postgres. Tests override via env.
    database_url: str = "postgresql+psycopg2://resolvedesk:resolvedesk@localhost:5432/resolvedesk"

    # LLM provider: "stub" (deterministic, default, key-free) or "openai".
    llm_provider: str = "stub"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Risk gate: drafts at or above this confidence with no money movement auto-resolve.
    auto_resolve_threshold: float = 0.80

    # Worker poll cadence (seconds) and outbox retry cap.
    worker_poll_seconds: float = 0.5
    outbox_max_attempts: int = 5

    # Dev-token auth for the console API (deliberately minimal - see DESIGN.md).
    api_token: str = "dev-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
