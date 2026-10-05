"""The Grafo de conhecimento through the API: built by a job (ingestion or a Base), queried by experiments.

TestClient runs background tasks before the request returns, so a job started by
a request has finished by the time the test reads it. Fake LLM extrator and
embedder, Qdrant :memory:, SQLite: no network, no Postgres.
"""
import io
import json
import logging

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import (
    get_embedder_factory,
    get_graph_builds,
    get_llm_factory,
    get_session_factory,
    get_store,
)
from app.api.experiments import get_experiment_deps
from app.api.options import get_store as options_get_store
from app.core.db.base import Base
from app.core.graph.jobs import GraphBuildDeps, GraphBuilds
from app.core.memory.manager import ModelManager
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.orchestrator import ExperimentDeps
from app.main import create_app

_EXTRACTOR = "mlx-community/Qwen2.5-3B-Instruct-4bit"
_REPLY = "entidade<|>Praça Central<|>lugar<|>Praça no centro.\n<|FIM|>"


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [[float(len(t) % 5), 1.0, 0.0] for t in texts]

    def embed_query(self, text):
        return [0.0, 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _LLM:
    """Extracts one entity from any chunk, answers anything else; counts extractions."""

    def __init__(self, calls):
        self._calls = calls

    def generate(self, prompt):
        if prompt.startswith("Extraia do texto"):
            self._calls.append(prompt)
            return _REPLY
        return "Resposta gerada."


class _FailingLLM:
    """Raises on every extraction call, like a crashed LLM extrator server."""

    def generate(self, prompt):
        if prompt.startswith("Extraia do texto"):
            raise RuntimeError("internal extractor boom: connection reset")
        return "Resposta gerada."


@pytest.fixture
def calls():
    return []


@pytest.fixture
def builds():
    return GraphBuilds()


@pytest.fixture
def client(calls, builds):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    store = QdrantStore(client=QdrantClient(":memory:"))

    def embedder_factory(name, **kw):
        return _FakeEmbedder()

    def llm_factory(name, **kw):
        return _LLM(calls)

    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[options_get_store] = lambda: store
    app.dependency_overrides[get_embedder_factory] = lambda: embedder_factory
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_llm_factory] = lambda: llm_factory
    app.dependency_overrides[get_graph_builds] = lambda: builds
    deps = ExperimentDeps(store=store, session_factory=session_factory, llm_factory=llm_factory,
                          embedder_factory=embedder_factory)
    app.dependency_overrides[get_experiment_deps] = lambda: deps
    return TestClient(app)


def _ingest(client, base="viagem", embeddings="gemini", **extra):
    files = [("files", ("a.txt", io.BytesIO(b"Para one.\n\nPara two."), "text/plain"))]
    data = {"base": base, "chunkings": "recursive", "embeddings": embeddings, **extra}
    response = client.post("/ingest", data=data, files=files)
    assert response.status_code == 200, response.text
    return response.json()


def _indexes(client, base="viagem"):
    return client.get("/options").json()["base_indexes"][base]


def test_ingesting_without_a_grafo_behaves_as_before(client, calls, builds):
    body = _ingest(client)
    assert body == {"collections": ["viagem__recursive__gemini"], "total_chunks": 1,
                    "graph_build": None}
    assert calls == [] and builds.list_jobs() == []
    assert _indexes(client) == [
        {"chunking": "recursive", "embedding": "gemini", "graph_extractors": []}
    ]


def test_ingesting_with_a_grafo_builds_it_in_the_background(client, calls):
    body = _ingest(client, embeddings="gemini,e5", graph_extractor=_EXTRACTOR)
    job = body["graph_build"]
    assert (job["base"], job["extractor"], job["status"]) == ("viagem", _EXTRACTOR, "pending")
    assert [(i["chunking"], i["embedding"]) for i in job["indexes"]] == [
        ("recursive", "gemini"), ("recursive", "e5"),
    ]

    done = client.get(f"/graph-builds/{job['id']}").json()
    assert done["status"] == "done"
    assert [(i["status"], i["extracted"], i["total"]) for i in done["indexes"]] == [
        ("done", 1, 1), ("done", 1, 1),
    ]
    assert len(calls) == 1  # one chunking: extracted once, for both embeddings
    assert all(i["graph_extractors"] == [_EXTRACTOR] for i in _indexes(client))


def test_a_grafo_is_built_for_an_existing_base_without_reingesting(client, calls):
    _ingest(client, embeddings="gemini,e5")
    response = client.post("/graph-builds", json={
        "base": "viagem", "extractor": _EXTRACTOR,
        "indexes": [{"chunking": "recursive", "embedding": "e5"}],
    })
    assert response.status_code == 202
    job = client.get(f"/graph-builds/{response.json()['id']}").json()
    assert job["status"] == "done" and len(calls) == 1
    by_index = {i["embedding"]: i["graph_extractors"] for i in _indexes(client)}
    assert by_index == {"gemini": [], "e5": [_EXTRACTOR]}

    # Without indexes, every Índice of the Base; the current Grafo is not rebuilt.
    again = client.post("/graph-builds", json={"base": "viagem", "extractor": _EXTRACTOR})
    assert again.status_code == 202
    assert len(client.get(f"/graph-builds/{again.json()['id']}").json()["indexes"]) == 2
    assert len(calls) == 1  # same chunks: the extraction cache answers
    assert [j["id"] for j in client.get("/graph-builds?base=viagem").json()] == [
        again.json()["id"], response.json()["id"],
    ]


def test_a_grafo_build_needs_existing_indexes(client):
    _ingest(client)
    unknown_base = client.post("/graph-builds", json={"base": "faq", "extractor": _EXTRACTOR})
    assert unknown_base.status_code == 422 and "faq" in unknown_base.json()["detail"]
    missing = client.post("/graph-builds", json={
        "base": "viagem", "extractor": _EXTRACTOR,
        "indexes": [{"chunking": "fixed", "embedding": "e5"}],
    })
    assert missing.status_code == 422
    assert "fixed × e5" in missing.json()["detail"]


def test_an_unknown_job_is_404_and_only_an_active_job_pauses(client):
    _ingest(client)
    assert client.get("/graph-builds/99").status_code == 404
    job_id = client.post("/graph-builds", json={"base": "viagem", "extractor": _EXTRACTOR}).json()["id"]
    assert client.post(f"/graph-builds/{job_id}/pause").status_code == 409  # already done
    assert client.post(f"/graph-builds/{job_id}/resume").status_code == 409


def _job_deps(client):
    overrides = client.app.dependency_overrides
    return GraphBuildDeps(
        store=overrides[get_store](), session_factory=overrides[get_session_factory](),
        models=ModelManager(overrides[get_embedder_factory](), max_local=1),
        llm_factory=overrides[get_llm_factory](),
    )


def test_a_paused_build_resumes_through_the_api(client, calls, builds):
    _ingest(client)
    job = builds.create("viagem", _EXTRACTOR, [("recursive", "gemini")])
    paused = client.post(f"/graph-builds/{job.id}/pause")
    assert paused.status_code == 200 and paused.json()["pause_requested"] is True
    builds.run(job.id, _job_deps(client))  # the queue reaches it: it stops before any chunk
    assert client.get(f"/graph-builds/{job.id}").json()["status"] == "paused" and calls == []

    resumed = client.post(f"/graph-builds/{job.id}/resume")
    assert resumed.status_code == 202
    assert client.get(f"/graph-builds/{job.id}").json()["status"] == "done"
    assert len(calls) == 1


def test_a_failed_index_gets_a_friendly_message_and_logs_the_detail(client, builds, caplog):
    _ingest(client)
    job = builds.create("viagem", _EXTRACTOR, [("recursive", "gemini")])
    deps = _job_deps(client)
    failing_deps = GraphBuildDeps(
        store=deps.store, session_factory=deps.session_factory, models=deps.models,
        llm_factory=lambda name, **kw: _FailingLLM(),
    )
    with caplog.at_level(logging.ERROR, logger="app.core.graph.jobs"):
        builds.run(job.id, failing_deps)

    done = client.get(f"/graph-builds/{job.id}").json()
    assert done["status"] == "failed"
    [index] = done["indexes"]
    assert index["status"] == "failed"
    # The client gets a friendly PT-BR message, never the raw exception text.
    assert index["error"]
    assert "internal extractor boom" not in index["error"]
    assert "the LLM extrator failed on every chunk" not in index["error"]
    # The raw detail is still available to operators, in the log.
    logged = "\n".join(r.message for r in caplog.records)
    assert "internal extractor boom" in logged or "failed on every chunk" in logged


def test_a_base_with_a_grafo_build_in_progress_cannot_be_deleted(client, builds):
    _ingest(client)
    job = builds.create("viagem", _EXTRACTOR, [("recursive", "gemini")])

    [base] = client.get("/bases").json()
    assert "Grafo" in base["in_use"] and _EXTRACTOR in base["in_use"]
    assert [(b["id"], b["status"]) for b in base["graph_builds"]] == [(job.id, "pending")]
    assert base["graph_builds"][0]["indexes"][0]["total"] == 0
    response = client.delete("/bases/viagem")
    assert response.status_code == 409 and "Grafo" in response.json()["detail"]


def _experiment(client, rags, **config):
    payload = {"base": "viagem", "chunkings": ["recursive"], "embeddings": ["gemini"],
               "rags": rags, "retrievers": ["similarity"], "metrics": ["rouge_l"],
               "llms": ["gemini"], **config}
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nOnde?,Aqui.\n"),
                           "text/csv")}
    return client.post("/experiments", data={"config": json.dumps(payload)}, files=files)


def test_an_experiment_with_graph_needs_a_current_grafo(client):
    _ingest(client)
    response = _experiment(client, ["naive", "graph"])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "graph" in detail and "recursive × gemini" in detail and "Gere o Grafo" in detail
    assert _experiment(client, ["naive"]).status_code == 200


def test_an_experiment_queries_the_only_grafo_without_building_one(client, calls):
    _ingest(client, graph_extractor=_EXTRACTOR)
    extractions = len(calls)
    response = _experiment(client, ["graph"])
    assert response.status_code == 200, response.text
    detail = client.get(f"/experiments/{response.json()['id']}").json()
    assert detail["status"] == "done" and detail["graph_extractor"] == _EXTRACTOR
    assert "graph" not in detail["progress"]
    [row] = detail["results"]
    assert row["answer"] == "Resposta gerada." and row["graph_stats"]["extractor"] == _EXTRACTOR
    assert len(calls) == extractions  # the experiment never extracted


def test_with_grafos_from_two_extractors_the_experiment_names_one(client):
    _ingest(client, graph_extractor=_EXTRACTOR)
    client.post("/graph-builds", json={"base": "viagem", "extractor": "qwen3:1.7b"})

    ambiguous = _experiment(client, ["graph_mix"])
    assert ambiguous.status_code == 422
    assert "qwen3:1.7b" in ambiguous.json()["detail"] and _EXTRACTOR in ambiguous.json()["detail"]

    chosen = _experiment(client, ["graph_mix"], graph_extractor="qwen3:1.7b")
    assert chosen.status_code == 200
    detail = client.get(f"/experiments/{chosen.json()['id']}").json()
    assert detail["graph_extractor"] == "qwen3:1.7b"

    unknown = _experiment(client, ["graph"], graph_extractor="nenhum:llm")
    assert unknown.status_code == 422 and "nenhum:llm" in unknown.json()["detail"]


def test_grafos_without_a_common_extractor_are_named_as_such(client):
    _ingest(client, embeddings="gemini,e5")
    client.post("/graph-builds", json={"base": "viagem", "extractor": _EXTRACTOR,
                                       "indexes": [{"chunking": "recursive", "embedding": "gemini"}]})
    client.post("/graph-builds", json={"base": "viagem", "extractor": "qwen3:1.7b",
                                       "indexes": [{"chunking": "recursive", "embedding": "e5"}]})
    response = _experiment(client, ["graph"], embeddings=["gemini", "e5"])
    assert response.status_code == 422
    assert "LLMs extratores diferentes" in response.json()["detail"]
