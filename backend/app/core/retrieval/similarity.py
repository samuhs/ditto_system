"""Dense similarity retriever (top-k vector search)."""
from app.core.embedding.base import Embedder
from app.core.retrieval.base import Retriever, retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore


class SimilarityRetriever(Retriever):
    """Retrieves the top-k nearest chunks by vector similarity."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        top_k: int = 5,
    ) -> None:
        self._store = store
        self._collection = collection
        self._embedder = embedder
        self._top_k = top_k

    def retrieve(self, query: str) -> list[dict]:
        """Embed the query and return the nearest chunks."""
        query_vector = self._embedder.embed_query(query)
        hits = self._store.search(self._collection, query_vector, top_k=self._top_k)
        return [{**hit["payload"], "score": hit["score"]} for hit in hits]


retrieval_registry.register("similarity", SimilarityRetriever)
