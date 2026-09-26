"""Oracle condition: the LLM answers with the annotated evidence as its context.

It is each LLM's best case (retrieval assumed perfect). A configuration can be
read as a share of it, and a question still answered badly here is hard for
the model itself, not for the retrieval. Needs the question's reference
evidence, so experiments run it only on questions that have one.
"""
from app.core.llm.base import LLM
from app.core.prompts import load_technique
from app.core.rag.base import RAG, RAGResult, format_context, rag_registry
from app.core.retrieval.base import Retriever


class OracleRAG(RAG):
    """Generate from the reference evidence; the retriever is accepted and never called."""

    uses_retrieval = False
    uses_evidence = True

    def __init__(
        self, retriever: Retriever, llm: LLM, prompts: dict[str, str] | None = None
    ) -> None:
        self._llm = llm
        resolved = prompts or load_technique("oracle")
        self._answer_prompt = resolved["answer"]

    def answer(self, query: str, evidence: list[str] | None = None) -> RAGResult:
        """Answer from the evidence passages, in their annotated order."""
        if not evidence:
            raise ValueError("the oracle needs the question's reference evidence")
        contexts = [{"text": passage, "source": "oracle"} for passage in evidence]
        prompt = self._answer_prompt.format(context=format_context(contexts), question=query)
        return RAGResult(answer=self._llm.generate(prompt).strip(), contexts=contexts)


rag_registry.register("oracle", OracleRAG)
