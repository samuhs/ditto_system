"""Tests for the /options and /ingest endpoints."""
import io

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.api.ingest import get_embedder_factory, get_store
from app.core.vectorstore.qdrant import QdrantStore
from app.main import create_app


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [[float(len(t) % 5), 1.0, 0.0] for t in texts]

    def embed_query(self, text):
        return [0.0, 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


@pytest.fixture
def client():
    app = create_app()
    store = QdrantStore(client=QdrantClient(":memory:"))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_embedder_factory] = lambda: (lambda name, **kw: _FakeEmbedder())
    return TestClient(app)


def test_options_lists_registered_techniques(client):
    response = client.get("/options")
    assert response.status_code == 200
    body = response.json()
    assert {"fixed", "recursive", "token", "semantic"} <= set(body["chunkings"])
    assert {"gemini", "e5", "paraphrase"} <= set(body["embeddings"])
    assert "gemini-2.5-flash-lite" in [o["value"] for o in body["llm_options"]]
    assert {"naive", "agentic"} <= set(body["rags"])
    assert {"similarity", "mmr", "multi_query", "parent_document"} <= set(body["retrievers"])
    assert {"answer_relevancy", "faithfulness", "rouge_l"} <= set(body["metrics"])


def test_options_bases_empty_when_store_unreachable():
    """A vector-store outage must not break /options; bases degrade to []."""
    from app.api.options import get_store as options_get_store

    class _BrokenStore:
        def list_collections(self):
            raise RuntimeError("qdrant down")

    app = create_app()
    app.dependency_overrides[options_get_store] = lambda: _BrokenStore()
    resp = TestClient(app).get("/options")
    assert resp.status_code == 200
    assert resp.json()["bases"] == []


def test_ingest_uploads_and_stores(client):
    files = [("files", ("a.txt", io.BytesIO(b"Para one.\n\nPara two here.\n\nPara three."), "text/plain"))]
    data = {"base": "viagem", "chunkings": "recursive", "embeddings": "gemini"}
    response = client.post("/ingest", data=data, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["collections"] == ["viagem__recursive__gemini"]
    assert body["total_chunks"] > 0


def test_ingest_rejects_non_utf8_file(client):
    files = [("files", ("bad.txt", io.BytesIO(b"\xff\xfe\x00invalid"), "text/plain"))]
    data = {"base": "viagem", "chunkings": "recursive", "embeddings": "gemini"}
    response = client.post("/ingest", data=data, files=files)
    assert response.status_code == 422
    assert "UTF-8" in response.json()["detail"]


def test_ingest_rejects_unknown_technique(client):
    files = [("files", ("a.txt", io.BytesIO(b"Some text here."), "text/plain"))]
    data = {"base": "viagem", "chunkings": "nope", "embeddings": "gemini"}
    response = client.post("/ingest", data=data, files=files)
    assert response.status_code == 422
    assert "chunking" in response.json()["detail"]


def test_options_lists_indexes_per_base():
    from app.api.options import get_store as options_get_store

    class _Store:
        def list_collections(self):
            return ["viagem__fixed__e5", "viagem__recursive__gemini", "faq__token__e5", "stray"]

    app = create_app()
    app.dependency_overrides[options_get_store] = lambda: _Store()
    body = TestClient(app).get("/options").json()
    assert body["bases"] == ["faq", "viagem"]
    assert body["base_indexes"] == {
        "faq": [{"chunking": "token", "embedding": "e5"}],
        "viagem": [
            {"chunking": "fixed", "embedding": "e5"},
            {"chunking": "recursive", "embedding": "gemini"},
        ],
    }


def _ingest(client, base: str) -> None:
    files = [("files", ("a.txt", io.BytesIO(b"Para one.\n\nPara two."), "text/plain"))]
    data = {"base": base, "chunkings": "recursive", "embeddings": "gemini"}
    assert client.post("/ingest", data=data, files=files).status_code == 200


def test_deleting_a_base_removes_its_indexes_and_their_grafos_only():
    from app.core.vectorstore.qdrant import graph_collection_names

    app = create_app()
    store = QdrantStore(client=QdrantClient(":memory:"))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_embedder_factory] = lambda: (lambda name, **kw: _FakeEmbedder())
    client = TestClient(app)
    # Names that share "viagem" as a prefix belong to other Bases.
    for base in ("viagem", "viagem2", "viagem__x"):
        _ingest(client, base)
        for name in graph_collection_names(base, "recursive", "gemini", "qwen3:1.7b"):
            store.ensure_collection(name, 3)

    response = client.delete("/bases/viagem")

    assert response.status_code == 200
    assert sorted(response.json()["deleted"]) == sorted([
        "viagem__recursive__gemini",
        *graph_collection_names("viagem", "recursive", "gemini", "qwen3:1.7b"),
    ])
    remaining = set(store.list_collections())
    assert not any(name.startswith("viagem__recursive") for name in remaining)
    for base in ("viagem2", "viagem__x"):
        assert f"{base}__recursive__gemini" in remaining
        assert set(graph_collection_names(base, "recursive", "gemini", "qwen3:1.7b")) <= remaining


def test_deleting_an_unknown_base_is_404(client):
    _ingest(client, "viagem2")
    assert client.delete("/bases/viagem").status_code == 404
