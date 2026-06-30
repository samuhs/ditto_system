"""Tests for the ingestion pipeline."""
from pathlib import Path

from qdrant_client import QdrantClient

from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig


class _FakeEmbedder:
    """Deterministic 3-dim embedder; no network."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), 1.0, 0.0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text) % 7), 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


def _factory(name: str, **kwargs) -> _FakeEmbedder:
    return _FakeEmbedder()


def test_ingest_creates_collections_and_inserts():
    store = QdrantStore(client=QdrantClient(":memory:"))
    docs = [Document(name="a.txt", text="Para 1.\n\nPara 2 is here.\n\nPara 3 ok.")]
    config = IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"])

    result = ingest_documents(docs, config, store, embedder_factory=_factory)

    name = collection_name("viagem", "recursive", "gemini")
    assert result.collections == [name]
    assert result.total_chunks > 0
    hits = store.search(name, query_vector=[1.0, 1.0, 0.0], top_k=10)
    assert len(hits) == result.total_chunks
    assert hits[0]["payload"]["source_doc"] == "a.txt"
    assert hits[0]["payload"]["chunking_strategy"] == "recursive"
    assert hits[0]["payload"]["embedding_model"] == "gemini"
    assert "text" in hits[0]["payload"]
    assert "chunk_index" in hits[0]["payload"]


def test_ingest_cartesian_over_combinations():
    store = QdrantStore(client=QdrantClient(":memory:"))
    docs = [Document(name="a.txt", text="One sentence. Two sentence. Three sentence.")]
    config = IngestConfig(
        base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"]
    )
    result = ingest_documents(docs, config, store, embedder_factory=_factory)
    assert set(result.collections) == {
        collection_name("viagem", "recursive", "gemini"),
        collection_name("viagem", "token", "gemini"),
    }


def test_ingest_real_travel_guide_document():
    store = QdrantStore(client=QdrantClient(":memory:"))
    path = Path(__file__).resolve().parents[2] / "database" / "faq_manus_completa.md"
    text = path.read_text(encoding="utf-8")
    docs = [Document(name=path.name, text=text)]
    config = IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"])
    result = ingest_documents(docs, config, store, embedder_factory=_factory)
    assert result.total_chunks > 5
