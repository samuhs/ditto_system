"""Application configuration read from environment."""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application environment variables."""

    database_url: str = "postgresql://ditto:ditto@localhost:5432/ditto"
    qdrant_url: str = "http://localhost:6333"
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b-instruct"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings.

    Respects ENV_FILE env var: set to empty string to disable .env reading
    (useful in tests to prevent the project .env from leaking into assertions).
    """
    env_file = os.environ.get("ENV_FILE", ".env") or None
    return Settings(_env_file=env_file)
