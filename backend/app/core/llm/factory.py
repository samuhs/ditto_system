"""LLM factory: resolves real model names and legacy names to a provider."""
from app.core.config.runtime import get_ollama_models
from app.core.llm.base import LLM, build_llm
from app.core.llm.ollama import OllamaLLM


def resolve_llm(name: str, **kwargs) -> LLM:
    """Build an LLM by name.

    - legacy named Ollama-model id (app settings) -> OllamaLLM with its model
    - "gemini-*" (a Gemini model name)            -> GeminiLLM with that model
    - "<model>:<tag>" (an Ollama model name)      -> OllamaLLM with that model
    - "<org>/<repo>" (MLX / Hugging Face name)    -> OllamaLLM (local OpenAI-compatible server)
    - anything else                               -> the provider registry
    """
    for entry in get_ollama_models():
        if entry.get("id") == name:
            return OllamaLLM(model=entry["model"], **kwargs)
    if name.startswith("gemini-"):
        return build_llm("gemini", model=name, **kwargs)
    if ":" in name or "/" in name:
        return OllamaLLM(model=name, **kwargs)
    return build_llm(name, **kwargs)
