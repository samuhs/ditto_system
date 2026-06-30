"""Naive RAG: retrieve top-k, stuff into the prompt, generate."""
from app.core.llm.base import LLM
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

_PROMPT = (
    "Use the context below to answer the question. If the context is not "
    "enough, say what you can.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"
)


class NaiveRAG(RAG):
    """Single-shot retrieve-then-generate technique."""

    def __init__(self, retriever: Retriever, llm: LLM) -> None:
        self._retriever = retriever
        self._llm = llm

    def answer(self, query: str) -> RAGResult:
        """Retrieve context and generate a grounded answer."""
        contexts = self._retriever.retrieve(query)
        prompt = _PROMPT.format(context=format_context(contexts), question=query)
        answer = self._llm.generate(prompt)
        return RAGResult(answer=answer, contexts=contexts)


rag_registry.register("naive", NaiveRAG)
