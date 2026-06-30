"""Tests for the semantic chunker."""
from app.core.chunking.base import build_chunker, chunking_registry
from app.core.chunking.semantic import SemanticChunker


class _FakeEmbedder:
    """Returns one of two orthogonal vectors based on the sentence's first word.

    Sentences starting with 'A' map to topic 1, others to topic 2, so the
    semantic boundary is deterministic and testable.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for t in texts:
            if t.strip().startswith("A"):
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0]

    @property
    def dimension(self) -> int:
        return 2


def test_semantic_chunker_splits_on_topic_change():
    text = "Apples are red. Apples are sweet. Cars are fast. Cars are loud."
    chunker = SemanticChunker(embedder=_FakeEmbedder(), threshold=0.5)
    chunks = chunker.split(text)
    assert len(chunks) == 2
    assert chunks[0] == "Apples are red. Apples are sweet."
    assert "Cars" in chunks[1] and "fast" in chunks[1] and "loud" in chunks[1]


def test_semantic_single_sentence_returns_one_chunk():
    chunker = SemanticChunker(embedder=_FakeEmbedder())
    assert chunker.split("Apples are red.") == ["Apples are red."]


def test_semantic_empty_text_returns_no_chunks():
    chunker = SemanticChunker(embedder=_FakeEmbedder())
    assert chunker.split("   ") == []


def test_semantic_registered_and_built():
    assert "semantic" in chunking_registry.names()
    chunker = build_chunker("semantic", embedder=_FakeEmbedder())
    assert isinstance(chunker, SemanticChunker)
