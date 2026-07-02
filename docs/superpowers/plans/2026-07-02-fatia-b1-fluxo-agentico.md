# Fatia B1.1 — Fluxo agêntico multi-nó + visualização Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o agente ReAct do B1 por um grafo LangGraph multi-nó (guardrail → triagem → RAG/direto → memória → persona), com técnica de RAG selecionável e uma tela que desenha e permite editar o fluxo e as personas.

**Architecture:** Backend: `StateGraph` do LangGraph com nós customizados que chamam o LLM da Fatia A (`.generate`); o nó RAG usa `build_rag`. Prompts de nó file-backed em `prompts/conversation/`. `run_flow` substitui `run_agent`. Frontend: tela "Agente" com react-flow (aba Fluxo + aba Personas). Config de chat ganha campo `rag`.

**Tech Stack:** FastAPI, SQLAlchemy, **LangGraph `StateGraph`**, LLM da Fatia A (`build_llm`), React+TS+Mantine+Vitest, **@xyflow/react** (react-flow).

## Global Constraints

- Nós do LangGraph são funções customizadas — **não usam tool-calling**; cada nó chama `build_llm(name)` (interface `.generate(prompt) -> str`) da Fatia A; o nó RAG usa `build_rag(name, retriever=, llm=)`.
- `StateGraph` API: `from langgraph.graph import StateGraph, START, END`; `add_node`, `add_edge`, `add_conditional_edges(node, router, {label: target})`, `compile()`, `.invoke(state)`.
- Prompts de nó file-backed em `backend/prompts/conversation/<node>.md` (reusa `app.core.prompts.prompts_dir`), placeholders obrigatórios: `guardrail`→`{question}`, `triage`→`{question}`, `memory`→`{history}`, `persona_compose`→`{persona}`,`{question}` (também disponíveis `{summary}`,`{context}`).
- Ids dos nós (usados em FlowState/FLOW_SPEC/flow_prompts/endpoints): `guardrail`, `triage`, `rag`, `memory`, `persona_compose`.
- `ChatConfig` ganha coluna `rag` (default `"naive"`); deploy roda `ALTER TABLE chat_config ADD COLUMN IF NOT EXISTS rag VARCHAR(60) DEFAULT 'naive';`.
- Todo código/comentários/docstrings em INGLÊS; UI e conteúdo de prompts em PT-BR.
- Backend tests de `backend/` com `.venv/bin/python -m pytest`; frontend `cd frontend && npm run test -- --run`.
- DI via `ChatDeps` mantém a suíte sem rede; o grafo é testável com um LLM fake (nós customizados não exigem `bind_tools`).
- Nova dep front **`@xyflow/react`**; import CSS `@xyflow/react/dist/style.css`.

---

## File Structure

- `backend/app/core/chat/flow_prompts.py` — manifesto + defaults + load/save de prompts de nó.
- `backend/prompts/conversation/{guardrail,triage,memory,persona_compose}.md` — prompts iniciais.
- `backend/app/core/chat/graph.py` — `FlowState`, funções de nó, `build_graph`, `run_flow`.
- `backend/app/core/chat/schemas.py` — +`ChatConfigView`.
- `backend/app/core/chat/deps.py` — `ChatDeps` reescrito (llm/rag/embedder/retriever factories + `agent_runner=run_flow`).
- `backend/app/core/chat/agent.py` — **removido** (ReAct).
- `backend/app/core/personas/loader.py` — +`save_persona`.
- `backend/app/core/db/models.py` — `ChatConfig` +`rag`.
- `backend/app/api/chat.py` — `/chat` usa run_flow; +`FLOW_SPEC`, `GET/PUT /chat/flow`, `GET/PUT /personas/{name}`.
- `frontend/src/api/{types,client}.ts` — tipos/funções do flow+persona; `rag` em ChatConfig.
- `frontend/src/pages/AgentePage.tsx` — react-flow + abas; rota em `App.tsx`; nav em `Sidebar.tsx`.
- `frontend/src/pages/ChatConfigsPage.tsx` — select de RAG.
- `frontend/package.json` — `@xyflow/react`.

---

### Task 1: Loader de prompts de nó (flow_prompts) + arquivos

**Files:**
- Create: `backend/app/core/chat/flow_prompts.py`
- Create: `backend/prompts/conversation/guardrail.md`, `triage.md`, `memory.md`, `persona_compose.md`
- Test: `backend/tests/test_flow_prompts.py`

**Interfaces:**
- Consumes: `app.core.prompts.prompts_dir`.
- Produces: `FLOW_PROMPT_SPECS: dict[str,set[str]]`, `DEFAULT_FLOW_PROMPTS: dict[str,str]`, `conversation_dir() -> Path`, `load_flow_prompt(node) -> str`, `load_flow_prompts() -> dict[str,str]`, `validate_flow_placeholders(node, text)`, `save_flow_prompt(node, text)`; nó desconhecido → `KeyError`, placeholder faltando → `ValueError`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_flow_prompts.py`:

```python
"""Tests for the conversation node prompt loader."""
import pytest

from app.core.chat.flow_prompts import (
    DEFAULT_FLOW_PROMPTS,
    FLOW_PROMPT_SPECS,
    load_flow_prompt,
    load_flow_prompts,
    save_flow_prompt,
    validate_flow_placeholders,
)


@pytest.fixture(autouse=True)
def prompts_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return tmp_path / "conversation"


def test_load_falls_back_to_default():
    assert load_flow_prompt("triage") == DEFAULT_FLOW_PROMPTS["triage"]


def test_load_all_covers_manifest():
    assert set(load_flow_prompts()) == set(FLOW_PROMPT_SPECS)


def test_save_then_load_roundtrip(prompts_tmp):
    text = "Classifique: responda RAG ou DIRECT. Mensagem: {question}"
    save_flow_prompt("triage", text)
    assert (prompts_tmp / "triage.md").exists()
    assert load_flow_prompt("triage") == text


def test_validate_requires_mandatory_placeholder():
    validate_flow_placeholders("memory", "Resumo de {history} extra {foo}")
    with pytest.raises(ValueError, match="history"):
        validate_flow_placeholders("memory", "sem placeholder")


def test_save_rejects_missing_placeholder():
    with pytest.raises(ValueError):
        save_flow_prompt("persona_compose", "só {persona} sem question")


def test_unknown_node_raises_keyerror():
    with pytest.raises(KeyError):
        load_flow_prompt("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_flow_prompts.py -v`
Expected: FAIL (ModuleNotFoundError: app.core.chat.flow_prompts).

- [ ] **Step 3: Create flow_prompts.py**

Create `backend/app/core/chat/flow_prompts.py`:

```python
"""File-backed prompts for the conversation graph nodes, with defaults + validation."""
import re
from pathlib import Path

from app.core.prompts import prompts_dir

FLOW_PROMPT_SPECS: dict[str, set[str]] = {
    "guardrail": {"question"},
    "triage": {"question"},
    "memory": {"history"},
    "persona_compose": {"persona", "question"},
}

DEFAULT_FLOW_PROMPTS: dict[str, str] = {
    "guardrail": (
        "Você é um filtro de segurança e escopo de um assistente conversacional. "
        "Responda APENAS com 'OK' se a mensagem for apropriada e dentro do escopo, "
        "ou 'BLOCK: <motivo>' se for insegura ou claramente fora do escopo.\n\n"
        "Mensagem: {question}"
    ),
    "triage": (
        "Classifique a mensagem do usuário. Responda APENAS com uma palavra:\n"
        "'RAG' se responder bem exige buscar informação no material do domínio, ou\n"
        "'DIRECT' se é saudação/conversa/algo respondível sem buscar.\n\n"
        "Mensagem: {question}"
    ),
    "memory": (
        "Resuma em poucas frases o histórico de conversa abaixo, mantendo o que "
        "importa para continuar o diálogo. Se estiver vazio, responda com vazio.\n\n"
        "Histórico:\n{history}"
    ),
    "persona_compose": (
        "{persona}\n\n"
        "Resumo da conversa até aqui: {summary}\n\n"
        "Informação de apoio: {context}\n\n"
        "Responda à mensagem do usuário na sua persona, de forma natural e útil.\n\n"
        "Mensagem: {question}"
    ),
}

_PLACEHOLDER_RE = re.compile(r"{(\w+)}")


def conversation_dir() -> Path:
    """Directory holding conversation node prompt files."""
    return prompts_dir() / "conversation"


def _check_known(node: str) -> None:
    if node not in FLOW_PROMPT_SPECS:
        raise KeyError(f"unknown flow node: {node}")


def load_flow_prompt(node: str) -> str:
    """Read a node prompt's .md; fall back to the built-in default when absent."""
    _check_known(node)
    path = conversation_dir() / f"{node}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").rstrip("\n")
    return DEFAULT_FLOW_PROMPTS[node]


def load_flow_prompts() -> dict[str, str]:
    """All node prompts in the manifest."""
    return {node: load_flow_prompt(node) for node in FLOW_PROMPT_SPECS}


def validate_flow_placeholders(node: str, text: str) -> None:
    """Raise ValueError if a required placeholder is missing from text."""
    _check_known(node)
    present = set(_PLACEHOLDER_RE.findall(text))
    missing = FLOW_PROMPT_SPECS[node] - present
    if missing:
        raise ValueError(
            f"flow prompt {node} missing required placeholder(s): "
            + ", ".join("{" + m + "}" for m in sorted(missing))
        )


def save_flow_prompt(node: str, text: str) -> None:
    """Validate placeholders and write the node prompt's .md file."""
    _check_known(node)
    validate_flow_placeholders(node, text)
    path = conversation_dir() / f"{node}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
```

- [ ] **Step 4: Create the .md files**

Create each file with the same text as the corresponding `DEFAULT_FLOW_PROMPTS` entry:
`backend/prompts/conversation/guardrail.md`, `triage.md`, `memory.md`, `persona_compose.md`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_flow_prompts.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/chat/flow_prompts.py backend/prompts/conversation backend/tests/test_flow_prompts.py
git commit -m "feat: file-backed conversation node prompts (guardrail/triage/memory/persona)"
```

---

### Task 2: Campo `rag` na ChatConfig

**Files:**
- Modify: `backend/app/core/db/models.py`
- Modify: `backend/app/api/chat.py` (body `ChatConfigBody` + list return)
- Test: `backend/tests/test_chat_models.py` (append), `backend/tests/test_chat_api.py` (append)

**Interfaces:**
- Produces: `ChatConfig.rag: Mapped[str]` (default `"naive"`); `ChatConfigBody.rag: str`; list endpoint returns `rag`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_chat_models.py`:

```python
def test_chat_config_has_rag_field():
    from app.core.db.models import ChatConfig
    s = _session()
    cfg = ChatConfig(
        name="c-rag", base="viagem", chunking="recursive", embedding="gemini",
        retriever="similarity", rag="agentic", llm="gemini", persona="travel_guide",
    )
    s.add(cfg)
    s.commit()
    assert s.get(ChatConfig, cfg.id).rag == "agentic"
```

Append to `backend/tests/test_chat_api.py` (inside, reusing the `client` fixture and `_make_config`; note `_make_config` will be updated in Step 3 to send `rag`):

```python
def test_create_config_persists_rag(client):
    resp = client.post("/chat-configs", json={
        "name": "with-rag", "base": "viagem", "chunking": "recursive", "embedding": "gemini",
        "retriever": "similarity", "rag": "naive", "llm": "gemini", "persona": "travel_guide",
    })
    assert resp.status_code == 200
    listed = client.get("/chat-configs").json()
    assert any(c["name"] == "with-rag" and c["rag"] == "naive" for c in listed)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_models.py::test_chat_config_has_rag_field tests/test_chat_api.py::test_create_config_persists_rag -v`
Expected: FAIL (`rag` is an invalid keyword / not returned).

- [ ] **Step 3: Add the column + body + list field**

In `backend/app/core/db/models.py`, inside `class ChatConfig`, add after the `retriever` column:

```python
    rag: Mapped[str] = mapped_column(String(60), default="naive")
```

In `backend/app/api/chat.py`, in `class ChatConfigBody`, add the field (after `retriever`):

```python
    rag: str = "naive"
```

In `create_chat_config`, `ChatConfig(**body.model_dump())` already includes `rag` (no change). In `list_chat_configs`, add `"rag": c.rag,` to each returned dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_models.py tests/test_chat_api.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/db/models.py backend/app/api/chat.py backend/tests/test_chat_models.py backend/tests/test_chat_api.py
git commit -m "feat: add rag technique field to chat_config"
```

---

### Task 3: Grafo do fluxo (StateGraph + nós + run_flow) + ChatConfigView

**Files:**
- Create: `backend/app/core/chat/graph.py`
- Modify: `backend/app/core/chat/schemas.py` (+`ChatConfigView`)
- Test: `backend/tests/test_chat_graph.py`

**Interfaces:**
- Consumes: `flow_prompts.load_flow_prompts`, `personas.load_persona`, `rag.base.format_context`, `vectorstore.qdrant.collection_name`, `schemas.ChatMessage`/`ChatTurnResult`.
- Produces:
  - `ChatConfigView` dataclass: `base, chunking, embedding, retriever, rag, llm, persona` (all str).
  - `FlowState` TypedDict (keys: `question, history, route, summary, draft, contexts, answer`).
  - `build_graph(llm, rag, persona_text: str, prompts: dict[str,str])` → compiled graph.
  - `run_flow(cfg: ChatConfigView, messages: list[ChatMessage], deps) -> ChatTurnResult` (deps duck-typed: has `store`, `llm_factory`, `embedder_factory`, `retriever_factory`, `rag_factory`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chat_graph.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_graph.py -v`
Expected: FAIL (ModuleNotFoundError: app.core.chat.graph).

- [ ] **Step 3: Add ChatConfigView to schemas.py**

Append to `backend/app/core/chat/schemas.py`:

```python
@dataclass
class ChatConfigView:
    """Plain snapshot of a chat config, decoupled from the ORM."""

    base: str
    chunking: str
    embedding: str
    retriever: str
    rag: str
    llm: str
    persona: str
```

- [ ] **Step 4: Create graph.py**

Create `backend/app/core/chat/graph.py`:

```python
"""LangGraph conversation flow: guardrail -> triage -> rag/direct -> memory -> persona."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.chat.flow_prompts import load_flow_prompts
from app.core.chat.schemas import ChatConfigView, ChatMessage, ChatTurnResult
from app.core.personas import load_persona
from app.core.rag.base import format_context
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


def run_flow(cfg: ChatConfigView, messages: list[ChatMessage], deps) -> ChatTurnResult:
    """Build the graph from a config snapshot and run one conversational turn."""
    llm = deps.llm_factory(cfg.llm)
    embedder = deps.embedder_factory(cfg.embedding)
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
```

The imports block is exactly as shown above (no `format_context`; the rag node reads `result.contexts` directly via `c.get("text","")`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_graph.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/chat/graph.py backend/app/core/chat/schemas.py backend/tests/test_chat_graph.py
git commit -m "feat: LangGraph conversation flow (guardrail/triage/rag/memory/persona)"
```

---

### Task 4: Ligar o grafo — deps + /chat + remover ReAct

**Files:**
- Modify: `backend/app/core/chat/deps.py`
- Delete: `backend/app/core/chat/agent.py`
- Modify: `backend/app/api/chat.py` (`/chat` route)
- Modify: `backend/tests/test_chat_api.py` (fixture + affected tests)

**Interfaces:**
- Consumes: `run_flow` (Task 3), `build_llm`/`build_embedder`/`build_retriever`/`build_rag`, `ChatConfigView`.
- Produces: `ChatDeps` with fields `store, session_factory, llm_factory=build_llm, embedder_factory=build_embedder, retriever_factory=build_retriever, rag_factory=build_rag, agent_runner=run_flow`. `/chat` calls `deps.agent_runner(view, body.messages, deps)`.

- [ ] **Step 1: Update the test fixture and tests (RED)**

In `backend/tests/test_chat_api.py`, replace the `client` fixture's deps construction and fake runner so the runner takes `(cfg_view, messages, deps)`:

```python
    def _fake_runner(cfg, messages, deps):
        captured["persona"] = cfg.persona
        captured["messages"] = messages
        return ChatTurnResult(answer=f"echo: {messages[-1].content}", contexts=["CTX"])

    deps = ChatDeps(
        store=QdrantStore(client=QdrantClient(":memory:")),
        session_factory=session_factory,
        agent_runner=_fake_runner,
    )
```

Update `test_chat_returns_reply_and_uses_persona` assertion `client.captured["persona"]` to expect `"travel_guide"` (the fake now captures `cfg.persona`, the persona NAME, not its text):

```python
    assert client.captured["persona"] == "travel_guide"
```

Replace `test_chat_unknown_retriever_returns_400` with a runner that raises KeyError:

```python
def test_chat_unknown_config_value_returns_400():
    """A KeyError from run_flow (unknown llm/rag/retriever/persona) maps to 400."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def _raising_runner(cfg, messages, deps):
        raise KeyError("unknown rag 'bogus'")

    deps = ChatDeps(
        store=QdrantStore(client=QdrantClient(":memory:")),
        session_factory=session_factory,
        agent_runner=_raising_runner,
    )
    app = create_app()
    app.dependency_overrides[get_chat_deps] = lambda: deps
    c = TestClient(app)
    cid = c.post("/chat-configs", json={
        "name": "x", "base": "viagem", "chunking": "recursive", "embedding": "gemini",
        "retriever": "similarity", "rag": "naive", "llm": "gemini", "persona": "travel_guide",
    }).json()["id"]
    resp = c.post("/chat", json={"config_id": cid, "messages": [{"role": "user", "content": "Oi"}]})
    assert resp.status_code == 400
```

Also update `_make_config` to include `"rag": "naive"` (if not already from Task 2).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_api.py -v`
Expected: FAIL (ChatDeps still requires chat_model_factory / agent_runner signature mismatch / run_agent import).

- [ ] **Step 3: Rewrite deps.py**

Replace `backend/app/core/chat/deps.py` with:

```python
"""Injectable dependencies for the chat service (overridable in tests)."""
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.chat.graph import run_flow
from app.core.embedding.base import build_embedder
from app.core.llm.base import build_llm
from app.core.rag.base import build_rag
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore


@dataclass
class ChatDeps:
    """Dependencies for handling a chat turn / persisting dialogues."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    llm_factory: Callable = build_llm
    embedder_factory: Callable = build_embedder
    retriever_factory: Callable = build_retriever
    rag_factory: Callable = build_rag
    agent_runner: Callable = run_flow
```

- [ ] **Step 4: Delete the ReAct agent**

```bash
git rm backend/app/core/chat/agent.py
```

(If any test imported from `app.core.chat.agent`, it was replaced by `graph`/`flow_prompts` tests; `test_chat_agent.py` from B1 must be removed too:)

```bash
git rm backend/tests/test_chat_agent.py
```

- [ ] **Step 5: Rewrite the /chat route**

In `backend/app/api/chat.py`: remove the `_build_chat_retriever` helper and the `build_llm` import if now unused (it moved into `graph.run_flow`). Add import `from app.core.chat.schemas import ChatConfigView` (alongside the existing `ChatMessage` import). Replace the `chat` handler body with:

```python
@router.post("/chat")
def chat(body: ChatTurnBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Run one conversational turn (stateless: history is supplied by the caller)."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, body.config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        view = ChatConfigView(
            base=cfg.base, chunking=cfg.chunking, embedding=cfg.embedding,
            retriever=cfg.retriever, rag=cfg.rag, llm=cfg.llm, persona=cfg.persona,
        )
    finally:
        session.close()
    try:
        result = deps.agent_runner(view, body.messages, deps)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"reply": result.answer, "contexts": result.contexts}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_api.py -v`
Expected: PASS (all, including the updated 400 test).

- [ ] **Step 7: Full backend suite (no regressions)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/chat/deps.py backend/app/api/chat.py backend/tests/test_chat_api.py
git rm backend/app/core/chat/agent.py backend/tests/test_chat_agent.py
git commit -m "feat: wire conversation graph into /chat; remove ReAct agent"
```

---

### Task 5: Endpoints do fluxo e edição de persona

**Files:**
- Modify: `backend/app/core/personas/loader.py` (+`save_persona`), `backend/app/core/personas/__init__.py` (export)
- Modify: `backend/app/api/chat.py` (FLOW_SPEC + endpoints)
- Test: `backend/tests/test_chat_flow_api.py`

**Interfaces:**
- Consumes: `flow_prompts` (load/save/validate + FLOW_PROMPT_SPECS), `personas` (load/save/list).
- Produces: `save_persona(name, text)`; routes `GET /chat/flow`, `PUT /chat/flow/{node}`, `GET /personas/{name}`, `PUT /personas/{name}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chat_flow_api.py`:

```python
"""Tests for the flow-visualization and persona-edit endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return TestClient(create_app())


def test_get_flow_returns_nodes_and_edges(client):
    body = client.get("/chat/flow").json()
    ids = {n["id"] for n in body["nodes"]}
    assert {"guardrail", "triage", "rag", "memory", "persona_compose"} <= ids
    assert body["edges"]
    triage = next(n for n in body["nodes"] if n["id"] == "triage")
    assert triage["type"] == "prompt"
    assert "{question}" in triage["prompt"]
    assert "question" in triage["required_placeholders"]
    rag = next(n for n in body["nodes"] if n["id"] == "rag")
    assert rag["type"] == "rag"


def test_put_flow_prompt_persists(client):
    new = "Classifique: RAG ou DIRECT. Mensagem: {question}"
    assert client.put("/chat/flow/triage", json={"text": new}).status_code == 200
    body = client.get("/chat/flow").json()
    assert next(n for n in body["nodes"] if n["id"] == "triage")["prompt"] == new


def test_put_flow_prompt_missing_placeholder_422(client):
    assert client.put("/chat/flow/triage", json={"text": "sem placeholder"}).status_code == 422


def test_put_flow_unknown_node_404(client):
    assert client.put("/chat/flow/nope", json={"text": "x"}).status_code == 404


def test_get_and_put_persona(client):
    body = client.get("/personas/travel_guide").json()
    assert body["name"] == "travel_guide"
    assert body["text"]
    assert client.put("/personas/travel_guide", json={"text": "Novo guia"}).status_code == 200
    assert client.get("/personas/travel_guide").json()["text"] == "Novo guia"


def test_get_unknown_persona_404(client):
    assert client.get("/personas/nope").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_flow_api.py -v`
Expected: FAIL (routes/endpoints missing).

- [ ] **Step 3: Add save_persona**

In `backend/app/core/personas/loader.py`, add:

```python
import re

_VALID_NAME = re.compile(r"^[\w-]+$")


def save_persona(name: str, text: str) -> None:
    """Write a persona's .md file. Raises ValueError for an invalid name."""
    if not _VALID_NAME.match(name):
        raise ValueError(f"invalid persona name: {name}")
    path = personas_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
```

In `backend/app/core/personas/__init__.py`, add `save_persona` to the imports and `__all__`.

- [ ] **Step 4: Add FLOW_SPEC + endpoints to chat.py**

In `backend/app/api/chat.py`, add imports:

```python
from app.core.chat.flow_prompts import (
    FLOW_PROMPT_SPECS,
    load_flow_prompt,
    save_flow_prompt,
)
from app.core.personas import load_persona, save_persona  # extend existing personas import
```

Add the static flow description near the top (after `router = APIRouter()`):

```python
# Static description of the conversation graph (structure is fixed in code).
_FLOW_NODES = [
    ("guardrail", "Guardrail", "prompt", "Verifica se a mensagem é segura e no escopo."),
    ("triage", "Triagem", "prompt", "Decide se a resposta precisa de busca (RAG) ou é direta."),
    ("rag", "RAG", "rag", "Executa a técnica de RAG escolhida na config."),
    ("memory", "Memória", "prompt", "Resume o histórico para manter a memória curta."),
    ("persona_compose", "Persona", "prompt", "Compõe a resposta final na voz da persona."),
]
_FLOW_EDGES = [
    ("guardrail", "triage", "ok"),
    ("guardrail", "persona_compose", "bloqueado"),
    ("triage", "rag", "precisa de conhecimento"),
    ("triage", "memory", "direto"),
    ("rag", "memory", ""),
    ("memory", "persona_compose", ""),
]
```

Add a body model (next to the others):

```python
class PromptBody(BaseModel):
    text: str
```

Add the endpoints:

```python
@router.get("/chat/flow")
def get_flow() -> dict:
    """Return the static conversation graph plus each prompt node's current prompt."""
    nodes = []
    for node_id, label, ntype, description in _FLOW_NODES:
        node = {"id": node_id, "label": label, "type": ntype, "description": description}
        if ntype == "prompt":
            node["prompt"] = load_flow_prompt(node_id)
            node["required_placeholders"] = sorted(FLOW_PROMPT_SPECS[node_id])
        nodes.append(node)
    edges = [{"source": s, "target": t, "label": lbl} for s, t, lbl in _FLOW_EDGES]
    return {"nodes": nodes, "edges": edges}


@router.put("/chat/flow/{node}")
def update_flow_prompt(node: str, body: PromptBody) -> dict:
    """Validate placeholders and persist a node prompt."""
    if node not in FLOW_PROMPT_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown flow node: {node}")
    try:
        save_flow_prompt(node, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"node": node, "text": body.text}


@router.get("/personas/{name}")
def get_persona(name: str) -> dict:
    """Return a persona's text."""
    try:
        text = load_persona(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {name}") from exc
    return {"name": name, "text": text}


@router.put("/personas/{name}")
def update_persona(name: str, body: PromptBody) -> dict:
    """Persist a persona's text (creates it if the name is new and valid)."""
    try:
        save_persona(name, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": name, "text": body.text}
```

(The existing `from app.core.personas import list_personas, load_persona` line: extend it to also import `save_persona`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_flow_api.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/personas backend/app/api/chat.py backend/tests/test_chat_flow_api.py
git commit -m "feat: flow-visualization endpoints + persona editing"
```

---

### Task 6: Frontend — cliente/tipos do fluxo e persona + dep react-flow

**Files:**
- Modify: `frontend/package.json` (+`@xyflow/react`)
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces types: `FlowNode` (`id, label, type, description, prompt?, required_placeholders?`), `FlowEdge` (`source, target, label`), `FlowSpec` (`nodes: FlowNode[], edges: FlowEdge[]`), `Persona` (`name, text`); add `rag: string` to `ChatConfig`. Functions: `getFlow`, `saveFlowPrompt(node, text)`, `getPersona(name)`, `savePersona(name, text)`.

- [ ] **Step 1: Add the dependency**

Run: `cd frontend && npm install @xyflow/react`
Expected: `@xyflow/react` added to `package.json` dependencies.

- [ ] **Step 2: Write the failing tests**

Append to `frontend/src/api/client.test.ts` (and add the new fns to the top import):

```typescript
  it("getFlow fetches the flow spec", async () => {
    const body = { nodes: [{ id: "triage", label: "Triagem", type: "prompt", description: "d", prompt: "{question}", required_placeholders: ["question"] }], edges: [] };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getFlow()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/chat/flow");
  });

  it("saveFlowPrompt PUTs the node prompt", async () => {
    const fetchMock = mockFetchOnce({ node: "triage", text: "t {question}" });
    vi.stubGlobal("fetch", fetchMock);
    await saveFlowPrompt("triage", "t {question}");
    expect(fetchMock).toHaveBeenCalledWith("/api/chat/flow/triage", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "t {question}" }),
    });
  });

  it("getPersona fetches a persona", async () => {
    const fetchMock = mockFetchOnce({ name: "travel_guide", text: "guia" });
    vi.stubGlobal("fetch", fetchMock);
    await getPersona("travel_guide");
    expect(fetchMock).toHaveBeenCalledWith("/api/personas/travel_guide");
  });

  it("savePersona PUTs the persona text", async () => {
    const fetchMock = mockFetchOnce({ name: "travel_guide", text: "novo" });
    vi.stubGlobal("fetch", fetchMock);
    await savePersona("travel_guide", "novo");
    expect(fetchMock).toHaveBeenCalledWith("/api/personas/travel_guide", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "novo" }),
    });
  });
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/api/client.test.ts`
Expected: FAIL (functions not exported).

- [ ] **Step 4: Add types**

In `frontend/src/api/types.ts`, add `rag: string;` to the `ChatConfig` interface (after `retriever`), and add:

```typescript
export interface FlowNode {
  id: string;
  label: string;
  type: "prompt" | "rag";
  description: string;
  prompt?: string;
  required_placeholders?: string[];
}

export interface FlowEdge {
  source: string;
  target: string;
  label: string;
}

export interface FlowSpec {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface Persona {
  name: string;
  text: string;
}
```

- [ ] **Step 5: Add client functions**

In `frontend/src/api/client.ts`, extend the type import with `FlowSpec, Persona`, and add:

```typescript
export async function getFlow(): Promise<FlowSpec> {
  return asJson<FlowSpec>(await fetch(`${BASE}/chat/flow`));
}

export async function saveFlowPrompt(node: string, text: string): Promise<{ node: string; text: string }> {
  return asJson(await fetch(`${BASE}/chat/flow/${node}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
  }));
}

export async function getPersona(name: string): Promise<Persona> {
  return asJson<Persona>(await fetch(`${BASE}/personas/${name}`));
}

export async function savePersona(name: string, text: string): Promise<Persona> {
  return asJson<Persona>(await fetch(`${BASE}/personas/${name}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
  }));
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/api/client.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(front): flow + persona API client, types, and @xyflow/react dep"
```

---

### Task 7: Frontend — select de RAG na config de chat

**Files:**
- Modify: `frontend/src/pages/ChatConfigsPage.tsx`
- Test: `frontend/src/pages/ChatConfigsPage.test.tsx` (append)

**Interfaces:**
- Consumes: `getOptions` (`.rags`), `createChatConfig` (body now includes `rag`).

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/ChatConfigsPage.test.tsx`:

```typescript
  it("includes rag in the created config", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome/i), "c-rag");
    await user.click(screen.getByRole("button", { name: /criar/i }));
    await waitFor(() =>
      expect(client.createChatConfig).toHaveBeenCalledWith(
        expect.objectContaining({ rag: expect.any(String) }),
      ),
    );
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/pages/ChatConfigsPage.test.tsx`
Expected: FAIL (`rag` not in the created config).

- [ ] **Step 3: Add the RAG select + state**

In `frontend/src/pages/ChatConfigsPage.tsx`: add state `const [rag, setRag] = useState("");`; in the options-load `useEffect`, when options load, auto-select the first rag (mirror the existing auto-select: `if (opts.rags.length > 0) setRag(opts.rags[0]);`); add `rag` to the `createChatConfig({ ... })` call; add `rag` to the `canSubmit` guard; and add a `Select` in the form (next to Retriever):

```tsx
            <Select label="RAG" data={options?.rags ?? []} value={rag || null} onChange={(v) => setRag(v ?? "")} searchable />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run src/pages/ChatConfigsPage.test.tsx`
Expected: PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatConfigsPage.tsx frontend/src/pages/ChatConfigsPage.test.tsx
git commit -m "feat(front): choose RAG technique in chat config"
```

---

### Task 8: Frontend — tela "Agente" (react-flow + personas)

**Files:**
- Create: `frontend/src/pages/AgentePage.tsx`
- Modify: `frontend/src/App.tsx` (route), `frontend/src/components/Sidebar.tsx` (nav), `frontend/src/styles/global.css` (flow styling)
- Test: `frontend/src/pages/AgentePage.test.tsx`

**Interfaces:**
- Consumes: `getFlow`, `saveFlowPrompt`, `getPersonas`, `getPersona`, `savePersona`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/AgentePage.test.tsx`:

```typescript
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { AgentePage } from "./AgentePage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <AgentePage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getFlow).mockResolvedValue({
    nodes: [
      { id: "triage", label: "Triagem", type: "prompt", description: "d", prompt: "Mensagem: {question}", required_placeholders: ["question"] },
      { id: "rag", label: "RAG", type: "rag", description: "usa a técnica" },
    ],
    edges: [{ source: "triage", target: "rag", label: "precisa" }],
  });
  vi.mocked(client.getPersonas).mockResolvedValue({ personas: ["travel_guide"] });
  vi.mocked(client.getPersona).mockResolvedValue({ name: "travel_guide", text: "guia" });
  vi.mocked(client.savePersona).mockResolvedValue({ name: "travel_guide", text: "novo" });
  vi.mocked(client.saveFlowPrompt).mockResolvedValue({ node: "triage", text: "x" });
});

describe("AgentePage", () => {
  it("loads and renders flow nodes", async () => {
    renderPage();
    expect(await screen.findByText("Triagem")).toBeInTheDocument();
    expect(await screen.findByText("RAG")).toBeInTheDocument();
  });

  it("edits and saves a persona in the Personas tab", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: /personas/i }));
    const area = await screen.findByDisplayValue("guia");
    await user.clear(area);
    await user.type(area, "novo");
    await user.click(screen.getByRole("button", { name: /salvar persona/i }));
    await waitFor(() => expect(client.savePersona).toHaveBeenCalledWith("travel_guide", "novo"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/pages/AgentePage.test.tsx`
Expected: FAIL (AgentePage does not exist).

- [ ] **Step 3: Create AgentePage**

Create `frontend/src/pages/AgentePage.tsx`:

```tsx
import { Alert, Button, Group, Select, Stack, Tabs, Text, Textarea } from "@mantine/core";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";

import {
  getFlow,
  getPersona,
  getPersonas,
  saveFlowPrompt,
  savePersona,
} from "../api/client";
import type { FlowNode, FlowSpec } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function toReactFlow(spec: FlowSpec): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = spec.nodes.map((n, i) => ({
    id: n.id,
    position: { x: (i % 2) * 240, y: i * 110 },
    data: { label: `${n.label}` },
    style: {
      border: "1px solid var(--stroke-strong)",
      background: "var(--surface-strong)",
      color: "var(--text-hi)",
      borderRadius: 12,
      padding: 8,
      fontSize: 12,
    },
  }));
  const edges: Edge[] = spec.edges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
  }));
  return { nodes, edges };
}

export function AgentePage() {
  const [spec, setSpec] = useState<FlowSpec | null>(null);
  const [selected, setSelected] = useState<FlowNode | null>(null);
  const [promptDraft, setPromptDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [personas, setPersonas] = useState<string[]>([]);
  const [personaName, setPersonaName] = useState<string | null>(null);
  const [personaText, setPersonaText] = useState("");
  const [personaSaved, setPersonaSaved] = useState(false);

  useEffect(() => {
    getFlow().then(setSpec).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getPersonas().then((p) => setPersonas(p.personas)).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!personaName) return;
    getPersona(personaName).then((p) => setPersonaText(p.text)).catch((e) => setError(String(e)));
  }, [personaName]);

  const graph = useMemo(() => (spec ? toReactFlow(spec) : { nodes: [], edges: [] }), [spec]);

  function pickNode(id: string) {
    const node = spec?.nodes.find((n) => n.id === id) ?? null;
    setSelected(node);
    setSaved(false);
    setPromptDraft(node?.prompt ?? "");
  }

  async function savePrompt() {
    if (!selected || selected.type !== "prompt") return;
    setError(null);
    try {
      await saveFlowPrompt(selected.id, promptDraft);
      setSaved(true);
      setSpec((s) => s && { ...s, nodes: s.nodes.map((n) => (n.id === selected.id ? { ...n, prompt: promptDraft } : n)) });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function doSavePersona() {
    if (!personaName) return;
    setError(null);
    try {
      await savePersona(personaName, personaText);
      setPersonaSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 04 · Conversar"
        title="Agente"
        subtitle="Visualize o fluxo do agente conversacional e edite o prompt de cada etapa, ou ajuste as personas."
      />

      {error && (
        <Alert color="red" variant="light" title="Erro" mb="md" radius="lg" maw={860}>
          {error}
        </Alert>
      )}

      <Tabs defaultValue="flow">
        <Tabs.List>
          <Tabs.Tab value="flow">Fluxo do agente</Tabs.Tab>
          <Tabs.Tab value="personas">Personas</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="flow" pt="md">
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 480px", height: 460 }} className="ditto-glass">
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                onNodeClick={(_e, node) => pickNode(node.id)}
                fitView
              >
                <Background />
                <Controls />
              </ReactFlow>
            </div>
            <div style={{ flex: "1 1 320px" }}>
              {!selected && <Text c="dimmed" size="sm">Clique num nó para ver/editar o prompt.</Text>}
              {selected && selected.type === "rag" && (
                <Alert color="violet" variant="light" radius="lg" title={selected.label}>
                  {selected.description} O prompt depende da técnica escolhida na config — edite em Prompts.
                </Alert>
              )}
              {selected && selected.type === "prompt" && (
                <Stack gap="sm">
                  <Text fw={700}>{selected.label}</Text>
                  <Text size="xs" c="dimmed">{selected.description}</Text>
                  <Textarea
                    autosize
                    minRows={6}
                    value={promptDraft}
                    onChange={(e) => setPromptDraft(e.currentTarget.value)}
                    styles={{ input: { fontFamily: "var(--font-mono)", fontSize: "0.82rem" } }}
                  />
                  <Text size="xs" c="dimmed">
                    Placeholders obrigatórios: {(selected.required_placeholders ?? []).map((p) => `{${p}}`).join(", ")}
                  </Text>
                  <Group>
                    <Button size="xs" variant="light" color="violet" onClick={savePrompt}>Salvar prompt</Button>
                    {saved && <Text size="xs" c="#07f285">Prompt salvo</Text>}
                  </Group>
                </Stack>
              )}
            </div>
          </div>
        </Tabs.Panel>

        <Tabs.Panel value="personas" pt="md">
          <Stack gap="sm" maw={760}>
            <Select
              label="Persona"
              data={personas}
              value={personaName}
              onChange={(v) => { setPersonaName(v); setPersonaSaved(false); }}
              placeholder="Selecione uma persona"
            />
            {personaName && (
              <>
                <Textarea
                  autosize
                  minRows={8}
                  value={personaText}
                  onChange={(e) => { setPersonaText(e.currentTarget.value); setPersonaSaved(false); }}
                  styles={{ input: { fontFamily: "var(--font-mono)", fontSize: "0.82rem" } }}
                />
                <Group>
                  <Button size="xs" variant="light" color="violet" onClick={doSavePersona}>Salvar persona</Button>
                  {personaSaved && <Text size="xs" c="#07f285">Persona salva</Text>}
                </Group>
              </>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 4: Add route and nav**

In `frontend/src/App.tsx`, import `AgentePage` and add a route after `/chat`:

```tsx
                <Route
                  path="/agente"
                  element={
                    <PageTransition>
                      <AgentePage />
                    </PageTransition>
                  }
                />
```

In `frontend/src/components/Sidebar.tsx`, add to `NAV` (reuse `FlaskIcon`):

```tsx
  { to: "/agente", label: "Agente", icon: <FlaskIcon /> },
```

- [ ] **Step 5: Add flow styling**

Append to `frontend/src/styles/global.css`:

```css
/* ---------- Agent flow (react-flow) ---------- */
.react-flow__attribution { display: none; }
.react-flow__controls button {
  background: var(--surface-strong);
  border-color: var(--stroke);
  color: var(--text-hi);
}
```

- [ ] **Step 6: Run tests + build**

Run: `cd frontend && npm run test -- --run`
Expected: PASS (all suites, incl. App.test.tsx with the new nav item and the 2 new AgentePage tests). If react-flow needs `ResizeObserver` (already stubbed in the test setup) it will render node labels as text.

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/AgentePage.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx frontend/src/styles/global.css frontend/src/pages/AgentePage.test.tsx
git commit -m "feat(front): Agente page — react-flow graph + node prompt & persona editing"
```

---

## Deploy (após todas as tasks)

```bash
cd /Users/samuelhenriquesilva/Desktop/doutorado/ditto_system
# migração: adiciona a coluna rag em instalações onde chat_config já existe
docker compose exec postgres psql -U ditto -d ditto -c "ALTER TABLE chat_config ADD COLUMN IF NOT EXISTS rag VARCHAR(60) DEFAULT 'naive';"
make front-build
docker compose up -d --build api frontend
```

A imagem da API instala `langgraph` (já no pyproject). Confirme que nenhum experimento está `running` antes do rebuild. Teste ao vivo: crie uma config de chat (agora com RAG), converse, e abra a tela "Agente" para ver/editar o fluxo e as personas.
