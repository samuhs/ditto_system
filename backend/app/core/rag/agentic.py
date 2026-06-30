"""Agentic RAG: a bounded loop where the LLM decides to search or answer."""
from app.core.llm.base import LLM
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

_DECIDE_PROMPT = (
    "You are answering a question using retrieved context. Based on the context "
    "so far, decide your next action. Reply with exactly one line:\n"
    "'SEARCH: <a better search query>' if you need more information, or\n"
    "'ANSWER: <your final answer>' if the context is sufficient.\n\n"
    "Question: {question}\n\nContext so far:\n{context}"
)
_ANSWER_PROMPT = (
    "Answer the question using the context.\n\nContext:\n{context}\n\n"
    "Question: {question}\n\nAnswer:"
)
_SEARCH_TAG = "SEARCH:"
_ANSWER_TAG = "ANSWER:"


class AgenticRAG(RAG):
    """Iteratively retrieves and lets the LLM decide when to answer."""

    def __init__(self, retriever: Retriever, llm: LLM, max_steps: int = 3) -> None:
        self._retriever = retriever
        self._llm = llm
        self._max_steps = max_steps

    def answer(self, query: str) -> RAGResult:
        """Run the bounded search-or-answer loop and return the result."""
        contexts: list[dict] = []
        current_query = query
        for _ in range(self._max_steps):
            contexts.extend(self._retriever.retrieve(current_query))
            decision = self._llm.generate(
                _DECIDE_PROMPT.format(question=query, context=format_context(contexts))
            ).strip()
            if decision.startswith(_ANSWER_TAG):
                return RAGResult(
                    answer=decision[len(_ANSWER_TAG):].strip(), contexts=contexts
                )
            if decision.startswith(_SEARCH_TAG):
                current_query = decision[len(_SEARCH_TAG):].strip()
                continue
            return RAGResult(answer=decision, contexts=contexts)
        final = self._llm.generate(
            _ANSWER_PROMPT.format(question=query, context=format_context(contexts))
        )
        return RAGResult(answer=final.strip(), contexts=contexts)


rag_registry.register("agentic", AgenticRAG)
