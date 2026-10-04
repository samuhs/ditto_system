"""Endpoint to ingest uploaded documents."""
from collections.abc import Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.chunking.base import chunking_registry
from app.core.embedding.base import Embedder, build_embedder, embedding_registry
from app.core.memory.manager import ModelManager, get_model_manager
from app.core.memory.profile import active_profile
from app.core.vectorstore.qdrant import QdrantStore
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig, IngestResult

router = APIRouter()


def get_store() -> QdrantStore:
    """FastAPI dependency providing the vector store."""
    return QdrantStore()


def get_embedder_factory() -> Callable[..., Embedder]:
    """FastAPI dependency providing the embedder factory."""
    return build_embedder


def get_models(
    embedder_factory: Callable[..., Embedder] = Depends(get_embedder_factory),
) -> ModelManager:
    """The shared model cache; a test-injected factory gets a private one."""
    if embedder_factory is build_embedder:
        return get_model_manager()
    return ModelManager(embedder_factory, max_local=active_profile().max_local_models)


def _csv(value: str) -> list[str]:
    """Split a comma-separated form field into a clean, de-duplicated list."""
    items = [item.strip() for item in value.split(",") if item.strip()]
    return list(dict.fromkeys(items))


def _validate(names: list[str], available: list[str], kind: str) -> None:
    """Raise 422 if any requested technique name is not registered."""
    unknown = [name for name in names if name not in available]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown {kind}: {unknown}. Available: {available}",
        )


@router.post("/ingest", response_model=IngestResult)
async def ingest(
    base: str = Form(...),
    chunkings: str = Form(...),
    embeddings: str = Form(...),
    files: list[UploadFile] = File(...),
    store: QdrantStore = Depends(get_store),
    models: ModelManager = Depends(get_models),
) -> IngestResult:
    """Ingest uploaded documents under the given configuration."""
    documents = []
    for file in files:
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{file.filename or 'file'}: not valid UTF-8",
            ) from exc
        documents.append(Document(name=file.filename or "document", text=text))
    config = IngestConfig(
        base=base, chunkings=_csv(chunkings), embeddings=_csv(embeddings)
    )
    _validate(config.chunkings, chunking_registry.names(), "chunking")
    _validate(config.embeddings, embedding_registry.names(), "embedding")
    return ingest_documents(documents, config, store, models=models)
