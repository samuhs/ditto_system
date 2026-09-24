"""Tests for multi-query and parent-document retrievers."""
import pytest
from qdrant_client import QdrantClient

from app.core.retrieval.base import build_retriever, retrieval_registry
from app.core.retrieval.multi_query import MultiQueryRetriever
from app.core.retrieval.parent_document import ParentDocumentRetriever
from app.core.vectorstore.qdrant import QdrantStore


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        if "beta" in text.lower():
            return [0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _ScriptedLLM:
    """Returns a fixed multi-line set of query variations."""

    def generate(self, prompt: str) -> str:
        return "alpha variant one\nbeta variant two"


@pytest.fixture
def store():
    s = QdrantStore(client=QdrantClient(":memory:"))
    s.ensure_collection("col", dimension=3)
    s.add(
        "col",
        vectors=[[1.0, 0.0, 0.0], [0.95, 0.05, 0.0], [0.0, 1.0, 0.0]],
        payloads=[
            {"source_doc": "a.txt", "chunk_index": 0, "text": "alpha zero"},
            {"source_doc": "a.txt", "chunk_index": 1, "text": "alpha one"},
            {"source_doc": "b.txt", "chunk_index": 0, "text": "beta zero"},
        ],
    )
    return s


def test_multi_query_unions_results(store):
    retriever = MultiQueryRetriever(
        store, "col", _FakeEmbedder(), _ScriptedLLM(), top_k=1, n_queries=2
    )
    results = retriever.retrieve("alpha question")
    texts = {r["text"] for r in results}
    assert "alpha zero" in texts
    assert "beta zero" in texts  # the 'beta' variant pulled a different chunk


def test_parent_document_expands_with_neighbors(store):
    retriever = ParentDocumentRetriever(store, "col", _FakeEmbedder(), top_k=1, window=1)
    results = retriever.retrieve("alpha question")
    assert len(results) == 1
    assert "alpha zero" in results[0]["text"]
    assert "alpha one" in results[0]["text"]  # neighbor included


def test_advanced_retrievers_registered(store):
    assert {"multi_query", "parent_document"} <= set(retrieval_registry.names())
    retriever = build_retriever(
        "parent_document", store=store, collection="col", embedder=_FakeEmbedder()
    )
    assert isinstance(retriever, ParentDocumentRetriever)
    multi = build_retriever(
        "multi_query",
        store=store,
        collection="col",
        embedder=_FakeEmbedder(),
        llm=_ScriptedLLM(),
    )
    assert isinstance(multi, MultiQueryRetriever)


def test_parent_document_fetches_only_the_neighbour_window():
    store = QdrantStore(client=QdrantClient(":memory:"))
    store.ensure_collection("long", 3)
    store.add(
        "long",
        vectors=[[1.0, 0.0, 0.0] if i == 15 else [0.0, 1.0, float(i)] for i in range(30)],
        payloads=[{"source_doc": "d.txt", "chunk_index": i, "text": f"c{i}"} for i in range(30)],
    )
    fetched = []
    real_scroll = store.scroll

    def spy(*args, **kwargs):
        points = real_scroll(*args, **kwargs)
        fetched.append(len(points))
        return points

    store.scroll = spy

    class _Query:
        def embed_query(self, text):
            return [1.0, 0.0, 0.0]

    [hit] = ParentDocumentRetriever(store, "long", _Query(), top_k=1, window=1).retrieve("q")
    assert hit["text"] == "c14 c15 c16"
    assert fetched and max(fetched) <= 3
