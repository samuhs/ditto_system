"""Naive RAG: retrieve top-k, stuff into the prompt, generate."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


class NaiveRAG(RAG):
    """Single-shot retrieve-then-generate technique."""

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        resolved = prompts or load_technique("naive")
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Retrieve context and generate a grounded answer."""
        contexts = self._retriever.retrieve(query)
        prompt = self._answer_prompt.format(
            context=format_context(contexts), question=query
        )
        generated = self._llm.generate(prompt)
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("naive", NaiveRAG)
