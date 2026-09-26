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

    def encode(self, text, **kwargs):
        if isinstance(text, list):
            return [[float(len(t)), 0.0, 0.0, 1.0] for t in text]
        return [float(len(text)), 0.0, 0.0, 1.0]

    def get_sentence_embedding_dimension(self) -> int:
        return 4


def test_e5_embeds_with_injected_model():
    emb = E5Embedder(model=_FakeSentenceTransformer())
    # The fake's first coordinate is the text length, e5 prefix included.
    assert emb.embed_documents(["abc"]) == [[float(len("passage: abc")), 0.0, 0.0, 1.0]]
    assert emb.embed_query("ab") == [float(len("query: ab")), 0.0, 0.0, 1.0]
    assert emb.dimension == 4


def test_local_embedders_registered():
    assert {"e5", "paraphrase"} <= set(embedding_registry.names())


def test_paraphrase_built_with_injected_model():
    emb = ParaphraseEmbedder(model=_FakeSentenceTransformer())
    assert emb.dimension == 4


def test_local_embedders_declare_locality():
    from app.core.embedding import E5Embedder, GeminiEmbedder, ParaphraseEmbedder

    assert E5Embedder.is_local and ParaphraseEmbedder.is_local
    assert not GeminiEmbedder.is_local


def test_huggingface_embedder_passes_the_device(monkeypatch):
    import sys
    import types

    seen = {}

    class _ST:
        def __init__(self, name, device=None):
            seen["args"] = (name, device)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=_ST))
    from app.core.embedding import E5Embedder

    E5Embedder(device="cpu")
    assert seen["args"] == ("intfloat/multilingual-e5-small", "cpu")
    E5Embedder(device="auto")
    assert seen["args"] == ("intfloat/multilingual-e5-small", None)


def test_embed_queries_defaults_to_embed_query():
    from app.core.embedding.base import Embedder

    class _E(Embedder):
        def embed_documents(self, texts):
            raise AssertionError("queries must not be embedded as documents")

        def embed_query(self, text):
            return [float(len(text))]

        @property
        def dimension(self):
            return 1

    assert _E().embed_queries(["a", "bb"]) == [[1.0], [2.0]]


def test_huggingface_batches_and_returns_plain_floats():
    import numpy as np

    from app.core.embedding.huggingface import HuggingFaceEmbedder

    calls = []

    class _Model:
        def encode(self, texts, **kwargs):
            calls.append((texts, kwargs.get("batch_size")))
            if isinstance(texts, str):
                return np.array([0.5, 1.0], dtype=np.float32)
            return np.ones((len(texts), 2), dtype=np.float32)

    emb = HuggingFaceEmbedder("x", model=_Model())
    out = emb.embed_queries(["a", "b", "c"])
    assert out == [[1.0, 1.0]] * 3 and type(out[0][0]) is float
    assert calls[-1] == (["a", "b", "c"], 32)
    assert emb.embed_query("q") == [0.5, 1.0]


class _RecordingSentenceTransformer(_FakeSentenceTransformer):
    """Records the exact texts the model was asked to encode."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def encode(self, text, **kwargs):
        self.seen.extend(text if isinstance(text, list) else [text])
        return super().encode(text, **kwargs)


def test_e5_prefixes_passages_and_queries():
    # The e5 model card: every input starts with "query: " or "passage: ".
    model = _RecordingSentenceTransformer()
    emb = E5Embedder(model=model)
    emb.embed_documents(["centro da cidade"])
    emb.embed_query("onde fica o centro?")
    emb.embed_queries(["onde comer?"])
    assert model.seen == [
        "passage: centro da cidade",
        "query: onde fica o centro?",
        "query: onde comer?",
    ]


def test_paraphrase_embeds_text_unprefixed():
    model = _RecordingSentenceTransformer()
    emb = ParaphraseEmbedder(model=model)
    emb.embed_documents(["a"])
    emb.embed_query("b")
    emb.embed_queries(["c"])
    assert model.seen == ["a", "b", "c"]
