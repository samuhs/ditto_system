"""Tests for similarity and MMR retrievers."""
import pytest
from qdrant_client import QdrantClient

from app.core.retrieval.base import Retriever, build_retriever, retrieval_registry
from app.core.retrieval.mmr import MMRRetriever
from app.core.retrieval.similarity import SimilarityRetriever
from app.core.vectorstore.qdrant import QdrantStore


class _FakeEmbedder:
    """Maps a query to a fixed 3-dim vector based on its first character."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        table = {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0], "c": [0.0, 0.0, 1.0]}
        return table.get(text[:1].lower(), [1.0, 0.0, 0.0])

    @property
    def dimension(self) -> int:
        return 3


@pytest.fixture
def store():
    s = QdrantStore(client=QdrantClient(":memory:"))
    s.ensure_collection("col", dimension=3)
    s.add(
        "col",
        vectors=[[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.0, 1.0, 0.0]],
        payloads=[
            {"source_doc": "a.txt", "chunk_index": 0, "text": "alpha one"},
            {"source_doc": "a.txt", "chunk_index": 1, "text": "alpha two"},
            {"source_doc": "b.txt", "chunk_index": 0, "text": "beta"},
        ],
    )
    return s


def test_similarity_returns_nearest_first(store):
    retriever = SimilarityRetriever(store, "col", _FakeEmbedder(), top_k=2)
    results = retriever.retrieve("alpha question")
    assert len(results) == 2
    assert results[0]["text"] == "alpha one"
    assert "score" in results[0]


def test_mmr_diversifies_results(store):
    retriever = MMRRetriever(store, "col", _FakeEmbedder(), top_k=2, fetch_k=3, lambda_mult=0.5)
    results = retriever.retrieve("alpha question")
    texts = [r["text"] for r in results]
    assert len(results) == 2
    assert "alpha one" in texts


def test_retrievers_registered_and_built(store):
    assert {"similarity", "mmr"} <= set(retrieval_registry.names())
    retriever = build_retriever("similarity", store=store, collection="col", embedder=_FakeEmbedder())
    assert isinstance(retriever, Retriever)
