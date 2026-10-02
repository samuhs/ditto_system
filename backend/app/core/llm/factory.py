"""LLM factory: resolves model names to a provider."""
from app.core.llm.base import LLM, build_llm
from app.core.llm.ollama import OllamaLLM


def resolve_llm(name: str, **kwargs) -> LLM:
    """Build an LLM by name.

    - "gemini-*" (a Gemini model name)            -> GeminiLLM with that model
    - "<model>:<tag>" (an Ollama model name)      -> OllamaLLM with that model
    - "<org>/<repo>" (MLX / Hugging Face name)    -> OllamaLLM (local OpenAI-compatible server)
    - anything else                               -> the provider registry
    """
    if name.startswith("gemini-"):
        return build_llm("gemini", model=name, **kwargs)
    if ":" in name or "/" in name:
        return OllamaLLM(model=name, **kwargs)
    return build_llm(name, **kwargs)


def is_local_llm(name: str) -> bool:
    """Whether the named LLM runs on this machine: anything Gemini does not serve."""
    return not (name == "gemini" or name.startswith("gemini-"))
