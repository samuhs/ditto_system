"""Tests for the embedding provider interface and implementations."""
from app.core.embedding.base import Embedder, build_embedder, embedding_registry
from app.core.embedding.gemini import GeminiEmbedder
from app.core.embedding.huggingface import E5Embedder, ParaphraseEmbedder


class _FakeEmbeddings:
    """Stands in for a LangChain embeddings client (3-dim vectors)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 2.0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 2.0]


def test_gemini_embed_documents_uses_injected_client():
    emb = GeminiEmbedder(client=_FakeEmbeddings())
    vectors = emb.embed_documents(["ab", "cde"])
    assert vectors == [[2.0, 1.0, 2.0], [3.0, 1.0, 2.0]]


def test_gemini_embed_query_and_dimension():
    emb = GeminiEmbedder(client=_FakeEmbeddings())
    assert emb.embed_query("xy") == [2.0, 1.0, 2.0]
    assert emb.dimension == 3


def test_gemini_dimension_is_cached():
    class _CountingFake(_FakeEmbeddings):
        def __init__(self) -> None:
            self.calls = 0

        def embed_query(self, text: str) -> list[float]:
            self.calls += 1
            return super().embed_query(text)

    client = _CountingFake()
    emb = GeminiEmbedder(client=client)
    assert emb.dimension == 3
    assert emb.dimension == 3
    assert client.calls == 1


def test_gemini_registered_and_built():
    assert "gemini" in embedding_registry.names()
    emb = build_embedder("gemini", client=_FakeEmbeddings())
    assert isinstance(emb, Embedder)


class _FakeSentenceTransformer:
    """Stands in for a SentenceTransformer model (4-dim)."""

    def encode(self, text):
        if isinstance(text, list):
            return [[float(len(t)), 0.0, 0.0, 1.0] for t in text]
        return [float(len(text)), 0.0, 0.0, 1.0]

    def get_sentence_embedding_dimension(self) -> int:
        return 4


def test_e5_embeds_with_injected_model():
    emb = E5Embedder(model=_FakeSentenceTransformer())
    assert emb.embed_documents(["abc"]) == [[3.0, 0.0, 0.0, 1.0]]
    assert emb.embed_query("ab") == [2.0, 0.0, 0.0, 1.0]
    assert emb.dimension == 4


def test_local_embedders_registered():
    assert {"e5", "paraphrase"} <= set(embedding_registry.names())


def test_paraphrase_built_with_injected_model():
    emb = ParaphraseEmbedder(model=_FakeSentenceTransformer())
    assert emb.dimension == 4
