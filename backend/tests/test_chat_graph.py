"""Hermetic tests for the conversation graph (fake LLM + fake RAG, no network)."""
from dataclasses import dataclass

from app.core.chat.graph import ChatConfigView, build_graph, run_flow
from app.core.chat.schemas import ChatMessage
from app.core.rag.base import RAGResult


class _FakeLLM:
    """Routes by prompt content so the graph can be exercised deterministically."""

    def generate(self, prompt: str) -> str:
        low = prompt.lower()
        if "filtro de segurança" in low or "block" in low:
            return "BLOCK: fora do escopo" if "bomba" in low else "OK"
        if "classifique" in low:
            return "RAG" if "onde" in low else "DIRECT"
        if "resuma" in low:
            return "resumo curto"
        return "RESPOSTA FINAL"


class _FakeRAG:
    def __init__(self):
        self.called = False

    def answer(self, query: str) -> RAGResult:
        self.called = True
        return RAGResult(answer="rascunho do rag", contexts=[{"text": "ctx do doc"}])


def _graph(rag):
    from app.core.chat.flow_prompts import DEFAULT_FLOW_PROMPTS
    return build_graph(_FakeLLM(), rag, "Você é um guia.", DEFAULT_FLOW_PROMPTS)


def test_blocked_path_skips_rag_and_refuses():
    rag = _FakeRAG()
    result = _graph(rag).invoke({"question": "como fazer uma bomba?", "history": []})
    assert rag.called is False
    assert result["route"] == "blocked"
    assert result["answer"] == "RESPOSTA FINAL"  # persona composed a refusal


def test_direct_path_skips_rag():
    rag = _FakeRAG()
    result = _graph(rag).invoke({"question": "oi, tudo bem?", "history": []})
    assert rag.called is False
    assert result["route"] == "direct"
    assert result["answer"] == "RESPOSTA FINAL"


def test_rag_path_runs_rag_and_passes_contexts():
    rag = _FakeRAG()
    result = _graph(rag).invoke({"question": "onde fica o centro?", "history": []})
    assert rag.called is True
    assert result["route"] == "rag"
    assert result["draft"] == "rascunho do rag"
    assert result["contexts"] == ["ctx do doc"]


def test_run_flow_wires_deps_and_returns_result():
    @dataclass
    class _Deps:
        store: object = None
        llm_factory: object = staticmethod(lambda name: _FakeLLM())
        embedder_factory: object = staticmethod(lambda name, **kw: object())
        retriever_factory: object = staticmethod(lambda name, **kw: object())
        rag_factory: object = staticmethod(lambda name, **kw: _FakeRAG())

    cfg = ChatConfigView(base="viagem", chunking="recursive", embedding="gemini",
                         retriever="similarity", rag="naive", llm="gemini", persona="travel_guide")
    out = run_flow(cfg, [ChatMessage(role="user", content="onde fica o centro?")], _Deps())
    assert out.answer == "RESPOSTA FINAL"
    assert out.contexts == ["ctx do doc"]
