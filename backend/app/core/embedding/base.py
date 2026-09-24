"""Embedding provider interface, registry, and factory."""
from abc import ABC, abstractmethod

from app.core.registry import Registry


class Embedder(ABC):
    """Minimal interface every embedding provider implements."""

    # True when the model's weights live in this process (counted by the ModelManager).
    is_local: bool = False

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed several queries (as queries, not documents). Providers may batch it."""
        return [self.embed_query(text) for text in texts]

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Length of the vectors this embedder produces."""


embedding_registry: Registry[type[Embedder]] = Registry("embedding")


def build_embedder(name: str, **kwargs) -> Embedder:
    """Instantiate a registered embedding provider by name."""
    return embedding_registry.get(name)(**kwargs)
