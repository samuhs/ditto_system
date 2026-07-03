"""Ollama LLM provider (OpenAI-compatible endpoint, model/url from settings)."""
from app.core.config.settings import get_settings
from app.core.llm.base import llm_registry
from app.core.llm.custom import CustomLLM


class OllamaLLM(CustomLLM):
    """Generates answers via a local Ollama server's OpenAI-compatible endpoint."""

    def __init__(self, model=None, base_url=None, api_key="ollama", client=None) -> None:
        settings = get_settings()
        super().__init__(
            model=model or settings.ollama_model,
            base_url=base_url or settings.ollama_base_url,
            api_key=api_key,
            client=client,
        )


llm_registry.register("ollama", OllamaLLM)
