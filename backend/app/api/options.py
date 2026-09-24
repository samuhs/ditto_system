"""Endpoint exposing the available techniques from the registries."""
from collections.abc import Callable

from fastapi import APIRouter, Depends

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.llm.gemini import DEFAULT_GEMINI_MODEL
from app.core.llm.ollama import list_ollama_models
from app.core.rag.base import rag_registry
from app.core.retrieval.base import retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore

router = APIRouter()


def get_store() -> QdrantStore:
    return QdrantStore()


def get_ollama_lister() -> Callable[[], list[str]]:
    return list_ollama_models


def _llm_options(list_ollama: Callable[[], list[str]]) -> list[dict[str, str]]:
    """Real model names: the Gemini model in use plus every model on the Ollama server."""
    llms = [{"value": DEFAULT_GEMINI_MODEL, "label": DEFAULT_GEMINI_MODEL, "location": "remote"}]
    try:
        names = list_ollama()
    except Exception:  # noqa: BLE001  an Ollama outage must not break the form pages
        names = []
    llms += [{"value": n, "label": n, "location": "local"} for n in names]
    return llms


def _ingested_bases(store: QdrantStore) -> list[str]:
    """Base names derived from collection names; empty if the store is unreachable."""
    try:
        names = store.list_collections()
    except Exception:  # noqa: BLE001  a vector-store outage must not break the form pages
        return []
    return sorted({n.split("__")[0] for n in names if "__" in n})


@router.get("/options")
def options(
    store: QdrantStore = Depends(get_store),
    list_ollama: Callable[[], list[str]] = Depends(get_ollama_lister),
) -> dict[str, list]:
    """List the registered techniques, ingested bases and available LLM models."""
    bases = _ingested_bases(store)
    llm_options = _llm_options(list_ollama)
    return {
        "bases": bases,
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llms": [o["value"] for o in llm_options],
        "llm_options": llm_options,
        "rags": rag_registry.names(),
        "retrievers": retrieval_registry.names(),
        "metrics": evaluation_registry.names(),
    }
