"""Maximal Marginal Relevance retriever (diversifies results)."""
from app.core.embedding.base import Embedder
from app.core.retrieval.base import Retriever, cosine_similarity, retrieval_registry
from app.core.vectorstore.qdrant import QdrantStore


def _mmr_select(
    query_vector: list[float],
    candidate_vectors: list[list[float]],
    top_k: int,
    lambda_mult: float,
) -> list[int]:
    """Select indices maximizing relevance while penalizing redundancy."""
    selected: list[int] = []
    remaining = list(range(len(candidate_vectors)))
    while remaining and len(selected) < top_k:
        best_index = remaining[0]
        best_score = None
        for index in remaining:
            relevance = cosine_similarity(query_vector, candidate_vectors[index])
            diversity = max(
                (cosine_similarity(candidate_vectors[index], candidate_vectors[s]) for s in selected),
                default=0.0,
            )
            score = lambda_mult * relevance - (1 - lambda_mult) * diversity
            if best_score is None or score > best_score:
                best_score = score
                best_index = index
        selected.append(best_index)
        remaining.remove(best_index)
    return selected


class MMRRetriever(Retriever):
    """Retrieves diverse chunks using Maximal Marginal Relevance."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        top_k: int = 5,
        fetch_k: int = 20,
        lambda_mult: float = 0.5,
    ) -> None:
        self._store = store
        self._collection = collection
        self._embedder = embedder
        self._top_k = top_k
        self._fetch_k = fetch_k
        self._lambda_mult = lambda_mult

    def retrieve(self, query: str) -> list[dict]:
        """Fetch candidates, then re-rank for diversity with MMR."""
        query_vector = self._embedder.embed_query(query)
        hits = self._store.search(
            self._collection, query_vector, top_k=self._fetch_k, with_vectors=True
        )
        if not hits:
            return []
        indices = _mmr_select(
            query_vector,
            [hit["vector"] for hit in hits],
            self._top_k,
            self._lambda_mult,
        )
        return [{**hits[i]["payload"], "score": hits[i]["score"]} for i in indices]


retrieval_registry.register("mmr", MMRRetriever)
