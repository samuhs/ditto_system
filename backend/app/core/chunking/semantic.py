"""Semantic chunker: splits where consecutive sentences change topic."""
import re

from app.core.chunking.base import Chunker, chunking_registry
from app.core.embedding.base import Embedder
from app.core.vector_math import cosine_distance

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class SemanticChunker(Chunker):
    """Groups consecutive sentences while they stay semantically close.

    By default it cuts where the distance between consecutive sentences is in the
    top (100 - percentile)% of that text's distances, so it adapts to each
    embedder's similarity scale. A fixed `threshold` cut misses embedders whose
    distances all fall below it: with 0.5, e5 and granite put the whole guide in
    one chunk (campaign 2026-10-10). Pass threshold=0.5 to reproduce those indexes.
    The default 90 gives ~300-token chunks on the town guide, in line with the
    fixed and recursive chunkers and within e5-small's 512-token input.
    """

    def __init__(
        self, embedder: Embedder, threshold: float | None = None, percentile: float = 90.0,
    ) -> None:
        self._embedder = embedder
        self._threshold = threshold
        self._percentile = percentile

    def split(self, text: str) -> list[str]:
        """Split text at sentence boundaries where topic shifts."""
        stripped = text.strip()
        if not stripped:
            return []
        sentences = [s for s in _SENTENCE_RE.split(stripped) if s]
        if len(sentences) <= 1:
            return sentences or [stripped]
        vectors = self._embedder.embed_documents(sentences)
        distances = [cosine_distance(vectors[i - 1], vectors[i]) for i in range(1, len(sentences))]
        cut = self._threshold if self._threshold is not None else _percentile(distances, self._percentile)
        chunks: list[str] = []
        current = [sentences[0]]
        for sentence, distance in zip(sentences[1:], distances):
            if distance > cut:
                chunks.append(" ".join(current))
                current = [sentence]
            else:
                current.append(sentence)
        chunks.append(" ".join(current))
        return chunks


def _percentile(values: list[float], q: float) -> float:
    """The q-th percentile (0-100) of values, linearly interpolated."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


chunking_registry.register("semantic", SemanticChunker)
