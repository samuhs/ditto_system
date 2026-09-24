"""Where local embedders run. The GPU belongs to the LLM; embedders get it only when it is free."""
from collections.abc import Callable, Iterable

from app.core.llm import ollama
from app.core.llm.factory import is_local_llm
from app.core.memory.profile import AUTO, CPU, MemoryProfile


def resolve_embedding_device(
    profile: MemoryProfile,
    llm_names: Iterable[str] = (),
    llm_resident: Callable[[], bool] | None = None,
) -> str:
    """CPU unless the profile allows the GPU and no local LLM can be on it."""
    if profile.embedding_device == CPU:
        return CPU
    if any(is_local_llm(name) for name in llm_names):
        return CPU
    probe = llm_resident or ollama.local_llm_resident
    return CPU if probe() else AUTO
