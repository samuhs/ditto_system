"""Endpoint exposing the available techniques from the registries."""
from fastapi import APIRouter

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.llm.base import llm_registry

router = APIRouter()


@router.get("/options")
def options() -> dict[str, list[str]]:
    """List the registered chunking, embedding, and LLM techniques."""
    return {
        "chunkings": chunking_registry.names(),
        "embeddings": embedding_registry.names(),
        "llms": llm_registry.names(),
    }
