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
