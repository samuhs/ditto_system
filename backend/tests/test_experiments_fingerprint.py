"""Unit tests for the Índice/Grafo fingerprint helper (issue #21)."""
from contextlib import nullcontext

from qdrant_client import QdrantClient

from app.core.graph.build import build_graph
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.fingerprint import (
    experiment_fingerprint,
    fingerprint_changes,
    graph_fingerprint,
    index_fingerprint,
)
from app.experiments.schemas import ExperimentConfig
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig


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


def _store() -> QdrantStore:
    return QdrantStore(client=QdrantClient(":memory:"))


def _ingest(store, base="viagem", text="Para one.\n\nPara two.\n\nPara three."):
    ingest_documents(
        [Document(name="a.txt", text=text)],
        IngestConfig(base=base, chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )


def test_index_fingerprint_absent_collection():
    store = _store()
    fp = index_fingerprint(store, "viagem", "recursive", "gemini")
    assert fp == {"exists": False, "points": 0, "ingested_at": None}


def test_index_fingerprint_reports_point_count():
    store = _store()
    _ingest(store)
    fp = index_fingerprint(store, "viagem", "recursive", "gemini")
    assert fp["exists"] is True
    assert fp["points"] > 0


def test_index_fingerprint_changes_after_reingesting():
    store = _store()
    _ingest(store)
    before = index_fingerprint(store, "viagem", "recursive", "gemini")
    _ingest(store, text="Mais um trecho novo de todo.")
    after = index_fingerprint(store, "viagem", "recursive", "gemini")
    assert after["points"] > before["points"]
    assert after != before


def test_graph_fingerprint_none_without_a_current_graph():
    store = _store()
    _ingest(store)
    assert graph_fingerprint(store, "viagem", "recursive", "gemini", "gemini") is None


def test_graph_fingerprint_changes_when_the_graph_is_rebuilt():
    store = _store()
    _ingest(store)
    build_graph(store, "viagem", "recursive", "gemini", "gemini", _FakeLLM(), lambda: nullcontext(_FakeEmbedder()))
    before = graph_fingerprint(store, "viagem", "recursive", "gemini", "gemini")
    assert before is not None

    build_graph(store, "viagem", "recursive", "gemini", "gemini", _FakeLLM(), lambda: nullcontext(_FakeEmbedder()))
    after = graph_fingerprint(store, "viagem", "recursive", "gemini", "gemini")
    assert after is not None
    assert after != before  # built_at always moves forward


def test_graph_fingerprint_goes_stale_after_reingesting_the_index():
    store = _store()
    _ingest(store)
    build_graph(store, "viagem", "recursive", "gemini", "gemini", _FakeLLM(), lambda: nullcontext(_FakeEmbedder()))
    assert graph_fingerprint(store, "viagem", "recursive", "gemini", "gemini") is not None

    _ingest(store, text="Um trecho totalmente diferente.")
    assert graph_fingerprint(store, "viagem", "recursive", "gemini", "gemini") is None


def _config(**overrides) -> ExperimentConfig:
    return ExperimentConfig(
        **{
            "base": "viagem", "chunkings": ["recursive"], "embeddings": ["gemini"],
            "rags": ["naive"], "retrievers": ["similarity"], "metrics": ["answer_relevancy"],
            "llms": ["gemini"],
            **overrides,
        }
    )


def test_experiment_fingerprint_has_no_graph_entry_without_graphrag():
    store = _store()
    _ingest(store)
    fp = experiment_fingerprint(_config(), store)
    assert list(fp) == ["recursive__gemini"]
    assert "graph" not in fp["recursive__gemini"]
    assert fp["recursive__gemini"]["index"]["exists"] is True


def test_experiment_fingerprint_includes_a_graph_entry_for_graphrag():
    store = _store()
    _ingest(store)
    build_graph(store, "viagem", "recursive", "gemini", "gemini", _FakeLLM(), lambda: nullcontext(_FakeEmbedder()))
    fp = experiment_fingerprint(_config(rags=["graph"], graph_extractor="gemini"), store)
    assert fp["recursive__gemini"]["graph"] is not None


def test_fingerprint_changes_is_empty_when_nothing_changed():
    store = _store()
    _ingest(store)
    fp = experiment_fingerprint(_config(), store)
    assert fingerprint_changes(fp, fp) == []


def test_fingerprint_changes_names_the_reingested_index():
    store = _store()
    _ingest(store)
    before = experiment_fingerprint(_config(), store)
    _ingest(store, text="Outro trecho qualquer aqui.")
    after = experiment_fingerprint(_config(), store)
    changes = fingerprint_changes(before, after)
    assert len(changes) == 1
    assert "recursive" in changes[0] and "gemini" in changes[0]
