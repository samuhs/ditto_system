"""Local LLM server provider: Ollama or any OpenAI-compatible server (MLX, llama.cpp).

Model and URL come from settings (OLLAMA_BASE_URL points at whichever server runs).
"""
from app.core.config.settings import get_settings
from app.core.llm.base import LLM, llm_registry


class OllamaLLM(LLM):
    """Generates answers via the local server's OpenAI-compatible chat endpoint."""

    def __init__(
        self, model=None, base_url=None, api_key="ollama", client=None, temperature=None,
        timeout: float | None = None,
    ) -> None:
        if client is None:
            from langchain_openai import ChatOpenAI

            settings = get_settings()
            # Without a temperature the server's default sampling applies.
            sampling = {} if temperature is None else {"temperature": temperature}
            client = ChatOpenAI(
                model=model or settings.ollama_model,
                base_url=base_url or settings.ollama_base_url,
                api_key=api_key,
                # Travamento/2 (#20): a hard timeout so a stuck server call fails
                # into the usual retry path instead of hanging the worker thread.
                timeout=timeout,
                **sampling,
            )
        self._client = client

    def generate(self, prompt: str) -> str:
        """Return the server's answer for the prompt."""
        return self._client.invoke(prompt).content


llm_registry.register("ollama", OllamaLLM)


def _server_root(base_url: str | None) -> str:
    """The server URL without the OpenAI-compatible /v1 suffix."""
    return (base_url or get_settings().ollama_base_url).rstrip("/").removesuffix("/v1")


def list_ollama_models(base_url: str | None = None, timeout: float = 2.0) -> list[str]:
    """Names of the models on the local LLM server (raises if unreachable).

    Ollama lists them at /api/tags; OpenAI-compatible servers without it
    (MLX, llama.cpp) at /v1/models.
    """
    import httpx

    root = _server_root(base_url)
    resp = httpx.get(f"{root}/api/tags", timeout=timeout)
    if resp.status_code < 400:
        return [m["name"] for m in resp.json().get("models", [])]
    resp = httpx.get(f"{root}/v1/models", timeout=timeout)
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("data", [])]


def local_llm_resident(base_url: str | None = None, timeout: float = 1.0) -> bool:
    """Whether the local LLM server may hold a model in memory right now.

    Ollama lists loaded models at /api/ps. Servers without it (MLX, llama.cpp)
    cannot say, so a reachable one counts as resident; so does a malformed
    reply. An unreachable server holds nothing. Never raises.
    """
    import httpx

    root = _server_root(base_url)
    try:
        resp = httpx.get(f"{root}/api/ps", timeout=timeout)
        if resp.status_code < 400:
            return bool(resp.json().get("models"))
        return httpx.get(f"{root}/v1/models", timeout=timeout).status_code < 400
    except httpx.HTTPError:
        return False
    except (ValueError, AttributeError):
        return True


def unload_local_llm(model: str, base_url: str | None = None, timeout: float = 5.0) -> bool:
    """Ask the local LLM server to free `model` now. True if it confirmed; never raises.

    Ollama unloads on a generate call with keep_alive=0. MLX and llama.cpp have
    no such API (the MLX server keeps one model and swaps it on demand).
    """
    import httpx

    root = _server_root(base_url)
    try:
        resp = httpx.post(
            f"{root}/api/generate", json={"model": model, "keep_alive": 0}, timeout=timeout
        )
        return resp.status_code < 400
    except httpx.HTTPError:
        return False
