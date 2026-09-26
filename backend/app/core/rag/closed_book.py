"""Closed-book baseline: the LLM answers from the question alone, without retrieval.

It shows what each LLM knows without the documents, so a configuration's gain
can be read against it (and a retrieval that hurts the answer shows up).
"""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, rag_registry
from app.core.retrieval.base import Retriever


class ClosedBookRAG(RAG):
    """Generate without context; the retriever is accepted and never called."""

    uses_retrieval = False

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._llm = llm
        resolved = prompts or load_technique("closed_book")
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Answer from the model's own knowledge."""
        generated = self._llm.generate(self._answer_prompt.format(question=query))
        return RAGResult(answer=generated.strip(), contexts=[])


rag_registry.register("closed_book", ClosedBookRAG)
