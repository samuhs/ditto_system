# Fatia B1 — Conversa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um agente conversacional (LangGraph ReAct) com persona trocável e memória curta que consulta a RAG da Fatia A, com telas de configuração de chat e conversa, e persistência opcional de diálogos.

**Architecture:** Backend FastAPI: personas file-backed (reusa `backend/prompts/`), tabela `chat_config`, módulo `app/core/chat/` (agente ReAct via `create_react_agent`, tool de busca a partir do retriever, injeção de deps `ChatDeps`), rotas `/personas`, `/chat-configs`, `/chat` (stateless request-response), `/dialogues`. Frontend React+Mantine: telas de configuração de chat e de conversa.

**Tech Stack:** Python 3.11 (container) / 3.13 (venv), FastAPI, SQLAlchemy, **LangGraph** (`create_react_agent`), langchain-google-genai (`ChatGoogleGenerativeAI`), React+TS+Mantine+Vitest.

## Global Constraints

- Nova dependência **`langgraph>=0.2,<2.0`** em `backend/pyproject.toml` (pin `<2.0`: `create_react_agent` é removido na v2). Import: `from langgraph.prebuilt import create_react_agent`.
- Todo código, comentários e docstrings em **INGLÊS**; textos de UI em **PT-BR**.
- Testes de backend rodam de `backend/` com `.venv/bin/python -m pytest`; frontend com `cd frontend && npm run test -- --run`.
- Backend **stateless** no chat: o frontend envia o histórico a cada turno; nenhum estado de sessão no servidor.
- No chat, o **retriever é a tool**; o agente ReAct faz o papel do RAG (não usa naive/agentic).
- Persona = system prompt em arquivo `backend/prompts/personas/<nome>.md` (reusa `app.core.prompts.prompts_dir`); sem placeholders obrigatórios.
- Injeção de dependências via `ChatDeps` (estilo `ExperimentDeps`) para manter a suíte sem rede.
- Sem streaming no B1 (request-response).
- LLM default do agente: `gemini` → `ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")`.

---

## File Structure

- `backend/app/core/personas/__init__.py`, `loader.py` — personas file-backed.
- `backend/prompts/personas/travel_guide.md`, `assistant.md` — personas iniciais.
- `backend/app/core/db/models.py` — +`ChatConfig`, `Dialogue`, `DialogueMessage`.
- `backend/app/core/chat/__init__.py`, `schemas.py`, `agent.py`, `deps.py` — núcleo do chat.
- `backend/app/api/chat.py` — rotas; wire em `backend/app/main.py`.
- `backend/pyproject.toml` — dep langgraph.
- `frontend/src/api/types.ts`, `client.ts` — tipos + funções.
- `frontend/src/pages/ChatConfigsPage.tsx`, `ChatPage.tsx` — telas; rotas em `App.tsx`; nav em `Sidebar.tsx`.

---

### Task 1: Personas loader + arquivos

**Files:**
- Create: `backend/app/core/personas/__init__.py`
- Create: `backend/app/core/personas/loader.py`
- Create: `backend/prompts/personas/travel_guide.md`
- Create: `backend/prompts/personas/assistant.md`
- Test: `backend/tests/test_personas_loader.py`

**Interfaces:**
- Produces: `DEFAULT_PERSONAS: dict[str, str]`, `personas_dir() -> Path`, `list_personas() -> list[str]`, `load_persona(name: str) -> str` (raises `KeyError` for unknown).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_personas_loader.py`:

```python
"""Tests for the file-backed persona loader."""
import pytest

from app.core.personas import DEFAULT_PERSONAS, list_personas, load_persona


@pytest.fixture(autouse=True)
def personas_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return tmp_path / "personas"


def test_load_persona_falls_back_to_default():
    assert load_persona("travel_guide") == DEFAULT_PERSONAS["travel_guide"]


def test_list_personas_includes_defaults():
    assert "travel_guide" in list_personas()
    assert "assistant" in list_personas()


def test_list_personas_includes_files(personas_tmp):
    personas_tmp.mkdir(parents=True)
    (personas_tmp / "sac.md").write_text("Você é um atendente de SAC.", encoding="utf-8")
    names = list_personas()
    assert "sac" in names
    assert "travel_guide" in names  # defaults still present


def test_load_persona_reads_file(personas_tmp):
    personas_tmp.mkdir(parents=True)
    (personas_tmp / "travel_guide.md").write_text("CUSTOM guide", encoding="utf-8")
    assert load_persona("travel_guide") == "CUSTOM guide"


def test_unknown_persona_raises_keyerror():
    with pytest.raises(KeyError):
        load_persona("does_not_exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_personas_loader.py -v`
Expected: FAIL (ModuleNotFoundError: app.core.personas).

- [ ] **Step 3: Create the loader**

Create `backend/app/core/personas/loader.py`:

```python
"""File-backed persona system prompts with built-in defaults."""
from pathlib import Path

from app.core.prompts import prompts_dir

DEFAULT_PERSONAS: dict[str, str] = {
    "travel_guide": (
        "Você é um guia de viagem simpático e prestativo. Responda em português, "
        "de forma conversacional, ajudando o usuário a planejar e conhecer o destino. "
        "Sempre que precisar de informações específicas sobre o destino, use a "
        "ferramenta de busca disponível e baseie a resposta no que encontrar. "
        "Se não houver informação suficiente, diga o que sabe e seja honesto sobre limites."
    ),
    "assistant": (
        "Você é um assistente prestativo e objetivo. Responda em português. "
        "Use a ferramenta de busca para fundamentar respostas quando a pergunta "
        "depender de informações específicas do domínio."
    ),
}


def personas_dir() -> Path:
    """Directory holding persona .md files (under the shared prompts dir)."""
    return prompts_dir() / "personas"


def list_personas() -> list[str]:
    """Persona names: built-in defaults plus any .md files present."""
    names = set(DEFAULT_PERSONAS)
    directory = personas_dir()
    if directory.exists():
        names.update(p.stem for p in directory.glob("*.md"))
    return sorted(names)


def load_persona(name: str) -> str:
    """Return a persona's system prompt; file wins over default. KeyError if unknown."""
    path = personas_dir() / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").rstrip("\n")
    if name in DEFAULT_PERSONAS:
        return DEFAULT_PERSONAS[name]
    raise KeyError(f"unknown persona: {name}")
```

Create `backend/app/core/personas/__init__.py`:

```python
"""Persona management: file-backed system prompts with defaults."""
from app.core.personas.loader import (
    DEFAULT_PERSONAS,
    list_personas,
    load_persona,
    personas_dir,
)

__all__ = ["DEFAULT_PERSONAS", "list_personas", "load_persona", "personas_dir"]
```

- [ ] **Step 4: Create the persona files**

`backend/prompts/personas/travel_guide.md` — same text as `DEFAULT_PERSONAS["travel_guide"]`.
`backend/prompts/personas/assistant.md` — same text as `DEFAULT_PERSONAS["assistant"]`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_personas_loader.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/personas backend/prompts/personas backend/tests/test_personas_loader.py
git commit -m "feat: file-backed persona loader with travel_guide/assistant defaults"
```

---

### Task 2: DB models (chat_config, dialogue, dialogue_message)

**Files:**
- Modify: `backend/app/core/db/models.py`
- Test: `backend/tests/test_chat_models.py`

**Interfaces:**
- Produces SQLAlchemy models: `ChatConfig(id, name, base, chunking, embedding, retriever, llm, persona, created_at)`; `Dialogue(id, config_snapshot: dict, created_at, messages: list[DialogueMessage])`; `DialogueMessage(id, dialogue_id, role, content, position)`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_chat_models.py`:

```python
"""Tests for chat/dialogue models."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db.base import Base
from app.core.db.models import ChatConfig, Dialogue, DialogueMessage


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_chat_config_persists():
    s = _session()
    cfg = ChatConfig(
        name="viagem-gemini", base="viagem", chunking="recursive", embedding="gemini",
        retriever="similarity", llm="gemini", persona="travel_guide",
    )
    s.add(cfg)
    s.commit()
    assert s.get(ChatConfig, cfg.id).persona == "travel_guide"


def test_dialogue_with_messages_cascade():
    s = _session()
    d = Dialogue(config_snapshot={"base": "viagem"})
    d.messages = [
        DialogueMessage(role="user", content="Oi", position=0),
        DialogueMessage(role="assistant", content="Olá!", position=1),
    ]
    s.add(d)
    s.commit()
    stored = s.get(Dialogue, d.id)
    assert [m.content for m in sorted(stored.messages, key=lambda m: m.position)] == ["Oi", "Olá!"]
    s.delete(stored)
    s.commit()
    assert s.query(DialogueMessage).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_models.py -v`
Expected: FAIL (ImportError: cannot import ChatConfig).

- [ ] **Step 3: Add the models**

Append to `backend/app/core/db/models.py` (the file already imports `JSON, DateTime, ForeignKey, Integer, String, func` and `Mapped, mapped_column, relationship`):

```python
class ChatConfig(Base):
    """A saved chat configuration binding a collection + retriever + llm + persona."""

    __tablename__ = "chat_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    base: Mapped[str] = mapped_column(String(120))
    chunking: Mapped[str] = mapped_column(String(60))
    embedding: Mapped[str] = mapped_column(String(60))
    retriever: Mapped[str] = mapped_column(String(60))
    llm: Mapped[str] = mapped_column(String(60), default="gemini")
    persona: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Dialogue(Base):
    """A saved conversation, kept for later human evaluation."""

    __tablename__ = "dialogue"

    id: Mapped[int] = mapped_column(primary_key=True)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["DialogueMessage"]] = relationship(
        back_populates="dialogue", cascade="all, delete-orphan"
    )


class DialogueMessage(Base):
    """A single message within a saved dialogue."""

    __tablename__ = "dialogue_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    dialogue_id: Mapped[int] = mapped_column(ForeignKey("dialogue.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, default=0)

    dialogue: Mapped["Dialogue"] = relationship(back_populates="messages")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/db/models.py backend/tests/test_chat_models.py
git commit -m "feat: chat_config, dialogue and dialogue_message models"
```

---

### Task 3: Chat core (schemas, agent, deps) + langgraph dependency

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/core/chat/__init__.py`
- Create: `backend/app/core/chat/schemas.py`
- Create: `backend/app/core/chat/agent.py`
- Create: `backend/app/core/chat/deps.py`
- Test: `backend/tests/test_chat_agent.py`

**Interfaces:**
- Consumes: `build_embedder`, `build_retriever`, `collection_name`, `format_context`, `load_persona`, `QdrantStore`, `SessionLocal`.
- Produces:
  - `ChatMessage` (pydantic: `role: str`, `content: str`); `ChatTurnResult` (dataclass: `answer: str`, `contexts: list[str]`).
  - `build_chat_model(llm: str)` → langchain chat model (KeyError if unknown).
  - `build_retrieve_tool(retriever)` → a langchain tool.
  - `to_lc_messages(messages: list[ChatMessage]) -> list` (Human/AI messages).
  - `extract_turn(result: dict) -> ChatTurnResult`.
  - `run_agent(persona: str, retriever, chat_model, messages: list[ChatMessage]) -> ChatTurnResult`.
  - `ChatDeps` dataclass (store, session_factory, chat_model_factory=build_chat_model, embedder_factory=build_embedder, retriever_factory=build_retriever, agent_runner=run_agent).

- [ ] **Step 1: Add the langgraph dependency and install**

In `backend/pyproject.toml`, add to the `dependencies` list:

```
    "langgraph>=0.2,<2.0",
```

Then install into the dev venv:

Run: `cd backend && .venv/bin/pip install "langgraph>=0.2,<2.0"`
Expected: installs langgraph (already present at 1.2.7 is fine).

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_chat_agent.py`:

```python
"""Hermetic tests for the chat core (no network, no real model)."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.chat.agent import (
    build_retrieve_tool,
    extract_turn,
    to_lc_messages,
)
from app.core.chat.schemas import ChatMessage


class _StubRetriever:
    def retrieve(self, query: str) -> list[dict]:
        return [{"text": "The center is the main square.", "source_doc": "a.txt", "score": 0.9}]


def test_build_retrieve_tool_returns_formatted_context():
    tool = build_retrieve_tool(_StubRetriever())
    out = tool.invoke({"query": "where is the center?"})
    assert "main square" in out


class _BrokenRetriever:
    def retrieve(self, query: str) -> list[dict]:
        raise RuntimeError("collection missing")


def test_retrieve_tool_degrades_on_error():
    tool = build_retrieve_tool(_BrokenRetriever())
    out = tool.invoke({"query": "x"})
    assert isinstance(out, str) and out  # graceful message, no raise


def test_to_lc_messages_maps_roles():
    msgs = to_lc_messages([ChatMessage(role="user", content="oi"), ChatMessage(role="assistant", content="olá")])
    assert isinstance(msgs[0], HumanMessage) and msgs[0].content == "oi"
    assert isinstance(msgs[1], AIMessage) and msgs[1].content == "olá"


def test_extract_turn_pulls_reply_and_contexts():
    result = {"messages": [
        HumanMessage(content="oi"),
        ToolMessage(content="CTX one", tool_call_id="t1"),
        AIMessage(content="resposta final"),
    ]}
    turn = extract_turn(result)
    assert turn.answer == "resposta final"
    assert turn.contexts == ["CTX one"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_agent.py -v`
Expected: FAIL (ModuleNotFoundError: app.core.chat).

- [ ] **Step 4: Create schemas.py**

Create `backend/app/core/chat/schemas.py`:

```python
"""Schemas and result types for the conversational agent."""
from dataclasses import dataclass, field

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """One message in a conversation turn history."""

    role: str  # "user" | "assistant"
    content: str


@dataclass
class ChatTurnResult:
    """The agent's answer for one turn plus the contexts it retrieved."""

    answer: str
    contexts: list[str] = field(default_factory=list)
```

- [ ] **Step 5: Create agent.py**

Create `backend/app/core/chat/agent.py`:

```python
"""LangGraph ReAct conversational agent over a retriever tool."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.core.chat.schemas import ChatMessage, ChatTurnResult
from app.core.config.settings import get_settings
from app.core.rag.base import format_context

_CHAT_MODELS = {"gemini": "gemini-2.5-flash-lite"}


def build_chat_model(llm: str):
    """Return a tool-calling chat model for the given llm name. KeyError if unknown."""
    if llm not in _CHAT_MODELS:
        raise KeyError(f"unknown chat model: {llm}")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=_CHAT_MODELS[llm],
        google_api_key=get_settings().gemini_api_key,
    )


def build_retrieve_tool(retriever):
    """Build a search tool the agent can call; degrades to a message on failure."""

    @tool
    def retrieve(query: str) -> str:
        """Search the destination's documents for information relevant to the query."""
        try:
            contexts = retriever.retrieve(query)
        except Exception:  # noqa: BLE001  a retrieval failure must not crash the turn
            return "No information was found for this query."
        return format_context(contexts) or "No information was found for this query."

    return retrieve


def to_lc_messages(messages: list[ChatMessage]) -> list:
    """Convert our chat messages to LangChain Human/AI messages."""
    converted = []
    for m in messages:
        if m.role == "assistant":
            converted.append(AIMessage(content=m.content))
        else:
            converted.append(HumanMessage(content=m.content))
    return converted


def extract_turn(result: dict) -> ChatTurnResult:
    """Pull the final answer and any tool-retrieved contexts from an agent result."""
    messages = result.get("messages", [])
    contexts = [m.content for m in messages if isinstance(m, ToolMessage)]
    answer = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            answer = m.content if isinstance(m.content, str) else str(m.content)
            break
    return ChatTurnResult(answer=answer, contexts=contexts)


def run_agent(persona: str, retriever, chat_model, messages: list[ChatMessage]) -> ChatTurnResult:
    """Run one conversational turn through a ReAct agent and return the result."""
    agent = create_react_agent(chat_model, tools=[build_retrieve_tool(retriever)], prompt=persona)
    result = agent.invoke({"messages": to_lc_messages(messages)})
    return extract_turn(result)
```

- [ ] **Step 6: Create deps.py**

Create `backend/app/core/chat/deps.py`:

```python
"""Injectable dependencies for the chat service (overridable in tests)."""
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.chat.agent import build_chat_model, run_agent
from app.core.embedding.base import build_embedder
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore


@dataclass
class ChatDeps:
    """Dependencies for handling a chat turn / persisting dialogues."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    chat_model_factory: Callable = build_chat_model
    embedder_factory: Callable = build_embedder
    retriever_factory: Callable = build_retriever
    agent_runner: Callable = run_agent
```

Create `backend/app/core/chat/__init__.py`:

```python
"""Conversational agent package."""
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_agent.py -v`
Expected: PASS (4 passed).

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app/core/chat backend/tests/test_chat_agent.py
git commit -m "feat: chat core — ReAct agent, retrieve tool, deps injection (langgraph)"
```

---

### Task 4: Chat API endpoints

**Files:**
- Create: `backend/app/api/chat.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_chat_api.py`

**Interfaces:**
- Consumes: `ChatDeps`, `ChatMessage`, `ChatTurnResult`, `list_personas`, `load_persona`, `build_embedder`, `collection_name`, models `ChatConfig`/`Dialogue`/`DialogueMessage`, `SessionLocal`, `QdrantStore`.
- Produces routes: `GET /personas`, `POST/GET/DELETE /chat-configs`, `POST /chat`, `POST /dialogues`; dependency `get_chat_deps()`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_chat_api.py`:

```python
"""Tests for the chat endpoints (hermetic via injected fake agent)."""
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chat import get_chat_deps
from app.core.chat.deps import ChatDeps
from app.core.chat.schemas import ChatTurnResult
from app.core.db.base import Base
from app.core.vectorstore.qdrant import QdrantStore
from app.main import create_app


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    captured = {}

    def _fake_runner(persona, retriever, chat_model, messages):
        captured["persona"] = persona
        captured["messages"] = messages
        return ChatTurnResult(answer=f"echo: {messages[-1].content}", contexts=["CTX"])

    deps = ChatDeps(
        store=QdrantStore(client=QdrantClient(":memory:")),
        session_factory=session_factory,
        chat_model_factory=lambda name: object(),
        embedder_factory=lambda name, **kw: object(),
        retriever_factory=lambda name, **kw: object(),
        agent_runner=_fake_runner,
    )
    app = create_app()
    app.dependency_overrides[get_chat_deps] = lambda: deps
    c = TestClient(app)
    c.captured = captured
    return c


def _make_config(client, name="c1"):
    return client.post("/chat-configs", json={
        "name": name, "base": "viagem", "chunking": "recursive", "embedding": "gemini",
        "retriever": "similarity", "llm": "gemini", "persona": "travel_guide",
    })


def test_personas_lists_defaults(client):
    body = client.get("/personas").json()
    assert "travel_guide" in body["personas"]


def test_create_list_delete_chat_config(client):
    assert _make_config(client).status_code == 200
    assert _make_config(client).status_code == 409  # duplicate name
    listed = client.get("/chat-configs").json()
    assert any(c["name"] == "c1" for c in listed)
    cid = listed[0]["id"]
    assert client.delete(f"/chat-configs/{cid}").status_code == 200
    assert client.delete("/chat-configs/9999").status_code == 404


def test_chat_returns_reply_and_uses_persona(client):
    cid = _make_config(client).json()["id"]
    resp = client.post("/chat", json={"config_id": cid, "messages": [{"role": "user", "content": "Oi"}]})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "echo: Oi"
    assert client.captured["persona"].startswith("Você é um guia")


def test_chat_missing_config_404(client):
    resp = client.post("/chat", json={"config_id": 999, "messages": [{"role": "user", "content": "Oi"}]})
    assert resp.status_code == 404


def test_save_dialogue_persists_messages(client):
    cid = _make_config(client).json()["id"]
    resp = client.post("/dialogues", json={"config_id": cid, "messages": [
        {"role": "user", "content": "Oi"}, {"role": "assistant", "content": "Olá!"},
    ]})
    assert resp.status_code == 200
    did = resp.json()["id"]
    assert isinstance(did, int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_api.py -v`
Expected: FAIL (ImportError: app.api.chat).

- [ ] **Step 3: Create the router**

Create `backend/app/api/chat.py`:

```python
"""Endpoints for chat configs, conversation turns, and saving dialogues."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.core.chat.deps import ChatDeps
from app.core.chat.schemas import ChatMessage
from app.core.db.base import SessionLocal
from app.core.db.models import ChatConfig, Dialogue, DialogueMessage
from app.core.llm.base import build_llm
from app.core.personas import list_personas, load_persona
from app.core.vectorstore.qdrant import QdrantStore, collection_name

router = APIRouter()


def get_chat_deps() -> ChatDeps:
    """Production chat dependencies."""
    return ChatDeps(store=QdrantStore(), session_factory=SessionLocal)


class ChatConfigBody(BaseModel):
    name: str
    base: str
    chunking: str
    embedding: str
    retriever: str
    llm: str = "gemini"
    persona: str


class ChatTurnBody(BaseModel):
    config_id: int
    messages: list[ChatMessage]


@router.get("/personas")
def personas() -> dict:
    """List available persona names."""
    return {"personas": list_personas()}


@router.post("/chat-configs")
def create_chat_config(body: ChatConfigBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Create a saved chat configuration."""
    session = deps.session_factory()
    try:
        cfg = ChatConfig(**body.model_dump())
        session.add(cfg)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=f"chat config name already exists: {body.name}") from exc
        session.refresh(cfg)
        return {"id": cfg.id, "name": cfg.name}
    finally:
        session.close()


@router.get("/chat-configs")
def list_chat_configs(deps: ChatDeps = Depends(get_chat_deps)) -> list[dict]:
    """List saved chat configurations, most recent first."""
    session = deps.session_factory()
    try:
        rows = session.query(ChatConfig).order_by(ChatConfig.id.desc()).all()
        return [
            {
                "id": c.id, "name": c.name, "base": c.base, "chunking": c.chunking,
                "embedding": c.embedding, "retriever": c.retriever, "llm": c.llm, "persona": c.persona,
            }
            for c in rows
        ]
    finally:
        session.close()


@router.delete("/chat-configs/{config_id}")
def delete_chat_config(config_id: int, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Delete a chat configuration."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        session.delete(cfg)
        session.commit()
        return {"id": config_id, "deleted": True}
    finally:
        session.close()


def _build_chat_retriever(deps: ChatDeps, cfg: ChatConfig):
    """Build the retriever tool backend from a chat config."""
    embedder = deps.embedder_factory(cfg.embedding)
    col = collection_name(cfg.base, cfg.chunking, cfg.embedding)
    kwargs = {"store": deps.store, "collection": col, "embedder": embedder}
    if cfg.retriever == "multi_query":
        # multi_query uses the Fatia A LLM interface (.generate), not the chat model.
        kwargs["llm"] = build_llm(cfg.llm)
    return deps.retriever_factory(cfg.retriever, **kwargs)


@router.post("/chat")
def chat(body: ChatTurnBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Run one conversational turn (stateless: history is supplied by the caller)."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, body.config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        cfg_persona, cfg_llm = cfg.persona, cfg.llm
        retriever = _build_chat_retriever(deps, cfg)
    finally:
        session.close()
    try:
        persona_text = load_persona(cfg_persona)
        chat_model = deps.chat_model_factory(cfg_llm)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = deps.agent_runner(persona_text, retriever, chat_model, body.messages)
    return {"reply": result.answer, "contexts": result.contexts}


@router.post("/dialogues")
def save_dialogue(body: ChatTurnBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Persist a dialogue and its messages for later evaluation."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, body.config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        dialogue = Dialogue(config_snapshot={
            "name": cfg.name, "base": cfg.base, "chunking": cfg.chunking,
            "embedding": cfg.embedding, "retriever": cfg.retriever, "llm": cfg.llm, "persona": cfg.persona,
        })
        dialogue.messages = [
            DialogueMessage(role=m.role, content=m.content, position=i)
            for i, m in enumerate(body.messages)
        ]
        session.add(dialogue)
        session.commit()
        session.refresh(dialogue)
        return {"id": dialogue.id}
    finally:
        session.close()
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, update the import line to include `chat`:

```python
from app.api import chat, experiments, health, ingest, options, prompts
```

and add inside `create_app`, after the other `include_router` calls:

```python
    app.include_router(chat.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chat_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/chat.py backend/app/main.py backend/tests/test_chat_api.py
git commit -m "feat: chat API — personas, chat-configs CRUD, /chat turn, /dialogues save"
```

---

### Task 5: Frontend client + types

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces types: `ChatConfig`, `ChatConfigInput`, `ChatMessage`, `ChatTurn`; functions `getPersonas`, `listChatConfigs`, `createChatConfig`, `deleteChatConfig`, `sendChat`, `saveDialogue`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/api/client.test.ts` (inside `describe("api client", ...)`), and add the new functions to the import at the top of the file:

```typescript
  it("getPersonas fetches personas", async () => {
    const body = { personas: ["travel_guide", "assistant"] };
    vi.stubGlobal("fetch", mockFetchOnce(body));
    await expect(getPersonas()).resolves.toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/personas");
  });

  it("createChatConfig posts the config", async () => {
    const cfg = { name: "c1", base: "viagem", chunking: "recursive", embedding: "gemini", retriever: "similarity", llm: "gemini", persona: "travel_guide" };
    const fetchMock = mockFetchOnce({ id: 1, name: "c1" });
    vi.stubGlobal("fetch", fetchMock);
    await createChatConfig(cfg);
    expect(fetchMock).toHaveBeenCalledWith("/api/chat-configs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
  });

  it("sendChat posts config_id and messages", async () => {
    const fetchMock = mockFetchOnce({ reply: "olá", contexts: [] });
    vi.stubGlobal("fetch", fetchMock);
    await sendChat(1, [{ role: "user", content: "oi" }]);
    expect(fetchMock).toHaveBeenCalledWith("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config_id: 1, messages: [{ role: "user", content: "oi" }] }),
    });
  });

  it("saveDialogue posts the dialogue", async () => {
    const fetchMock = mockFetchOnce({ id: 7 });
    vi.stubGlobal("fetch", fetchMock);
    await saveDialogue(1, [{ role: "user", content: "oi" }]);
    expect(fetchMock).toHaveBeenCalledWith("/api/dialogues", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config_id: 1, messages: [{ role: "user", content: "oi" }] }),
    });
  });
```

Update the top import to include: `createChatConfig, getPersonas, saveDialogue, sendChat` (plus existing).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/api/client.test.ts`
Expected: FAIL (functions not exported).

- [ ] **Step 3: Add types**

In `frontend/src/api/types.ts`, add:

```typescript
export interface ChatConfig {
  id: number;
  name: string;
  base: string;
  chunking: string;
  embedding: string;
  retriever: string;
  llm: string;
  persona: string;
}

export type ChatConfigInput = Omit<ChatConfig, "id">;

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatTurn {
  reply: string;
  contexts: string[];
}
```

- [ ] **Step 4: Add client functions**

In `frontend/src/api/client.ts`, add to the type import: `ChatConfig`, `ChatConfigInput`, `ChatMessage`, `ChatTurn`. Then add:

```typescript
export async function getPersonas(): Promise<{ personas: string[] }> {
  return asJson(await fetch(`${BASE}/personas`));
}

export async function listChatConfigs(): Promise<ChatConfig[]> {
  return asJson<ChatConfig[]>(await fetch(`${BASE}/chat-configs`));
}

export async function createChatConfig(config: ChatConfigInput): Promise<{ id: number; name: string }> {
  return asJson(await fetch(`${BASE}/chat-configs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  }));
}

export async function deleteChatConfig(id: number): Promise<{ id: number; deleted: boolean }> {
  return asJson(await fetch(`${BASE}/chat-configs/${id}`, { method: "DELETE" }));
}

export async function sendChat(configId: number, messages: ChatMessage[]): Promise<ChatTurn> {
  return asJson<ChatTurn>(await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config_id: configId, messages }),
  }));
}

export async function saveDialogue(configId: number, messages: ChatMessage[]): Promise<{ id: number }> {
  return asJson(await fetch(`${BASE}/dialogues`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config_id: configId, messages }),
  }));
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/api/client.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(front): chat API client and types"
```

---

### Task 6: Chat configs page + route + nav

**Files:**
- Create: `frontend/src/pages/ChatConfigsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Test: `frontend/src/pages/ChatConfigsPage.test.tsx`

**Interfaces:**
- Consumes: `getOptions`, `getPersonas`, `listChatConfigs`, `createChatConfig`, `deleteChatConfig`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ChatConfigsPage.test.tsx`:

```typescript
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ChatConfigsPage } from "./ChatConfigsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <ChatConfigsPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.getOptions).mockResolvedValue({
    bases: ["viagem"], chunkings: ["recursive"], embeddings: ["gemini"], llms: ["gemini"],
    rags: ["naive"], retrievers: ["similarity"], metrics: ["rouge_l"],
  });
  vi.mocked(client.getPersonas).mockResolvedValue({ personas: ["travel_guide", "assistant"] });
  vi.mocked(client.listChatConfigs).mockResolvedValue([]);
  vi.mocked(client.createChatConfig).mockResolvedValue({ id: 1, name: "c1" });
});

describe("ChatConfigsPage", () => {
  it("loads options and personas", async () => {
    renderPage();
    expect(await screen.findByLabelText(/nome/i)).toBeInTheDocument();
  });

  it("creates a chat config", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/nome/i), "c1");
    await user.click(screen.getByRole("button", { name: /criar/i }));
    await waitFor(() => expect(client.createChatConfig).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/pages/ChatConfigsPage.test.tsx`
Expected: FAIL (ChatConfigsPage does not exist).

- [ ] **Step 3: Create the page**

Create `frontend/src/pages/ChatConfigsPage.tsx`:

```tsx
import { Alert, Button, Group, Select, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import {
  createChatConfig,
  deleteChatConfig,
  getOptions,
  getPersonas,
  listChatConfigs,
} from "../api/client";
import type { ChatConfig, Options } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function ChatConfigsPage() {
  const [options, setOptions] = useState<Options | null>(null);
  const [personas, setPersonas] = useState<string[]>([]);
  const [configs, setConfigs] = useState<ChatConfig[]>([]);
  const [name, setName] = useState("");
  const [base, setBase] = useState("");
  const [chunking, setChunking] = useState("");
  const [embedding, setEmbedding] = useState("");
  const [retriever, setRetriever] = useState("");
  const [llm, setLlm] = useState("gemini");
  const [persona, setPersona] = useState("travel_guide");
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listChatConfigs().then(setConfigs).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    getOptions().then(setOptions).catch((e) => setError(String(e)));
    getPersonas().then((p) => setPersonas(p.personas)).catch((e) => setError(String(e)));
    refresh();
  }, []);

  async function submit() {
    setError(null);
    try {
      await createChatConfig({ name, base, chunking, embedding, retriever, llm, persona });
      setName("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const canSubmit = name.trim() !== "" && base && chunking && embedding && retriever && persona;

  return (
    <div>
      <PageHeader
        eyebrow="Passo 04 · Conversar"
        title="Configurações de chat"
        subtitle="Crie uma configuração para o agente conversacional: qual base/coleção consultar, retriever, modelo e persona."
      />

      <div className="ditto-glass" style={{ padding: 30, maxWidth: 760 }}>
        <Stack gap="lg">
          <TextInput label="Nome" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <Group grow align="flex-start">
            <Select label="Base" data={options?.bases ?? []} value={base || null} onChange={(v) => setBase(v ?? "")} searchable />
            <Select label="Corte" data={options?.chunkings ?? []} value={chunking || null} onChange={(v) => setChunking(v ?? "")} searchable />
          </Group>
          <Group grow align="flex-start">
            <Select label="Embedding" data={options?.embeddings ?? []} value={embedding || null} onChange={(v) => setEmbedding(v ?? "")} searchable />
            <Select label="Retriever" data={options?.retrievers ?? []} value={retriever || null} onChange={(v) => setRetriever(v ?? "")} searchable />
          </Group>
          <Group grow align="flex-start">
            <Select label="Modelo (LLM)" data={options?.llms ?? []} value={llm || null} onChange={(v) => setLlm(v ?? "gemini")} searchable />
            <Select label="Persona" data={personas} value={persona || null} onChange={(v) => setPersona(v ?? "")} searchable />
          </Group>
          <Button
            onClick={submit}
            disabled={!canSubmit}
            size="md"
            variant="gradient"
            gradient={{ from: "#ab63f2", to: "#f26dcf", deg: 115 }}
            style={{ alignSelf: "flex-start" }}
          >
            Criar
          </Button>
        </Stack>
      </div>

      {error && (
        <Alert color="red" variant="light" title="Erro" mt="xl" radius="lg" maw={760}>
          {error}
        </Alert>
      )}

      <div className="ditto-exp-list" style={{ maxWidth: 760, marginTop: 24 }}>
        {configs.map((c) => (
          <div key={c.id} className="ditto-exp-row" style={{ cursor: "default" }}>
            <div>
              <Text fw={600} fz="sm">{c.name}</Text>
              <Text size="xs" c="dimmed">
                {c.base} · {c.chunking} · {c.embedding} · {c.retriever} · {c.persona}
              </Text>
            </div>
            <Button
              size="xs"
              variant="subtle"
              color="red"
              onClick={() => deleteChatConfig(c.id).then(refresh)}
            >
              Remover
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add the route and nav item**

In `frontend/src/App.tsx`, import the page and add a route after `/prompts`:

```tsx
import { ChatConfigsPage } from "./pages/ChatConfigsPage";
```

```tsx
                <Route
                  path="/chat-configs"
                  element={
                    <PageTransition>
                      <ChatConfigsPage />
                    </PageTransition>
                  }
                />
```

In `frontend/src/components/Sidebar.tsx`, add to the `NAV` array (reuse `FlaskIcon`, already imported):

```tsx
  { to: "/chat-configs", label: "Config. de chat", icon: <FlaskIcon /> },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run` (full suite; App.test.tsx must still pass with the new nav item).
Expected: PASS.

- [ ] **Step 6: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ChatConfigsPage.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx frontend/src/pages/ChatConfigsPage.test.tsx
git commit -m "feat(front): chat configs page"
```

---

### Task 7: Conversation page + route + nav

**Files:**
- Create: `frontend/src/pages/ChatPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/styles/global.css`
- Test: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: `listChatConfigs`, `sendChat`, `saveDialogue`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ChatPage.test.tsx`:

```typescript
import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { ChatPage } from "./ChatPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MantineProvider>
      <ChatPage />
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(client.listChatConfigs).mockResolvedValue([
    { id: 1, name: "c1", base: "viagem", chunking: "recursive", embedding: "gemini", retriever: "similarity", llm: "gemini", persona: "travel_guide" },
  ]);
  vi.mocked(client.sendChat).mockResolvedValue({ reply: "Olá! Sou seu guia.", contexts: [] });
  vi.mocked(client.saveDialogue).mockResolvedValue({ id: 5 });
});

describe("ChatPage", () => {
  it("sends a message and shows the reply", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/c1/); // config option loaded
    await user.type(screen.getByPlaceholderText(/mensagem/i), "Oi");
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(client.sendChat).toHaveBeenCalledWith(1, [{ role: "user", content: "Oi" }]));
    expect(await screen.findByText(/Sou seu guia/)).toBeInTheDocument();
  });

  it("saves the dialogue", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByText(/c1/);
    await user.type(screen.getByPlaceholderText(/mensagem/i), "Oi");
    await user.click(screen.getByRole("button", { name: /enviar/i }));
    await screen.findByText(/Sou seu guia/);
    await user.click(screen.getByRole("button", { name: /salvar di/i }));
    await waitFor(() => expect(client.saveDialogue).toHaveBeenCalledWith(1, [
      { role: "user", content: "Oi" },
      { role: "assistant", content: "Olá! Sou seu guia." },
    ]));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/pages/ChatPage.test.tsx`
Expected: FAIL (ChatPage does not exist).

- [ ] **Step 3: Create the page**

Create `frontend/src/pages/ChatPage.tsx`:

```tsx
import { Alert, Button, Group, Loader, Select, Text, TextInput } from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { listChatConfigs, saveDialogue, sendChat } from "../api/client";
import type { ChatConfig, ChatMessage } from "../api/types";
import { PageHeader } from "../components/PageHeader";

export function ChatPage() {
  const [configs, setConfigs] = useState<ChatConfig[]>([]);
  const [configId, setConfigId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listChatConfigs()
      .then((cs) => {
        setConfigs(cs);
        if (cs.length > 0) setConfigId(String(cs[0].id));
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function newConversation() {
    setMessages([]);
    setSaved(false);
    setError(null);
  }

  async function send() {
    if (!configId || input.trim() === "" || sending) return;
    setError(null);
    setSaved(false);
    const next = [...messages, { role: "user" as const, content: input.trim() }];
    setMessages(next);
    setInput("");
    setSending(true);
    try {
      const turn = await sendChat(Number(configId), next);
      setMessages([...next, { role: "assistant", content: turn.reply }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  async function save() {
    if (!configId || messages.length === 0) return;
    try {
      await saveDialogue(Number(configId), messages);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Passo 04 · Conversar"
        title="Conversa"
        subtitle="Escolha uma configuração e converse com o agente. Ao final, você pode salvar o diálogo para avaliação."
      />

      <Group mb="md" align="flex-end" gap="sm">
        <Select
          label="Configuração"
          data={configs.map((c) => ({ value: String(c.id), label: c.name }))}
          value={configId}
          onChange={setConfigId}
          w={280}
        />
        <Button variant="subtle" color="gray" size="sm" onClick={newConversation}>
          Nova conversa
        </Button>
        <Button
          variant="light"
          color="violet"
          size="sm"
          disabled={messages.length === 0}
          onClick={save}
        >
          Salvar diálogo
        </Button>
        {saved && <Text size="sm" c="#07f285">Diálogo salvo</Text>}
      </Group>

      <div className="ditto-glass ditto-chat-window">
        {messages.length === 0 && (
          <p className="ditto-empty">Sem mensagens ainda. Diga um "oi" para começar.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className="ditto-chat-msg" data-role={m.role}>
            <span className="ditto-chat-bubble">{m.content}</span>
          </div>
        ))}
        {sending && (
          <div className="ditto-chat-msg" data-role="assistant">
            <span className="ditto-chat-bubble"><Loader size="xs" color="#05dbf2" /></span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <Group mt="md" gap="sm">
        <TextInput
          placeholder="Sua mensagem…"
          value={input}
          onChange={(e) => setInput(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          style={{ flex: 1 }}
          disabled={!configId}
        />
        <Button onClick={send} loading={sending} disabled={!configId}>
          Enviar
        </Button>
      </Group>

      {error && (
        <Alert color="red" variant="light" title="Erro" mt="md" radius="lg">
          {error}
        </Alert>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Add chat CSS**

Append to `frontend/src/styles/global.css`:

```css
/* ---------- Chat window ---------- */
.ditto-chat-window {
  padding: 20px;
  min-height: 320px;
  max-height: 60vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ditto-chat-msg {
  display: flex;
}
.ditto-chat-msg[data-role="user"] {
  justify-content: flex-end;
}
.ditto-chat-bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 16px;
  line-height: 1.5;
  font-size: 0.92rem;
  background: var(--surface-strong);
  border: 1px solid var(--stroke);
  color: var(--text-hi);
  white-space: pre-wrap;
  word-break: break-word;
}
.ditto-chat-msg[data-role="user"] .ditto-chat-bubble {
  background: var(--grad-brand-soft);
  border-color: var(--stroke-strong);
}
```

- [ ] **Step 5: Add the route and nav item**

In `frontend/src/App.tsx`, import and add a route after `/chat-configs`:

```tsx
import { ChatPage } from "./pages/ChatPage";
```

```tsx
                <Route
                  path="/chat"
                  element={
                    <PageTransition>
                      <ChatPage />
                    </PageTransition>
                  }
                />
```

In `frontend/src/components/Sidebar.tsx`, add to `NAV` (reuse `FlaskIcon`):

```tsx
  { to: "/chat", label: "Conversa", icon: <FlaskIcon /> },
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run`
Expected: PASS (all suites).

- [ ] **Step 7: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx frontend/src/styles/global.css frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(front): conversation page with save-dialogue"
```

---

## Deploy (após todas as tasks)

```bash
cd /Users/samuelhenriquesilva/Desktop/doutorado/ditto_system
make front-build
docker compose up -d --build api frontend
```

A imagem da API instala `langgraph` automaticamente (dep no pyproject; Dockerfile faz `pip install .`). Confirme que nenhum experimento está `running` antes do rebuild da API. Teste ao vivo: crie uma config de chat sobre uma base já ingerida e converse.
