"""Application configuration read from environment."""
import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application environment variables."""

    database_url: str = "postgresql://ditto:ditto@localhost:5432/ditto"
    qdrant_url: str = "http://localhost:6333"
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:3b-instruct"
    # Memory profile (low | standard) and explicit overrides; empty means unset.
    memory_profile: str = "standard"
    max_local_models: int | None = None
    embedding_device: str | None = None
    max_experiment_concurrency: int | None = None
    # The perplexity signal loads a second copy of an MLX model beside the server.
    # Without free memory for it, it is skipped unless swapping is allowed.
    perplexity_allow_swap: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator(
        "max_local_models", "embedding_device", "max_experiment_concurrency", mode="before"
    )
    @classmethod
    def _empty_is_unset(cls, value):
        """Compose passes unset .env keys through as empty strings."""
        return None if value == "" else value

    @field_validator("perplexity_allow_swap", mode="before")
    @classmethod
    def _empty_is_false(cls, value):
        """An unset .env key arrives as an empty string: keep the default."""
        return False if value == "" else value


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings.

    Respects ENV_FILE env var: set to empty string to disable .env reading
    (useful in tests to prevent the project .env from leaking into assertions).
    """
    env_file = os.environ.get("ENV_FILE", ".env") or None
    return Settings(_env_file=env_file)
