"""Parent-document retriever: expands hits with neighboring chunks."""
from app.core.embedding.base import Embedder
from app.core.retrieval.base import Retriever, retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore


class ParentDocumentRetriever(Retriever):
    """Retrieves top chunks and expands each with its neighbors."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        top_k: int = 3,
        window: int = 1,
    ) -> None:
        self._store = store
        self._collection = collection
        self._embedder = embedder
        self._top_k = top_k
        self._window = window

    def retrieve(self, query: str) -> list[dict]:
        """Return top chunks expanded with same-document neighbors."""
        query_vector = self._embedder.embed_query(query)
        hits = self._store.search(self._collection, query_vector, top_k=self._top_k)
        results = []
        for hit in hits:
            payload = hit["payload"]
            source = payload["source_doc"]
            index = payload["chunk_index"]
            siblings = self._store.scroll(self._collection, where={"source_doc": source})
            window_chunks = sorted(
                (
                    s["payload"]
                    for s in siblings
                    if abs(s["payload"]["chunk_index"] - index) <= self._window
                ),
                key=lambda p: p["chunk_index"],
            )
            text = " ".join(chunk["text"] for chunk in window_chunks)
            results.append(
                {
                    "text": text,
                    "score": hit["score"],
                    "source_doc": source,
                    "chunk_index": index,
                }
            )
        return results


retrieval_registry.register("parent_document", ParentDocumentRetriever)
