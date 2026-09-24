"""Ingestion pipeline: chunk, embed, and store documents per combination."""
from collections.abc import Callable

from app.core.chunking.base import Chunker, build_chunker
from app.core.embedding.base import Embedder, build_embedder
from app.core.memory.device import resolve_embedding_device
from app.core.memory.manager import ModelManager
from app.core.memory.profile import active_profile
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.ingestion.schemas import Document, IngestConfig, IngestResult


def _build_chunker_for(chunking: str, embedder: Embedder) -> Chunker:
    """Build a chunker, injecting the embedder only for the semantic strategy."""
    if chunking == "semantic":
        return build_chunker(chunking, embedder=embedder)
    return build_chunker(chunking)


def ingest_documents(
    documents: list[Document],
    config: IngestConfig,
    store: QdrantStore,
    embedder_factory: Callable[..., Embedder] = build_embedder,
    models: ModelManager | None = None,
    batch_size: int = 256,
) -> IngestResult:
    """Chunk, embed, and store every chunking x embedding combination.

    Chunks are embedded and stored `batch_size` at a time, so a large document
    never holds all its vectors in memory at once.
    """
    profile = active_profile()
    models = models or ModelManager(embedder_factory, max_local=profile.max_local_models)
    device = resolve_embedding_device(profile)
    collections: list[str] = []
    total_chunks = 0
    for embedding in config.embeddings:
        with models.acquire(embedding, device) as embedder:
            for chunking in config.chunkings:
                name = collection_name(config.base, chunking, embedding)
                store.ensure_collection(name, embedder.dimension)
                chunker = _build_chunker_for(chunking, embedder)
                next_id = store.count(name)
                for document in documents:
                    chunks = chunker.split(document.text)
                    for start in range(0, len(chunks), batch_size):
                        batch = chunks[start : start + batch_size]
                        payloads = [
                            {
                                "source_doc": document.name,
                                "chunking_strategy": chunking,
                                "embedding_model": embedding,
                                "chunk_index": start + offset,
                                "text": chunk,
                            }
                            for offset, chunk in enumerate(batch)
                        ]
                        store.add(name, embedder.embed_documents(batch), payloads, start_id=next_id)
                        next_id += len(batch)
                    total_chunks += len(chunks)
                collections.append(name)
    return IngestResult(collections=collections, total_chunks=total_chunks)
