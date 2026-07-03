"""Tests for CompressionRAG."""
from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.compression import CompressionRAG


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


_DOCS = [
    {"text": "Trecho relevante A.", "score": 0.9},
    {"text": "Ruido irrelevante B.", "score": 0.5},
]


def test_compression_collapses_to_single_context():
    retriever = _StubRetriever(_DOCS)
    llm = _QueueLLM(["Extrato: apenas A.", "Resposta final."])
    rag = CompressionRAG(retriever, llm)
    result = rag.answer("pergunta?")
    assert len(result.contexts) == 1
    assert result.contexts[0]["text"] == "Extrato: apenas A."
    assert "Extrato: apenas A." in llm.prompts[1]
    assert result.answer == "Resposta final."


def test_compression_empty_pool_answers_without_compress():
    retriever = _StubRetriever([])
    llm = _QueueLLM(["Resposta sem contexto."])
    rag = CompressionRAG(retriever, llm)
    result = rag.answer("pergunta?")
    assert result.contexts == []
    assert result.answer == "Resposta sem contexto."


def test_compression_registered_and_prompts():
    assert "compression" in rag_registry.names()
    rag = build_rag("compression", retriever=_StubRetriever(_DOCS), llm=_QueueLLM(["c", "a"]))
    assert isinstance(rag, RAG)
    assert set(load_technique("compression").keys()) == {"compress", "answer"}
