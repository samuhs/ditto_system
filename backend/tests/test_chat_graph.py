"""Hermetic tests for the conversation graph (fake LLM + fake RAG, no network)."""
from dataclasses import dataclass, field

from app.core.chat.graph import ChatConfigView, build_graph, run_flow
from app.core.chat.schemas import ChatMessage
from app.core.memory.manager import ModelManager
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
        return RAGResult(answer="rascunho do rag", contexts=[{"text": "ctx do doc", "score": 0.8}])


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


def _flow_deps(loads):
    def embedder_factory(name, **kw):
        loads.append(name)
        return object()

    @dataclass
    class _Deps:
        store: object = None
        llm_factory: object = staticmethod(lambda name: _FakeLLM())
        retriever_factory: object = staticmethod(lambda name, **kw: object())
        rag_factory: object = staticmethod(lambda name, **kw: _FakeRAG())
        models: object = field(
            default_factory=lambda: ModelManager(embedder_factory, max_local=1, is_local=lambda n: False)
        )

    return _Deps()


_CFG = ChatConfigView(base="viagem", chunking="recursive", embedding="gemini",
                      retriever="similarity", rag="naive", llm="gemini", persona="travel_guide")


def test_run_flow_wires_deps_and_returns_result():
    out = run_flow(_CFG, [ChatMessage(role="user", content="onde fica o centro?")], _flow_deps([]))
    assert out.answer == "RESPOSTA FINAL"
    assert out.contexts == ["ctx do doc"]


def test_run_flow_reuses_the_embedder_across_turns():
    loads = []
    deps = _flow_deps(loads)
    for _ in range(2):
        run_flow(_CFG, [ChatMessage(role="user", content="onde fica o centro?")], deps)
    assert loads == ["gemini"]


def test_chat_waits_briefly_for_a_model_slot():
    from contextlib import contextmanager

    from app.core.chat.graph import CHAT_WAIT_S

    seen = {}

    class _SpyModels:
        @contextmanager
        def acquire(self, name, device="auto", wait_timeout_s=None):
            seen["wait"] = wait_timeout_s
            yield object()

    deps = _flow_deps([])
    deps.models = _SpyModels()
    run_flow(_CFG, [ChatMessage(role="user", content="onde fica o centro?")], deps)
    assert seen["wait"] == CHAT_WAIT_S <= 5


def test_run_flow_reports_question_and_retrieval_signals():
    out = run_flow(_CFG, [ChatMessage(role="user", content="onde fica o centro?")], _flow_deps([]))
    assert out.difficulty["question"]["question_length"] == 3.0
    assert "mean_idf" not in out.difficulty["question"]  # no store: no corpus stats
    assert out.difficulty["retrieval"]["top_score"] == 0.8


def test_direct_turn_has_no_retrieval_signals():
    out = run_flow(_CFG, [ChatMessage(role="user", content="oi, tudo bem?")], _flow_deps([]))
    assert out.difficulty["retrieval"] == {} and out.difficulty["question"]
