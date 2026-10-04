"""Tests for the /bases endpoints: the Bases catalog and deleting a Base."""
import io

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.bases import get_session_factory
from app.api.ingest import get_embedder_factory, get_store
from app.core.db.base import Base
from app.core.db.models import Experiment
from app.core.graph.knowledge import GraphEntity, GraphRelation, write_graph
from app.core.vectorstore.qdrant import QdrantStore, graph_collection_names
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
def store():
    return QdrantStore(client=QdrantClient(":memory:"))


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def client(store, session_factory):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_embedder_factory] = lambda: (lambda name, **kw: _FakeEmbedder())
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    return TestClient(app)


def _ingest(client, base: str, chunkings: str = "recursive", embeddings: str = "gemini") -> None:
    files = [("files", ("a.txt", io.BytesIO(b"Para one.\n\nPara two."), "text/plain"))]
    data = {"base": base, "chunkings": chunkings, "embeddings": embeddings}
    assert client.post("/ingest", data=data, files=files).status_code == 200


def _write_graph(store, base, chunking, embedding, extractor, stats, built_at=None) -> None:
    entities = [
        GraphEntity(key=k, name=k, type="lugar", description=k, chunk_ids=[0])
        for k in ("parque", "igreja", "praça")
    ]
    relations = [
        GraphRelation(
            source="parque", target="igreja", source_key="parque", target_key="igreja",
            keywords="perto", description="perto", chunk_ids=[0],
        )
    ]
    meta = {"extractor": extractor, "stats": stats}
    if built_at is not None:
        meta["built_at"] = built_at
    write_graph(
        store, graph_collection_names(base, chunking, embedding, extractor),
        entities, relations, _FakeEmbedder(), meta,
    )


def test_bases_lists_each_base_with_its_indexes_and_their_grafos(client, store):
    _ingest(client, "viagem", chunkings="recursive,fixed")
    _ingest(client, "faq")
    _write_graph(
        store, "viagem", "recursive", "gemini", "qwen3:1.7b",
        {"entities": 3, "relations": 1, "lines": 40, "failed_lines": 10},
        built_at="2026-10-01T12:00:00+00:00",
    )

    response = client.get("/bases")

    assert response.status_code == 200
    bases = response.json()
    assert [b["name"] for b in bases] == ["faq", "viagem"]
    viagem = bases[1]
    assert viagem["in_use"] is None
    assert [(i["chunking"], i["embedding"]) for i in viagem["indexes"]] == [
        ("fixed", "gemini"), ("recursive", "gemini"),
    ]
    fixed, recursive = viagem["indexes"]
    assert fixed["chunks"] > 0 and fixed["graphs"] == []
    assert recursive["graphs"] == [{
        "extractor": "qwen3:1.7b",
        "entities": 3,
        "relations": 1,
        "failed_pct": 25.0,
        "built_at": "2026-10-01T12:00:00+00:00",
    }]


def test_bases_is_empty_without_any_index(client):
    assert client.get("/bases").json() == []


class _ExtractorLLM:
    def generate(self, prompt):
        return "entidade<|>Praça Central<|>lugar<|>Praça no centro.\n<|FIM|>"


def test_a_grafo_built_now_shows_its_build_date(client, store):
    from contextlib import nullcontext
    from datetime import datetime

    from app.core.graph.build import build_graph

    _ingest(client, "viagem")
    build_graph(
        store, "viagem", "recursive", "gemini", "qwen3:1.7b", _ExtractorLLM(),
        lambda: nullcontext(_FakeEmbedder()),
    )

    (graph,) = client.get("/bases").json()[0]["indexes"][0]["graphs"]

    assert graph["entities"] == 1
    assert datetime.fromisoformat(graph["built_at"]).tzinfo is not None


def test_a_grafo_without_date_shows_none_and_an_unfinished_one_is_left_out(client, store):
    _ingest(client, "viagem")
    _write_graph(
        store, "viagem", "recursive", "gemini", "gemini-2.5-flash-lite",
        {"entities": 3, "relations": 1, "lines": 0, "failed_lines": 0},
    )
    # A build that stopped before its metadata point: no Grafo yet.
    for name in graph_collection_names("viagem", "recursive", "gemini", "qwen3:1.7b"):
        store.ensure_collection(name, 3)

    (index,) = client.get("/bases").json()[0]["indexes"]

    assert [(g["extractor"], g["failed_pct"], g["built_at"]) for g in index["graphs"]] == [
        ("gemini-2.5-flash-lite", 0.0, None),
    ]


def test_deleting_a_base_removes_its_indexes_and_their_grafos_only(client, store):
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


def _experiment(session_factory, name: str, status: str, base: str = "viagem") -> int:
    session = session_factory()
    experiment = Experiment(name=name, status=status, config={"base": base})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    return experiment_id


@pytest.mark.parametrize("status", ["running", "pending"])
def test_a_base_an_active_experiment_uses_cannot_be_deleted(client, store, session_factory, status):
    _ingest(client, "viagem")
    _experiment(session_factory, "exp-viagem", status)

    response = client.delete("/bases/viagem")

    assert response.status_code == 409
    assert "exp-viagem" in response.json()["detail"]
    assert "viagem__recursive__gemini" in store.list_collections()
    assert client.get("/bases").json()[0]["in_use"] == response.json()["detail"]


def test_a_finished_experiment_or_one_on_another_base_does_not_block(client, session_factory):
    _ingest(client, "viagem")
    _experiment(session_factory, "exp-done", "done")
    _experiment(session_factory, "exp-faq", "running", base="faq")

    assert client.get("/bases").json()[0]["in_use"] is None
    assert client.delete("/bases/viagem").status_code == 200


def test_a_base_whose_grafo_is_being_built_cannot_be_deleted(client, session_factory, monkeypatch):
    from app.experiments import orchestrator

    _ingest(client, "viagem")
    experiment_id = _experiment(session_factory, "exp-grafo", "running")
    monkeypatch.setitem(orchestrator._graph_progress, experiment_id, {"extracted": 2, "total": 5})

    response = client.delete("/bases/viagem")

    assert response.status_code == 409
    assert "Grafo" in response.json()["detail"]


def test_a_grafo_build_is_named_even_behind_a_queued_experiment(
    client, session_factory, monkeypatch
):
    from app.experiments import orchestrator

    _ingest(client, "viagem")
    _experiment(session_factory, "exp-fila", "pending")
    building = _experiment(session_factory, "exp-grafo", "running")
    monkeypatch.setitem(orchestrator._graph_progress, building, {"extracted": 2, "total": 5})

    detail = client.delete("/bases/viagem").json()["detail"]

    assert "Grafo" in detail and "exp-grafo" in detail
