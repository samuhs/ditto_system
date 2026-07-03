"""Tests for CragRAG."""
from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.crag import CragRAG


class _RecordingRetriever:
    def __init__(self, docs):
        self._docs = docs
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return list(self._docs)


class _QueueLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def generate(self, prompt):
        return self._responses.pop(0)


_DOCS = [{"text": "contexto", "score": 0.9}]


def test_crag_sufficient_does_not_rewrite():
    retriever = _RecordingRetriever(_DOCS)
    llm = _QueueLLM(["SUFICIENTE, o contexto responde.", "Resposta final."])
    rag = CragRAG(retriever, llm)
    result = rag.answer("pergunta original?")
    assert retriever.queries == ["pergunta original?"]
    assert result.answer == "Resposta final."


def test_crag_insufficient_rewrites_and_reretrieves():
    retriever = _RecordingRetriever(_DOCS)
    llm = _QueueLLM(["INSUFICIENTE, falta detalhe.", "consulta reescrita", "Resposta final."])
    rag = CragRAG(retriever, llm, max_corrections=1)
    result = rag.answer("pergunta original?")
    assert retriever.queries == ["pergunta original?", "consulta reescrita"]
    assert result.answer == "Resposta final."


def test_crag_registered_and_prompts():
    assert "crag" in rag_registry.names()
    rag = build_rag("crag", retriever=_RecordingRetriever(_DOCS), llm=_QueueLLM(["SUFICIENTE", "a"]))
    assert isinstance(rag, RAG)
    assert set(load_technique("crag").keys()) == {"grade", "rewrite", "answer"}
