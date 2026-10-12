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


class _HighSimilarityEmbedder(_FakeEmbedder):
    """Every pair of sentences is close (cosine distance < 0.1), as with e5 or granite,
    but a topic change is still further apart than sentences on the same topic."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.05] if t.strip().startswith("A") else [1.0, 0.45] for t in texts]


def test_default_split_is_relative_so_close_embedders_still_split():
    """Campaign 2026-10-10: the fixed 0.5 cut left e5 and granite with one chunk
    for the whole guide; the default now cuts at the largest distances."""
    text = "Apples are red. Apples are sweet. Cars are fast. Cars are loud."
    chunks = SemanticChunker(embedder=_HighSimilarityEmbedder()).split(text)
    assert chunks == ["Apples are red. Apples are sweet.", "Cars are fast. Cars are loud."]


def test_a_fixed_threshold_keeps_the_old_behaviour():
    """threshold=0.5 reproduces the campaign's semantic indexes."""
    text = "Apples are red. Apples are sweet. Cars are fast. Cars are loud."
    chunks = SemanticChunker(embedder=_HighSimilarityEmbedder(), threshold=0.5).split(text)
    assert chunks == [text]


def test_two_sentences_on_different_topics_split():
    """One distance has nothing to compare against: the fixed cut decides."""
    chunks = SemanticChunker(embedder=_FakeEmbedder()).split("Apples are red. Cars are fast.")
    assert chunks == ["Apples are red.", "Cars are fast."]


def test_two_sentences_on_the_same_topic_stay_together():
    chunks = SemanticChunker(embedder=_FakeEmbedder()).split("Apples are red. Apples are sweet.")
    assert chunks == ["Apples are red. Apples are sweet."]
