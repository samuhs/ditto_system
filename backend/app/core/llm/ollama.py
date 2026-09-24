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


def list_ollama_models(base_url: str | None = None, timeout: float = 2.0) -> list[str]:
    """Names of the models pulled on the Ollama server (raises if unreachable)."""
    import httpx

    root = (base_url or get_settings().ollama_base_url).rstrip("/").removesuffix("/v1")
    resp = httpx.get(f"{root}/api/tags", timeout=timeout)
    resp.raise_for_status()
    return [m["name"] for m in resp.json().get("models", [])]
