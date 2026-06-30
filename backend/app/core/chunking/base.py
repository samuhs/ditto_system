"""Chunking strategy interface, registry, and factory."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


class Chunker(ABC):
    """Minimal interface every chunking strategy implements."""

    @abstractmethod
    def split(self, text: str) -> list[str]:
        """Split a document's text into chunks."""


chunking_registry: Registry[type[Chunker]] = Registry("chunking")


def build_chunker(name: str, **kwargs) -> Chunker:
    """Instantiate a registered chunking strategy by name."""
    return chunking_registry.get(name)(**kwargs)
