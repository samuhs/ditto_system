"""Semantic chunker: splits where consecutive sentences change topic."""
import re

from app.core.chunking.base import Chunker, chunking_registry
from app.core.embedding.base import Embedder
from app.core.vector_math import cosine_distance

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class SemanticChunker(Chunker):
    """Groups consecutive sentences while they stay semantically close."""

    def __init__(self, embedder: Embedder, threshold: float = 0.5) -> None:
        self._embedder = embedder
        self._threshold = threshold

    def split(self, text: str) -> list[str]:
        """Split text at sentence boundaries where topic shifts."""
        stripped = text.strip()
        if not stripped:
            return []
        sentences = [s for s in _SENTENCE_RE.split(stripped) if s]
        if len(sentences) <= 1:
            return sentences or [stripped]
        vectors = self._embedder.embed_documents(sentences)
        chunks: list[str] = []
        current = [sentences[0]]
        for i in range(1, len(sentences)):
            if cosine_distance(vectors[i - 1], vectors[i]) > self._threshold:
                chunks.append(" ".join(current))
                current = [sentences[i]]
            else:
                current.append(sentences[i])
        chunks.append(" ".join(current))
        return chunks


chunking_registry.register("semantic", SemanticChunker)
