"""Endpoint to ingest uploaded documents."""
from collections.abc import Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.embedding.base import Embedder, build_embedder
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


def _csv(value: str) -> list[str]:
    """Split a comma-separated form field into a clean list."""
    return [item.strip() for item in value.split(",") if item.strip()]


@router.post("/ingest", response_model=IngestResult)
async def ingest(
    base: str = Form(...),
    chunkings: str = Form(...),
    embeddings: str = Form(...),
    files: list[UploadFile] = File(...),
    store: QdrantStore = Depends(get_store),
    embedder_factory: Callable[..., Embedder] = Depends(get_embedder_factory),
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
    return ingest_documents(documents, config, store, embedder_factory=embedder_factory)
