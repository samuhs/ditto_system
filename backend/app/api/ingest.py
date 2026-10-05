"""Endpoint to ingest uploaded documents (and, optionally, build their Grafo de conhecimento)."""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import (  # noqa: F401  get_embedder_factory: tests override it here
    get_embedder_factory,
    get_graph_build_deps,
    get_graph_builds,
    get_models,
    get_store,
)
from app.api.graph_builds import check_extractor, start_graph_build
from app.core.chunking.base import chunking_registry
from app.core.embedding.base import embedding_registry
from app.core.graph.jobs import GraphBuildDeps, GraphBuilds
from app.core.memory.manager import ModelManager
from app.core.uploads import read_upload
from app.core.vectorstore.qdrant import QdrantStore, parse_collection_name
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig, IngestResult

router = APIRouter()


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
    background_tasks: BackgroundTasks,
    base: str = Form(...),
    chunkings: str = Form(...),
    embeddings: str = Form(...),
    files: list[UploadFile] = File(...),
    # "Gerar Grafo de conhecimento": the LLM extrator; empty creates the Índices only.
    graph_extractor: str | None = Form(None),
    store: QdrantStore = Depends(get_store),
    models: ModelManager = Depends(get_models),
    builds: GraphBuilds = Depends(get_graph_builds),
    graph_deps: GraphBuildDeps = Depends(get_graph_build_deps),
) -> IngestResult:
    """Create the Índices now; with a graph_extractor, queue their Grafo build after them."""
    try:  # refused before any upload is read
        store.check_new_base_name(base)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    config = IngestConfig(base=base, chunkings=_csv(chunkings), embeddings=_csv(embeddings))
    documents = []
    for file in files:
        raw = await read_upload(file)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{file.filename or 'file'}: not valid UTF-8",
            ) from exc
        documents.append(Document(name=file.filename or "document", text=text))
    _validate(config.chunkings, chunking_registry.names(), "chunking")
    _validate(config.embeddings, embedding_registry.names(), "embedding")
    with_graph = bool(graph_extractor and graph_extractor.strip())
    if with_graph:  # refused before any Índice is written
        check_extractor(graph_extractor, graph_deps)
    result = ingest_documents(documents, config, store, models=models)
    if with_graph:
        indexes = [parse_collection_name(name)[1:] for name in result.collections]
        result.graph_build = start_graph_build(
            base, graph_extractor, indexes, builds, graph_deps, background_tasks
        )
    return result
