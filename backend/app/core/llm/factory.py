"""LLM factory that resolves named Ollama models before the static registry."""
from app.core.config.runtime import get_ollama_models
from app.core.llm.base import LLM, build_llm
from app.core.llm.ollama import OllamaLLM


def resolve_llm(name: str, **kwargs) -> LLM:
    """Build an LLM by name; a named Ollama-model id resolves to OllamaLLM."""
    for entry in get_ollama_models():
        if entry.get("id") == name:
            return OllamaLLM(model=entry["model"], **kwargs)
    return build_llm(name, **kwargs)
