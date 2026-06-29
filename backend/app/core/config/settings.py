"""Application configuration read from environment."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application environment variables."""

    database_url: str = "postgresql://ditto:ditto@localhost:5432/ditto"
    qdrant_url: str = "http://localhost:6333"
    gemini_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings."""
    return Settings()
