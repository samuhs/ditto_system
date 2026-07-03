"""Tests for RerankRAG and _parse_ranking."""
import pytest

from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.rerank import RerankRAG, _parse_ranking


class _StubRetriever:
    def __init__(self, docs):
        self._docs = docs

    def retrieve(self, query):
        return list(self._docs)


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self._responses.pop(0)


def _docs(n):
    return [{"text": f"doc{i}", "score": 1.0 - i * 0.1} for i in range(n)]


@pytest.mark.parametrize("text,n,expected", [
    ("2,0,1", 3, [2, 0, 1]),
    ("1", 3, [1, 0, 2]),
    ("5,9", 2, [0, 1]),
    ("abc", 2, [0, 1]),
    ("1,1,0", 2, [1, 0]),
])
def test_parse_ranking(text, n, expected):
    assert _parse_ranking(text, n) == expected


def test_rerank_reorders_and_truncates():
    retriever = _StubRetriever(_docs(3))
    llm = _QueueLLM(["2,0,1", "Resposta."])
    rag = RerankRAG(retriever, llm, keep_n=2)
    result = rag.answer("pergunta?")
    assert [c["text"] for c in result.contexts] == ["doc2", "doc0"]
    assert result.answer == "Resposta."


def test_rerank_empty_pool_skips_rerank():
    retriever = _StubRetriever([])
    llm = _QueueLLM(["Resposta sem contexto."])
    rag = RerankRAG(retriever, llm)
    result = rag.answer("pergunta?")
    assert result.contexts == []
    assert result.answer == "Resposta sem contexto."


def test_rerank_registered_and_prompts():
    assert "rerank" in rag_registry.names()
    rag = build_rag("rerank", retriever=_StubRetriever(_docs(1)), llm=_QueueLLM(["0", "a"]))
    assert isinstance(rag, RAG)
    assert set(load_technique("rerank").keys()) == {"rerank", "answer"}
