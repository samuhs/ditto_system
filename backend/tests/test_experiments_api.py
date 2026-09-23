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


def test_list_experiments_paginated(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    client.post("/experiments", data={"config": _config_payload()}, files=files)
    body = client.get("/experiments").json()
    assert set(body.keys()) == {"items", "total", "page", "page_size"}
    assert body["total"] >= 1
    assert body["page"] == 1 and body["page_size"] == 20
    item = body["items"][0]
    assert {"id", "name", "status", "created_at"} <= set(item.keys())
    assert item["created_at"]  # ISO string present
    assert item["created_at"].endswith("+00:00")


def test_get_experiment_includes_timestamps(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["created_at"]  # present
    assert detail["created_at"].endswith("+00:00")
    assert detail["finished_at"]  # experiment ran to completion → finished_at set
    assert detail["finished_at"].endswith("+00:00")


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


def test_get_experiment_reports_pause_requested(client):
    from app.experiments.orchestrator import _pause_requests, request_pause

    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    request_pause(exp_id)
    try:
        assert client.get(f"/experiments/{exp_id}").json()["pause_requested"] is True
    finally:
        _pause_requests.discard(exp_id)


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


def _seed_experiment(client, name="Exp Árvore/1"):
    """Insert an experiment with two results, one of them missing a metric."""
    from app.core.db.models import Experiment, ExperimentRun, RunResult

    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    try:
        experiment = Experiment(name=name, status="done", config={})
        run = ExperimentRun(
            chunking="recursive", embedding="gemini", rag_technique="naive",
            retriever="similarity", llm="gemini", status="done",
        )
        run.results = [
            RunResult(
                question="Onde fica?", reference_answer="Ali", generated_answer="Lá, perto",
                scores={"faithfulness": 0.5, "answer_relevancy": 1.0}, latency_ms=120, tokens=42,
            ),
            RunResult(
                question="Quando?", reference_answer=None, generated_answer="Amanhã",
                scores={"answer_relevancy": 0.25}, latency_ms=80, tokens=10,
            ),
        ]
        experiment.runs = [run]
        session.add(experiment)
        session.commit()
        return experiment.id
    finally:
        session.close()


def test_export_experiment_csv(client):
    import csv

    exp_id = _seed_experiment(client)
    response = client.get(f"/experiments/{exp_id}/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="Exp_Arvore_1.csv"' in disposition

    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # BOM so Excel detects UTF-8
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0] == [
        "chunking", "embedding", "rag", "retriever", "llm",
        "pergunta", "resposta_referencia", "resposta",
        "answer_relevancy", "faithfulness", "media", "latency_ms", "tokens",
    ]
    assert len(rows) == 3
    assert rows[1] == [
        "recursive", "gemini", "naive", "similarity", "gemini",
        "Onde fica?", "Ali", "Lá, perto", "1.0", "0.5", "0.75", "120", "42",
    ]
    # missing metric → empty cell; media averages only present scores
    assert rows[2][6] == ""
    assert rows[2][8:] == ["0.25", "", "0.25", "80", "10"]


def test_export_missing_experiment_404(client):
    assert client.get("/experiments/99999/export.csv").status_code == 404
