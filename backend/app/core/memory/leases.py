"""Helpers that decide when an embedder must actually be in memory."""
import threading
from collections.abc import Callable
from contextlib import ExitStack

from app.core.embedding.base import Embedder
from app.core.memory.manager import ModelManager


class CachedQueryEmbedder(Embedder):
    """Answers known queries from precomputed vectors; loads the real model only on a miss.

    Staged experiments embed every question before any LLM runs. Text the LLM
    writes later (a HyDE passage, multi-query variations, CRAG/agentic
    rewrites) is a miss, and only then does the model come into memory.
    """

    def __init__(
        self,
        vectors: dict[str, list[float]],
        fallback: Callable[[], Embedder],
        dimension: int,
    ) -> None:
        self._vectors = vectors
        self._fallback_factory = fallback
        self._fallback: Embedder | None = None
        self._dimension = dimension
        self._lock = threading.Lock()  # questions run in parallel threads

    @property
    def loaded_fallback(self) -> bool:
        """Whether a miss forced the real model into memory."""
        return self._fallback is not None

    def _model(self) -> Embedder:
        with self._lock:
            if self._fallback is None:
                self._fallback = self._fallback_factory()
            return self._fallback

    def embed_query(self, text: str) -> list[float]:
        """The cached vector, or the real model's for text never seen before."""
        vector = self._vectors.get(text)
        return vector if vector is not None else self._model().embed_query(text)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Cached vectors where known, the real model for the rest."""
        return [self.embed_query(text) for text in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Documents are never cached: always the real model."""
        return self._model().embed_documents(texts)

    @property
    def dimension(self) -> int:
        """Vector length of the cached (and real) vectors."""
        return self._dimension


class LeaseSwitcher:
    """Holds one embedder lease and swaps it only when the requested model changes."""

    def __init__(self, models: ModelManager) -> None:
        self._models = models
        self._key: tuple[str, str] | None = None
        self._stack: ExitStack | None = None
        self._embedder: Embedder | None = None
        self._lock = threading.RLock()

    def get(self, name: str, device: str) -> Embedder:
        """The embedder for (name, device), keeping the current lease if it matches."""
        with self._lock:
            if self._key != (name, device):
                self.close()
                stack = ExitStack()
                self._embedder = stack.enter_context(self._models.acquire(name, device))
                self._stack, self._key = stack, (name, device)
            return self._embedder

    def close(self) -> None:
        """Release the current lease, if any."""
        with self._lock:
            if self._stack is not None:
                self._stack.close()
            self._stack, self._key, self._embedder = None, None, None

    def __enter__(self) -> "LeaseSwitcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
