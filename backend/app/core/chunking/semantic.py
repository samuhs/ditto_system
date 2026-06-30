"""Semantic chunker: splits where consecutive sentences change topic."""
import re

from app.core.chunking.base import Chunker, chunking_registry
from app.core.embedding.base import Embedder

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Return 1 - cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


class SemanticChunker(Chunker):
    """Groups consecutive sentences while they stay semantically close."""

    def __init__(self, embedder: Embedder, threshold: float = 0.5) -> None:
        self._embedder = embedder
        self._threshold = threshold

    def split(self, text: str) -> list[str]:
        """Split text at sentence boundaries where topic shifts."""
        sentences = [s for s in _SENTENCE_RE.split(text.strip()) if s]
        if len(sentences) <= 1:
            return sentences or [text]
        vectors = self._embedder.embed_documents(sentences)
        chunks: list[str] = []
        current = [sentences[0]]
        for i in range(1, len(sentences)):
            if _cosine_distance(vectors[i - 1], vectors[i]) > self._threshold:
                chunks.append(" ".join(current))
                current = [sentences[i]]
            else:
                current.append(sentences[i])
        chunks.append(" ".join(current))
        return chunks


chunking_registry.register("semantic", SemanticChunker)
