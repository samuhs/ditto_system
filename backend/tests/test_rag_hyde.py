"""Tests for HydeRAG."""
from app.core.prompts import load_technique
from app.core.rag.base import RAG, build_rag, rag_registry
from app.core.rag.hyde import HydeRAG


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
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self._responses.pop(0)


_DOCS = [{"text": "A praça central fica no centro.", "score": 0.9}]


def test_hyde_retrieves_with_hypothesis_not_raw_query():
    retriever = _RecordingRetriever(_DOCS)
    llm = _QueueLLM(["Hipotese: a praca central e o coracao da cidade.", "Resposta final."])
    rag = HydeRAG(retriever, llm)
    result = rag.answer("Onde fica o centro?")
    assert retriever.queries == ["Hipotese: a praca central e o coracao da cidade."]
    assert result.answer == "Resposta final."
    assert len(result.contexts) == 1


def test_hyde_registered_and_built():
    assert "hyde" in rag_registry.names()
    rag = build_rag("hyde", retriever=_RecordingRetriever(_DOCS), llm=_QueueLLM(["h", "a"]))
    assert isinstance(rag, RAG)


def test_hyde_prompts_have_expected_keys():
    assert set(load_technique("hyde").keys()) == {"hypothesis", "answer"}
