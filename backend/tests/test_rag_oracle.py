"""Tests for OracleRAG (answer with the annotated evidence as context)."""
import pytest

from app.core.rag.base import build_rag, rag_registry
from app.core.rag.oracle import OracleRAG


class _FailingRetriever:
    def retrieve(self, query: str) -> list[dict]:
        raise AssertionError("oracle must not retrieve")


class _EchoLLM:
    def __init__(self) -> None:
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return " Na praça. "


def test_oracle_answers_with_the_evidence_as_context():
    llm = _EchoLLM()
    result = OracleRAG(_FailingRetriever(), llm).answer("Onde?", evidence=["Fica na praça.", "Perto da igreja."])
    assert result.answer == "Na praça."
    assert [c["text"] for c in result.contexts] == ["Fica na praça.", "Perto da igreja."]
    assert all(c["source"] == "oracle" for c in result.contexts)
    assert "Fica na praça." in llm.last_prompt and "Onde?" in llm.last_prompt


def test_oracle_without_evidence_fails():
    with pytest.raises(ValueError):
        OracleRAG(_FailingRetriever(), _EchoLLM()).answer("Onde?")


def test_oracle_is_registered_needs_evidence_and_never_retrieves():
    assert "oracle" in rag_registry.names()
    rag = build_rag("oracle", retriever=_FailingRetriever(), llm=_EchoLLM())
    assert rag.uses_evidence and not rag.uses_retrieval
