"""Chat and ingestion lease embedders from the ModelManager instead of rebuilding them."""
from qdrant_client import QdrantClient

from app.core.chat.deps import ChatDeps
from app.core.memory.manager import ModelManager
from app.core.vectorstore.qdrant import QdrantStore
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig


class _Emb:
    def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]

    @property
    def dimension(self):
        return 3


def _counting_factory(loads):
    def factory(name, **kwargs):
        loads.append(name)
        return _Emb()
    return factory


def test_chat_deps_default_manager_wraps_the_factory():
    loads = []
    deps = ChatDeps(store=None, session_factory=None, embedder_factory=_counting_factory(loads))
    with deps.models.acquire("gemini"), deps.models.acquire("gemini"):
        pass
    assert loads == ["gemini"]


def test_ingestion_loads_each_embedding_once_across_calls():
    loads = []
    models = ModelManager(_counting_factory(loads), max_local=1, is_local=lambda n: False)
    store = QdrantStore(client=QdrantClient(":memory:"))
    config = IngestConfig(base="b", chunkings=["recursive"], embeddings=["gemini"])
    for _ in range(2):
        ingest_documents([Document(name="a.txt", text="Um texto.")], config, store, models=models)
    assert loads == ["gemini"]
