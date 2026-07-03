"""Endpoint exposing the available techniques from the registries."""
from fastapi import APIRouter, Depends

from app.core.chunking.base import chunking_registry
from app.core.config.runtime import get_ollama_models
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.llm.base import llm_registry
from app.core.rag.base import rag_registry
from app.core.retrieval.base import retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore

router = APIRouter()


def get_store() -> QdrantStore:
    return QdrantStore()


def _ingested_bases(store: QdrantStore) -> list[str]:
    """Base names derived from collection names; empty if the store is unreachable."""
    try:
        names = store.list_collections()
    except Exception:  # noqa: BLE001  a vector-store outage must not break the form pages
        return []
    return sorted({n.split("__")[0] for n in names if "__" in n})


@router.get("/options")
def options(store: QdrantStore = Depends(get_store)) -> dict[str, list[str]]:
    """List the registered techniques and ingested bases available."""
    bases = _ingested_bases(store)
    return {
        "bases": bases,
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llms": llm_registry.names() + [m["id"] for m in get_ollama_models()],
        "rags": rag_registry.names(),
        "retrievers": retrieval_registry.names(),
        "metrics": evaluation_registry.names(),
    }
