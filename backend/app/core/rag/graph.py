"""GraphRAG: answer from the Índice's Grafo de conhecimento.

The query is a LangGraph StateGraph with no LLM call before generation:

    START -> link (question vector -> top-k entities and relations)
          -> expand (1-hop neighbours) -> score_chunks (top-k chunks)
          -> generate (naive answer prompt + a short block of facts) -> END

The contexts are the Índice's chunks, in the same format as the other techniques.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.graph.knowledge import GraphRelation, KnowledgeGraph
from app.core.llm.base import LLM
from app.core.prompts import load_prompt
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

# A neighbour counts for this share of the entity it was reached from.
NEIGHBOUR_WEIGHT = 0.5
# The facts block stays short (~500 tokens) next to the chunks.
MAX_FACTS = 10
MAX_FACTS_CHARS = 2000
FACTS_HEADER = "Fatos do Grafo de conhecimento:"
# A hub entity can have hundreds of neighbours: the result keeps only the best ones.
MAX_NEIGHBOURS_SHOWN = 20


class QueryState(TypedDict, total=False):
    question: str
    entity_scores: dict[str, float]
    relations: list[tuple[GraphRelation, float]]
    node_scores: dict[str, float]
    contexts: list[dict]
    facts: list[str]
    answer: str


class GraphRAG(RAG):
    """Retrieve chunks through the Grafo de conhecimento; uses an Índice but no Retriever."""

    uses_retrieval = False
    uses_graph = True

    def __init__(
        self,
        retriever: Retriever | None,
        llm: LLM,
        graph: KnowledgeGraph,
        embedder,
        prompts: dict[str, str] | None = None,
        top_k_entities: int = 5,
        top_k_relations: int = 5,
        top_k: int = 5,
    ) -> None:
        self._graph = graph
        self._embedder = embedder
        # The naive answer prompt, so the difference comes from the retrieval.
        answer_prompt = (prompts or {}).get("answer") or load_prompt("naive", "answer")
        self._flow = self._build_flow(llm, answer_prompt, top_k_entities, top_k_relations, top_k)

    def _build_flow(self, llm, answer_prompt, top_k_entities, top_k_relations, top_k):
        graph, embedder = self._graph, self._embedder

        def link(state: QueryState) -> dict:
            vector = embedder.embed_query(state["question"])
            return {
                "entity_scores": {
                    e.key: score for e, score in graph.search_entities(vector, top_k_entities)
                },
                "relations": graph.search_relations(vector, top_k_relations),
            }

        def expand(state: QueryState) -> dict:
            scores = dict(state["entity_scores"])
            for key, score in state["entity_scores"].items():
                for neighbour in graph.neighbours(key):
                    scores[neighbour] = max(scores.get(neighbour, 0.0), score * NEIGHBOUR_WEIGHT)
            return {"node_scores": scores}

        def score_chunks(state: QueryState) -> dict:
            chunk_scores: dict[int, float] = {}
            for key, score in state["node_scores"].items():
                entity = graph.entities.get(key)
                for cid in entity.chunk_ids if entity else []:
                    chunk_scores[cid] = chunk_scores.get(cid, 0.0) + score
            for relation, score in state["relations"]:
                for cid in relation.chunk_ids:
                    chunk_scores[cid] = chunk_scores.get(cid, 0.0) + score
            ranked = sorted(
                (item for item in chunk_scores.items() if item[1] > 0 and item[0] in graph.chunks),
                key=lambda item: (-item[1], item[0]),
            )[:top_k]
            contexts = [{**graph.chunks[cid], "score": score} for cid, score in ranked]
            return {"contexts": contexts, "facts": self._facts(state)}

        def generate(state: QueryState) -> dict:
            context = format_context(state["contexts"])
            if state["facts"]:
                context += "\n\n" + FACTS_HEADER + "\n" + "\n".join(f"- {f}" for f in state["facts"])
            prompt = answer_prompt.format(context=context, question=state["question"])
            return {"answer": llm.generate(prompt).strip()}

        flow = StateGraph(QueryState)
        for name, node in [
            ("link", link), ("expand", expand), ("score_chunks", score_chunks), ("generate", generate)
        ]:
            flow.add_node(name, node)
        flow.add_edge(START, "link")
        flow.add_edge("link", "expand")
        flow.add_edge("expand", "score_chunks")
        flow.add_edge("score_chunks", "generate")
        flow.add_edge("generate", END)
        return flow.compile()

    def _facts(self, state: QueryState) -> list[str]:
        """The matched relations, then those touching a matched entity, within budget."""
        seeds = state["entity_scores"]
        candidates = [r for r, _ in state["relations"]] + [
            r for r in self._graph.relations if r.source_key in seeds or r.target_key in seeds
        ]
        facts, size = [], 0
        for fact in dict.fromkeys(r.fact() for r in candidates):
            if len(facts) == MAX_FACTS or size + len(fact) > MAX_FACTS_CHARS:
                break
            facts.append(fact)
            size += len(fact)
        return facts

    def answer(self, query: str) -> RAGResult:
        """Retrieve chunks through the graph and generate the answer."""
        state = self._flow.invoke({"question": query})
        return RAGResult(
            answer=state["answer"], contexts=state["contexts"],
            graph_explanation={"entities": self._entities_found(state), "facts": state["facts"]},
        )

    def _entities_found(self, state: QueryState) -> list[dict]:
        """The linked entities (hop 0), then their best neighbours (hop 1), by score."""
        seeds = state["entity_scores"]
        found = [
            {"name": entity.name, "score": float(score), "hop": 0 if key in seeds else 1}
            for key, score in state["node_scores"].items()
            if (entity := self._graph.entities.get(key)) is not None
        ]
        found.sort(key=lambda e: (e["hop"], -e["score"], e["name"]))
        return found[: len(seeds) + MAX_NEIGHBOURS_SHOWN]


rag_registry.register("graph", GraphRAG)
