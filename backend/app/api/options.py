"""Endpoint exposing the available techniques from the registries."""
from collections.abc import Callable

from fastapi import APIRouter, Depends

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.graph.build import current_extractors
from app.core.config.runtime import get_gemini_key
from app.core.llm.gemini import DEFAULT_GEMINI_MODEL
from app.core.llm.ollama import list_ollama_models
from app.core.rag.base import rag_registry
from app.core.retrieval.base import retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore, parse_collection_name

router = APIRouter()


def get_store() -> QdrantStore:
    return QdrantStore()


def get_ollama_lister() -> Callable[[], list[str]]:
    return list_ollama_models


def _llm_options(list_ollama: Callable[[], list[str]]) -> list[dict[str, str]]:
    """Real model names: every model on the local server, plus Gemini when a key is set.

    Without a key a Gemini run would only fail, so it is not offered.
    """
    llms = []
    if get_gemini_key() is not None:
        llms.append({"value": DEFAULT_GEMINI_MODEL, "label": DEFAULT_GEMINI_MODEL, "location": "remote"})
    try:
        names = list_ollama()
    except Exception:  # noqa: BLE001  an Ollama outage must not break the form pages
        names = []
    llms += [{"value": n, "label": n, "location": "local"} for n in names]
    return llms


def _base_indexes(store: QdrantStore) -> dict[str, list[dict]]:
    """Indexed chunking x embedding pairs per base, read from the collection names.

    Each lists the LLM extratores with a current Grafo de conhecimento of it:
    graph and graph_mix are offered only for those. Empty if the store is
    unreachable: a vector-store outage must not break the form pages.
    """
    try:
        names = store.list_collections()
    except Exception:  # noqa: BLE001
        return {}
    indexes: dict[str, list[dict]] = {}
    for name in sorted(names):
        parsed = parse_collection_name(name)
        if parsed is None:
            continue
        base, chunking, embedding = parsed
        indexes.setdefault(base, []).append({
            "chunking": chunking, "embedding": embedding,
            "graph_extractors": _graph_extractors(store, base, chunking, embedding, names),
        })
    return dict(sorted(indexes.items()))


def _graph_extractors(store: QdrantStore, base, chunking, embedding, names) -> list[str]:
    """The Índice's current Grafos' LLM extratores; none if the store fails mid-way."""
    try:
        return current_extractors(store, base, chunking, embedding, collections=names)
    except Exception:  # noqa: BLE001  an outage must not break the form pages
        return []


@router.get("/options")
def options(
    store: QdrantStore = Depends(get_store),
    list_ollama: Callable[[], list[str]] = Depends(get_ollama_lister),
) -> dict:
    """List the registered techniques, ingested bases and available LLM models."""
    base_indexes = _base_indexes(store)
    return {
        "bases": list(base_indexes),
        "base_indexes": base_indexes,
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llm_options": _llm_options(list_ollama),
        "rags": rag_registry.names(),
        "retrievers": retrieval_registry.names(),
        "metrics": evaluation_registry.names(),
    }
