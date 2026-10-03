"""Tests for the Qdrant vector store wrapper (in-memory)."""
import pytest
from qdrant_client import QdrantClient

from app.core.vectorstore.qdrant import QdrantStore, collection_name, parse_collection_name


@pytest.fixture
def store():
    return QdrantStore(client=QdrantClient(":memory:"))


def test_collection_name_convention():
    assert collection_name("viagem", "recursive", "e5") == "viagem__recursive__e5"


def test_parse_collection_name_inverts_the_convention():
    assert parse_collection_name("viagem__recursive__e5") == ("viagem", "recursive", "e5")
    assert parse_collection_name("guia__da__cidade__token__gemini") == ("guia__da__cidade", "token", "gemini")
    assert parse_collection_name("solta") is None


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


def test_add_appends_without_id_collision(store):
    name = "viagem__recursive__gemini"
    store.ensure_collection(name, dimension=3)
    store.add(name, vectors=[[1.0, 0.0, 0.0]], payloads=[{"text": "first"}])
    store.add(name, vectors=[[0.0, 1.0, 0.0]], payloads=[{"text": "second"}])
    hits = store.search(name, query_vector=[1.0, 0.0, 0.0], top_k=5)
    assert {h["payload"]["text"] for h in hits} == {"first", "second"}


def test_graph_collections_keep_llm_extrators_apart_and_never_read_as_an_index():
    from app.core.vectorstore.qdrant import graph_collection_names

    names = {
        llm: graph_collection_names("guia", "markdown", "e5", llm)
        for llm in ["qwen3:1.7b", "qwen3-1.7b", "org/model", "org:model"]
    }
    assert len({n for pair in names.values() for n in pair}) == 8
    assert names["qwen3-1.7b"][0] == "guia__markdown__e5__kg_ent__qwen3-1.7b"
    assert all("/" not in n and ":" not in n for pair in names.values() for n in pair)
    assert all(parse_collection_name(n) is None for pair in names.values() for n in pair)


def test_add_rejects_mismatched_lengths(store):
    store.ensure_collection("c", dimension=3)
    with pytest.raises(ValueError):
        store.add("c", vectors=[[1.0, 0.0, 0.0]], payloads=[])
