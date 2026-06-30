"""Endpoint exposing the available techniques from the registries."""
from fastapi import APIRouter

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.llm.base import llm_registry
from app.core.rag.base import rag_registry
from app.core.retrieval.base import retrieval_registry

router = APIRouter()


@router.get("/options")
def options() -> dict[str, list[str]]:
    """List the registered techniques available across the pipeline."""
    return {
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llms": llm_registry.names(),
        "rags": rag_registry.names(),
        "retrievers": retrieval_registry.names(),
        "metrics": evaluation_registry.names(),
    }
