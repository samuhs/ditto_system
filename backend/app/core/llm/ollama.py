"""Local LLM server provider: Ollama or any OpenAI-compatible server (MLX, llama.cpp).

Model and URL come from settings (OLLAMA_BASE_URL points at whichever server runs).
"""
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
    """Names of the models on the local LLM server (raises if unreachable).

    Ollama lists them at /api/tags; OpenAI-compatible servers without it
    (MLX, llama.cpp) at /v1/models.
    """
    import httpx

    root = (base_url or get_settings().ollama_base_url).rstrip("/").removesuffix("/v1")
    resp = httpx.get(f"{root}/api/tags", timeout=timeout)
    if resp.status_code < 400:
        return [m["name"] for m in resp.json().get("models", [])]
    resp = httpx.get(f"{root}/v1/models", timeout=timeout)
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("data", [])]
