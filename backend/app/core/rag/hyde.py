"""HyDE RAG: retrieve using a hypothetical document, then answer."""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


class HydeRAG(RAG):
    """Generate a hypothetical passage, retrieve with it, then answer."""

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        resolved = prompts or load_technique("hyde")
        self._hypothesis_prompt = resolved["hypothesis"]
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str) -> RAGResult:
        """Retrieve with a hypothetical document, then generate a grounded answer."""
        hypo = self._llm.generate(
            self._hypothesis_prompt.format(question=query)
        ).strip()
        contexts = self._retriever.retrieve(hypo)
        generated = self._llm.generate(
            self._answer_prompt.format(
                context=format_context(contexts), question=query
            )
        )
        return RAGResult(answer=generated.strip(), contexts=contexts)


rag_registry.register("hyde", HydeRAG)
