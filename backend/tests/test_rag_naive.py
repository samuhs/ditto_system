"""Tests for NaiveRAG."""
from app.core.rag.base import RAG, RAGResult, build_rag, rag_registry
from app.core.rag.naive import NaiveRAG


class _StubRetriever:
    """Returns two fixed documents regardless of query."""

    def retrieve(self, query: str) -> list[dict]:
        return [
            {"text": "The center is around the main square.", "source_doc": "a.txt", "score": 0.9},
            {"text": "The food street has artisanal cheese.", "source_doc": "a.txt", "score": 0.8},
        ]


class _EchoLLM:
    """Echoes the prompt it received so the test can inspect it."""

    def __init__(self) -> None:
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return "The center is around the main square."


def test_naive_rag_builds_prompt_with_context_and_answers():
    llm = _EchoLLM()
    rag = NaiveRAG(_StubRetriever(), llm)
    result = rag.answer("Where is the center?")
    assert isinstance(result, RAGResult)
    assert result.answer == "The center is around the main square."
    assert len(result.contexts) == 2
    assert "main square" in llm.last_prompt
    assert "Where is the center?" in llm.last_prompt


def test_naive_rag_registered_and_built():
    assert "naive" in rag_registry.names()
    rag = build_rag("naive", retriever=_StubRetriever(), llm=_EchoLLM())
    assert isinstance(rag, RAG)


def test_naive_rag_uses_injected_answer_prompt():
    llm = _EchoLLM()
    rag = NaiveRAG(_StubRetriever(), llm, prompts={"answer": "CUSTOM {context} :: {question}"})
    rag.answer("Where is the center?")
    assert llm.last_prompt.startswith("CUSTOM ")
    assert "Where is the center?" in llm.last_prompt
