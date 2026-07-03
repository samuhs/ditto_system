"""Tests for the experiments endpoints (background runs synchronously under TestClient)."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.experiments import get_experiment_deps
from app.core.db.base import Base
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.orchestrator import ExperimentDeps
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig
from app.main import create_app


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [float(len(text) % 5), 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _FakeLLM:
    def generate(self, prompt: str) -> str:
        return "An answer."


def _embedder_factory(name, **kwargs):
    return _FakeEmbedder()


def _llm_factory(name, **kwargs):
    return _FakeLLM()


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two.\n\nPara three.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )
    app = create_app()
    app.dependency_overrides[get_experiment_deps] = lambda: deps
    return TestClient(app)


def _config_payload():
    return json.dumps(
        {
            "base": "viagem",
            "chunkings": ["recursive"],
            "embeddings": ["gemini"],
            "rags": ["naive"],
            "retrievers": ["similarity"],
            "metrics": ["answer_relevancy"],
        }
    )


def test_create_experiment_runs_and_persists(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    response = client.post("/experiments", data={"config": _config_payload()}, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"pending", "done"}
    assert body["name"]

    detail = client.get(f"/experiments/{body['id']}").json()
    assert detail["status"] == "done"
    assert len(detail["results"]) == 1
    assert detail["results"][0]["answer"] == "An answer."
    assert "answer_relevancy" in detail["results"][0]["scores"]


def test_list_experiments(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nWhere?\n"), "text/csv")}
    client.post("/experiments", data={"config": _config_payload()}, files=files)
    listing = client.get("/experiments").json()
    assert len(listing) >= 1
    assert {"id", "name", "status"} <= set(listing[0])


def test_get_missing_experiment_404(client):
    assert client.get("/experiments/99999").status_code == 404


def test_create_experiment_invalid_config_422(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nWhere?\n"), "text/csv")}
    response = client.post("/experiments", data={"config": "{not valid json"}, files=files)
    assert response.status_code == 422


def test_create_experiment_csv_missing_column_422(client):
    files = {"questions": ("q.csv", io.BytesIO(b"wrong_header\nvalue\n"), "text/csv")}
    response = client.post("/experiments", data={"config": _config_payload()}, files=files)
    assert response.status_code == 422


def test_experiment_records_llm_dimension(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    config = json.dumps({
        "base": "viagem", "chunkings": ["recursive"], "embeddings": ["gemini"],
        "rags": ["naive"], "retrievers": ["similarity"], "metrics": ["answer_relevancy"],
        "llms": ["gemini", "custom"],
    })
    resp = client.post("/experiments", data={"config": config}, files=files)
    assert resp.status_code == 200
    detail = client.get(f"/experiments/{resp.json()['id']}").json()
    llms_in_rows = {row["llm"] for row in detail["results"]}
    assert llms_in_rows == {"gemini", "custom"}


def test_experiment_snapshots_prompts(client):
    config = {
        "base": "viagem",
        "chunkings": ["recursive"],
        "embeddings": ["gemini"],
        "rags": ["naive"],
        "retrievers": ["similarity"],
        "metrics": ["answer_relevancy"],
    }
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nOnde fica o centro?\n"), "text/csv")}
    data = {"config": json.dumps(config)}
    resp = client.post("/experiments", data=data, files=files)
    assert resp.status_code == 200
    exp_id = resp.json()["id"]

    detail = client.get(f"/experiments/{exp_id}").json()
    assert "prompts" in detail
    assert "naive" in detail["prompts"]
    assert "answer" in detail["prompts"]["naive"]
    assert "{context}" in detail["prompts"]["naive"]["answer"]
