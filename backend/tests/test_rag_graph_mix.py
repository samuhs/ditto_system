"""Tests for graph_mix: the Grafo de conhecimento's chunks united with the Retriever's."""
from app.core.rag.base import build_rag, rag_registry
from tests.test_rag_graph import (
    CACHOEIRA,
    IGREJA,
    SITIO,
    _AnswerLLM,
    _graph,
    _indexed_store,
    _KeywordEmbedder,
)


class _FixedRetriever:
    """Returns the given chunks for any question."""

    def __init__(self, texts):
        self._texts = texts
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return [{"text": t, "source_doc": "guia.md", "chunk_index": i, "score": 0.9}
                for i, t in enumerate(self._texts)]


def test_graph_mix_unites_the_grafos_chunks_with_the_retrievers_without_duplicates():
    graph = _graph(_indexed_store())
    retriever = _FixedRetriever([SITIO, IGREJA])
    llm = _AnswerLLM()
    rag = build_rag(
        "graph_mix", retriever=retriever, llm=llm, graph=graph, embedder=_KeywordEmbedder(),
        top_k_entities=1, top_k_relations=1, top_k=2,
    )

    result = rag.answer("O que tem perto da Cachoeira do Dédi?")

    # The Grafo brings Cachoeira and Sítio; the Retriever, Sítio again and Igreja.
    texts = [c["text"] for c in result.contexts]
    assert texts == [CACHOEIRA, SITIO, IGREJA]  # alternating, Sítio once
    assert retriever.queries == ["O que tem perto da Cachoeira do Dédi?"]
    # One generation, with every chunk and the Grafo's facts.
    [prompt] = llm.prompts
    assert all(t in prompt for t in texts)
    assert "Fatos do Grafo de conhecimento:" in prompt


def test_graph_mix_uses_an_index_a_retriever_and_the_grafo():
    technique = rag_registry.get("graph_mix")
    assert technique.uses_index and technique.uses_retrieval and technique.uses_graph
