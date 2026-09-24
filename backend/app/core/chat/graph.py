"""LangGraph conversation flow: guardrail -> triage -> rag/direct -> memory -> persona."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.chat.flow_prompts import load_flow_prompts
from app.core.chat.schemas import ChatConfigView, ChatMessage, ChatTurnResult
from app.core.memory.device import resolve_embedding_device
from app.core.memory.profile import active_profile
from app.core.personas import load_persona
from app.core.vectorstore.qdrant import collection_name


class FlowState(TypedDict, total=False):
    """Mutable state threaded through the conversation graph."""

    question: str
    history: list[ChatMessage]
    route: str
    summary: str
    draft: str
    contexts: list[str]
    answer: str


def _format_history(history: list[ChatMessage]) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in history)


def build_graph(llm, rag, persona_text: str, prompts: dict[str, str]):
    """Compile the conversation StateGraph bound to a given llm/rag/persona/prompts."""

    def guardrail(state: FlowState) -> dict:
        out = llm.generate(prompts["guardrail"].format(question=state["question"])).strip()
        return {"route": "blocked"} if out.upper().startswith("BLOCK") else {}

    def triage(state: FlowState) -> dict:
        out = llm.generate(prompts["triage"].format(question=state["question"])).strip()
        return {"route": "rag" if out.upper().startswith("RAG") else "direct"}

    def rag_node(state: FlowState) -> dict:
        try:
            result = rag.answer(state["question"])
        except Exception:  # noqa: BLE001  a retrieval failure must not crash the turn
            return {"draft": "", "contexts": []}
        contexts = [c.get("text", "") for c in result.contexts]
        return {"draft": result.answer, "contexts": contexts}

    def memory(state: FlowState) -> dict:
        history = _format_history(state.get("history", []))
        if not history:
            return {"summary": ""}
        return {"summary": llm.generate(prompts["memory"].format(history=history)).strip()}

    def persona(state: FlowState) -> dict:
        if state.get("route") == "blocked":
            context = "(fora do escopo — recuse educadamente)"
        elif state.get("draft"):
            context = state["draft"]
        else:
            context = "(responda diretamente)"
        answer = llm.generate(
            prompts["persona_compose"].format(
                persona=persona_text,
                summary=state.get("summary", ""),
                context=context,
                question=state["question"],
            )
        ).strip()
        return {"answer": answer}

    graph = StateGraph(FlowState)
    graph.add_node("guardrail", guardrail)
    graph.add_node("triage", triage)
    graph.add_node("rag", rag_node)
    graph.add_node("memory", memory)
    graph.add_node("persona_compose", persona)

    graph.add_edge(START, "guardrail")
    graph.add_conditional_edges(
        "guardrail",
        lambda s: "blocked" if s.get("route") == "blocked" else "ok",
        {"blocked": "persona_compose", "ok": "triage"},
    )
    graph.add_conditional_edges(
        "triage",
        lambda s: s.get("route", "direct"),
        {"rag": "rag", "direct": "memory"},
    )
    graph.add_edge("rag", "memory")
    graph.add_edge("memory", "persona_compose")
    graph.add_edge("persona_compose", END)
    return graph.compile()


# A chat turn waits at most this long for a model slot held by an experiment,
# then loads beyond the limit instead of stalling the conversation.
CHAT_WAIT_S = 5.0


def run_flow(cfg: ChatConfigView, messages: list[ChatMessage], deps) -> ChatTurnResult:
    """Build the graph from a config snapshot and run one conversational turn."""
    llm = deps.llm_factory(cfg.llm)
    device = resolve_embedding_device(active_profile(), [cfg.llm])
    with deps.models.acquire(cfg.embedding, device, wait_timeout_s=CHAT_WAIT_S) as embedder:
        collection = collection_name(cfg.base, cfg.chunking, cfg.embedding)
        kwargs = {"store": deps.store, "collection": collection, "embedder": embedder}
        if cfg.retriever == "multi_query":
            kwargs["llm"] = llm
        retriever = deps.retriever_factory(cfg.retriever, **kwargs)
        rag = deps.rag_factory(cfg.rag, retriever=retriever, llm=llm)
        persona_text = load_persona(cfg.persona)
        graph = build_graph(llm, rag, persona_text, load_flow_prompts())
        question = messages[-1].content if messages else ""
        history = messages[:-1]
        result = graph.invoke({"question": question, "history": history})
    return ChatTurnResult(answer=result.get("answer", ""), contexts=result.get("contexts", []))
