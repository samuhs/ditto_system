"""Tests for QdrantStore retrieval extensions (id, vectors, scroll)."""
import pytest
from qdrant_client import QdrantClient

from app.core.vectorstore.qdrant import QdrantStore


@pytest.fixture
def store():
    s = QdrantStore(client=QdrantClient(":memory:"))
    s.ensure_collection("c", dimension=3)
    s.add(
        "c",
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        payloads=[
            {"source_doc": "a.txt", "chunk_index": 0, "text": "x"},
            {"source_doc": "a.txt", "chunk_index": 1, "text": "y"},
            {"source_doc": "b.txt", "chunk_index": 0, "text": "z"},
        ],
    )
    return s


def test_search_includes_id(store):
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1)
    assert "id" in hits[0]
    assert hits[0]["payload"]["text"] == "x"


def test_search_with_vectors_returns_vector(store):
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1, with_vectors=True)
    assert hits[0]["vector"] == [1.0, 0.0, 0.0]


def test_search_without_vectors_omits_vector_key(store):
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1)
    assert "vector" not in hits[0]


def test_scroll_by_payload_filter(store):
    points = store.scroll("c", where={"source_doc": "a.txt"})
    texts = sorted(p["payload"]["text"] for p in points)
    assert texts == ["x", "y"]
