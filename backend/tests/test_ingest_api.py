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
    assert "gemini-2.5-flash-lite" in body["llms"]
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
