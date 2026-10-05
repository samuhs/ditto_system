"""LLM provider interface, registry, and factory."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


class LLM(ABC):
    """Minimal interface every LLM provider implements."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return the model's answer for a single prompt."""


llm_registry: Registry[type[LLM]] = Registry("llm")


def build_llm(name: str, **kwargs) -> LLM:
    """Instantiate a registered LLM provider by name."""
    return llm_registry.get(name)(**kwargs)


def sampling_kwargs(**params) -> dict:
    """The given sampling params minus the unset (None) ones; 0 is kept."""
    return {k: v for k, v in params.items() if v is not None}
