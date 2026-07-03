"""Contextual compression RAG: condense the retrieved context, then answer."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


class CompressionRAG(RAG):
    """Compress the retrieved pool into a focused extract, then answer on it."""

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        resolved = prompts or load_technique("compression")
        self._compress_prompt = resolved["compress"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Compress the retrieved context in one call, then answer on the extract."""
        contexts = self._retriever.retrieve(query)
        if not contexts:
            generated = self._llm.generate(
                self._answer_prompt.format(context="", question=query)
            )
            return RAGResult(answer=generated.strip(), contexts=[])
        compressed_text = self._llm.generate(
            self._compress_prompt.format(
                question=query, context=format_context(contexts)
            )
        ).strip()
        compressed_contexts = [
            {"text": compressed_text, "score": 1.0, "source": "compression"}
        ]
        generated = self._llm.generate(
            self._answer_prompt.format(context=compressed_text, question=query)
        )
        return RAGResult(answer=generated.strip(), contexts=compressed_contexts)


rag_registry.register("compression", CompressionRAG)
