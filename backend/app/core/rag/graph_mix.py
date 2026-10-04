"""graph_mix: GraphRAG whose chunks are united with the row's Retriever's (LightRAG's mix).

The query is GraphRAG's StateGraph with one node added before generation:

    ... -> score_chunks -> mix (Retriever's chunks, united without duplicates) -> generate

The Grafo's and the Retriever's chunks alternate, so neither list buries the other's
best chunk; a chunk both bring appears once, where it first comes.
"""
from itertools import chain, zip_longest

from app.core.rag.base import rag_registry
from app.core.rag.graph import GraphRAG, QueryState
from app.core.retrieval.base import Retriever


def unite(graph_chunks: list[dict], retrieved: list[dict]) -> list[dict]:
    """Alternate the two lists, keeping the first of each text."""
    seen, united = set(), []
    for context in chain.from_iterable(zip_longest(graph_chunks, retrieved)):
        if context is not None and context.get("text") not in seen:
            seen.add(context.get("text"))
            united.append(context)
    return united


class GraphMixRAG(GraphRAG):
    """GraphRAG plus the row's Retriever: uses an Índice, a Retriever and the Grafo."""

    uses_retrieval = True

    def __init__(self, retriever: Retriever, llm, graph, embedder, **kwargs) -> None:
        self._retriever = retriever
        super().__init__(retriever, llm, graph, embedder, **kwargs)

    def _extra_steps(self, top_k):
        retriever = self._retriever

        def mix(state: QueryState) -> dict:
            return {"contexts": unite(state["contexts"], retriever.retrieve(state["question"]))}

        return [("mix", mix)]


rag_registry.register("graph_mix", GraphMixRAG)
