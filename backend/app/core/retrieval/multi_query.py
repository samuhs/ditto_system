"""Multi-query retriever: expands the query with LLM-generated variations."""
from app.core.embedding.base import Embedder
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.retrieval.base import Retriever, retrieval_registry
from app.core.retrieval.similarity import SimilarityRetriever
from app.core.vectorstore.qdrant import QdrantStore


class MultiQueryRetriever(Retriever):
    """Retrieves with the original query plus LLM-generated variations."""

    def __init__(
        self,
        store: QdrantStore,
        collection: str,
        embedder: Embedder,
        llm: LLM,
        top_k: int = 5,
        n_queries: int = 3,
        prompts: dict[str, str] | None = None,
    ) -> None:
        self._base = SimilarityRetriever(store, collection, embedder, top_k=top_k)
        self._llm = llm
        self._n_queries = n_queries
        resolved = prompts or load_technique("multi_query")
        self._prompt = resolved["generate"]

    def _variations(self, query: str) -> list[str]:
        """Ask the LLM for alternative phrasings of the query."""
        raw = self._llm.generate(
            self._prompt.format(n=self._n_queries, question=query)
        )
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def retrieve(self, query: str) -> list[dict]:
        """Union retrieval over the query and its variations, deduplicated."""
        merged: dict[tuple, dict] = {}
        for candidate in [query, *self._variations(query)]:
            for context in self._base.retrieve(candidate):
                key = (context["source_doc"], context["chunk_index"])
                merged.setdefault(key, context)
        return list(merged.values())


retrieval_registry.register("multi_query", MultiQueryRetriever)
