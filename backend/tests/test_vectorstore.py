"""Tests for the Qdrant vector store wrapper (in-memory)."""
import pytest
from qdrant_client import QdrantClient

from app.core.vectorstore.qdrant import QdrantStore, collection_name


@pytest.fixture
def store():
    return QdrantStore(client=QdrantClient(":memory:"))


def test_collection_name_convention():
    assert collection_name("viagem", "recursive", "e5") == "viagem__recursive__e5"


def test_add_and_search_returns_nearest(store):
    name = "viagem__recursive__e5"
    store.ensure_collection(name, dimension=3)
    store.add(
        name,
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        payloads=[{"source_doc": "a.txt", "text": "alpha"},
                  {"source_doc": "b.txt", "text": "beta"}],
    )
    hits = store.search(name, query_vector=[0.9, 0.1, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0]["payload"]["text"] == "alpha"
    assert hits[0]["score"] > 0


def test_search_with_payload_filter(store):
    name = "viagem__fixed__gemini"
    store.ensure_collection(name, dimension=3)
    store.add(
        name,
        vectors=[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        payloads=[{"source_doc": "a.txt"}, {"source_doc": "b.txt"}],
    )
    hits = store.search(name, query_vector=[1.0, 0.0, 0.0], top_k=5,
                        where={"source_doc": "b.txt"})
    assert [h["payload"]["source_doc"] for h in hits] == ["b.txt"]


def test_ensure_collection_is_idempotent(store):
    store.ensure_collection("c", dimension=3)
    store.ensure_collection("c", dimension=3)
    hits = store.search("c", query_vector=[1.0, 0.0, 0.0], top_k=1)
    assert hits == []
