"""Retriever interface, registry, and factory."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


class Retriever(ABC):
    """Minimal interface every retriever implements."""

    @abstractmethod
    def retrieve(self, query: str) -> list[dict]:
        """Return relevant contexts (payload dicts plus a 'score')."""


retrieval_registry: Registry[type[Retriever]] = Registry("retrieval")


def build_retriever(name: str, **kwargs) -> Retriever:
    """Instantiate a registered retriever by name."""
    return retrieval_registry.get(name)(**kwargs)
