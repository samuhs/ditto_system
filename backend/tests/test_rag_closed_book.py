"""Tests for ClosedBookRAG (no-retrieval baseline)."""
from app.core.rag.base import build_rag, rag_registry
from app.core.rag.closed_book import ClosedBookRAG


class _FailingRetriever:
    def retrieve(self, query: str) -> list[dict]:
        raise AssertionError("closed book must not retrieve")


class _EchoLLM:
    def __init__(self) -> None:
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return "  Não sei.  "


def test_closed_book_answers_from_the_question_alone():
    llm = _EchoLLM()
    result = ClosedBookRAG(_FailingRetriever(), llm).answer("Onde fica o centro?")
    assert result.answer == "Não sei." and result.contexts == []
    assert "Onde fica o centro?" in llm.last_prompt


def test_closed_book_registered_and_uses_its_prompt():
    assert "closed_book" in rag_registry.names()
    llm = _EchoLLM()
    rag = build_rag("closed_book", retriever=_FailingRetriever(), llm=llm,
                    prompts={"answer": "P: {question}"})
    rag.answer("Q?")
    assert llm.last_prompt == "P: Q?"
