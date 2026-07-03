"""Corrective RAG: grade the context, rewrite and re-retrieve if insufficient."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever

_INSUFFICIENT = "INSUFICIENTE"


class CragRAG(RAG):
    """Retrieve, grade; if insufficient, rewrite the query and retry, then answer."""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLM,
        prompts: dict[str, str] | None = None,
        max_corrections: int = 1,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._max_corrections = max_corrections
        resolved = prompts or load_technique("crag")
        self._grade_prompt = resolved["grade"]
        self._rewrite_prompt = resolved["rewrite"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Grade the retrieved context and correct the query if it is insufficient."""
        contexts = self._retriever.retrieve(query)
        for _ in range(self._max_corrections):
            verdict = self._llm.generate(
                self._grade_prompt.format(
                    question=query, context=format_context(contexts)
                )
            )
            if not verdict.strip().upper().startswith(_INSUFFICIENT):
                break
            new_query = self._llm.generate(
                self._rewrite_prompt.format(question=query)
            ).strip()
            contexts = self._retriever.retrieve(new_query)
        generated = self._llm.generate(
            self._answer_prompt.format(
                context=format_context(contexts), question=query
            )
        )
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("crag", CragRAG)
