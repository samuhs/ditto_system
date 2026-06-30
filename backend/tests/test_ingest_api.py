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
    assert {"gemini", "custom"} <= set(body["llms"])


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
