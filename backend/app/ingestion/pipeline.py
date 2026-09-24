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
) -> IngestResult:
    """Chunk, embed, and store every chunking x embedding combination."""
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
                for document in documents:
                    chunks = chunker.split(document.text)
                    if not chunks:
                        continue
                    vectors = embedder.embed_documents(chunks)
                    payloads = [
                        {
                            "source_doc": document.name,
                            "chunking_strategy": chunking,
                            "embedding_model": embedding,
                            "chunk_index": index,
                            "text": chunk,
                        }
                        for index, chunk in enumerate(chunks)
                    ]
                    store.add(name, vectors, payloads)
                    total_chunks += len(chunks)
                collections.append(name)
    return IngestResult(collections=collections, total_chunks=total_chunks)
