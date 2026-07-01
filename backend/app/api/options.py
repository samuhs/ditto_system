"""Endpoint exposing the available techniques from the registries."""
from fastapi import APIRouter, Depends

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.llm.base import llm_registry
from app.core.rag.base import rag_registry
from app.core.retrieval.base import retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore

router = APIRouter()


def get_store() -> QdrantStore:
    return QdrantStore()


@router.get("/options")
def options(store: QdrantStore = Depends(get_store)) -> dict[str, list[str]]:
    """List the registered techniques and ingested bases available."""
    collections = store._client.get_collections().collections
    bases = sorted({c.name.split("__")[0] for c in collections if "__" in c.name})
    return {
        "bases": bases,
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llms": llm_registry.names(),
        "rags": rag_registry.names(),
        "retrievers": retrieval_registry.names(),
        "metrics": evaluation_registry.names(),
    }
