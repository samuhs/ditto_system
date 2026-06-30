"""Retriever interface, registry, factory, and similarity helpers."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity between two vectors (0 if either is zero)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class Retriever(ABC):
    """Minimal interface every retriever implements."""

    @abstractmethod
    def retrieve(self, query: str) -> list[dict]:
        """Return relevant contexts (payload dicts plus a 'score')."""


retrieval_registry: Registry[type[Retriever]] = Registry("retrieval")


def build_retriever(name: str, **kwargs) -> Retriever:
    """Instantiate a registered retriever by name."""
    return retrieval_registry.get(name)(**kwargs)
