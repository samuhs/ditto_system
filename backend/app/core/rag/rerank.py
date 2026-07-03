"""Rerank RAG: retrieve, let the LLM reorder, answer with the top ones."""
import re

from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


def _parse_ranking(text: str, n: int) -> list[int]:
    """Parse a ranking string into a full permutation of range(n).

    Extract integers in order, drop duplicates and out-of-range values,
    then append any missing indices in natural order.
    """
    order: list[int] = []
    for token in re.findall(r"\d+", text):
        i = int(token)
        if 0 <= i < n and i not in order:
            order.append(i)
    for i in range(n):
        if i not in order:
            order.append(i)
    return order


class RerankRAG(RAG):
    """Retrieve a pool, rerank it with the LLM, answer with the top keep_n."""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLM,
        prompts: dict[str, str] | None = None,
        keep_n: int = 3,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._keep_n = keep_n
        resolved = prompts or load_technique("rerank")
        self._rerank_prompt = resolved["rerank"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Retrieve, rerank via the LLM, and answer with the top contexts."""
        contexts = self._retriever.retrieve(query)
        if contexts:
            documents = "\n".join(
                f"[{i}] {c.get('text', '')}" for i, c in enumerate(contexts)
            )
            ranking = self._llm.generate(
                self._rerank_prompt.format(question=query, documents=documents)
            )
            order = _parse_ranking(ranking, len(contexts))
            contexts = [contexts[i] for i in order][: self._keep_n]
        generated = self._llm.generate(
            self._answer_prompt.format(
                context=format_context(contexts), question=query
            )
        )
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("rerank", RerankRAG)
