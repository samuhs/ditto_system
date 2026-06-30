"""Tests for AgenticRAG."""
from app.core.rag.agentic import AgenticRAG
from app.core.rag.base import RAGResult, rag_registry


class _StubRetriever:
    """Stub retriever that records queried strings."""

    def __init__(self) -> None:
        self.queries = []

    def retrieve(self, query: str) -> list[dict]:
        self.queries.append(query)
        return [{"text": f"context for {query}", "source_doc": "a.txt", "score": 0.5}]


class _ScriptedLLM:
    """Returns a queued list of responses, one per call."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return self._responses.pop(0)


def test_agentic_searches_then_answers():
    retriever = _StubRetriever()
    llm = _ScriptedLLM(["SEARCH: refined query", "ANSWER: final answer"])
    rag = AgenticRAG(retriever, llm, max_steps=3)
    result = rag.answer("original question")
    assert isinstance(result, RAGResult)
    assert result.answer == "final answer"
    assert retriever.queries == ["original question", "refined query"]
    assert len(result.contexts) == 2


def test_agentic_answers_immediately():
    retriever = _StubRetriever()
    llm = _ScriptedLLM(["ANSWER: quick answer"])
    rag = AgenticRAG(retriever, llm, max_steps=3)
    result = rag.answer("question")
    assert result.answer == "quick answer"
    assert retriever.queries == ["question"]


def test_agentic_stops_at_max_steps():
    retriever = _StubRetriever()
    llm = _ScriptedLLM(["SEARCH: a", "SEARCH: b", "final fallback answer"])
    rag = AgenticRAG(retriever, llm, max_steps=2)
    result = rag.answer("question")
    assert result.answer == "final fallback answer"
    assert len(retriever.queries) == 2


def test_agentic_unrecognized_response_becomes_answer():
    retriever = _StubRetriever()
    llm = _ScriptedLLM(["just a plain answer with no tag"])
    rag = AgenticRAG(retriever, llm, max_steps=3)
    result = rag.answer("question")
    assert result.answer == "just a plain answer with no tag"
    assert len(retriever.queries) == 1


def test_agentic_registered():
    assert "agentic" in rag_registry.names()
