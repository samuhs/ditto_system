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


def test_chat_unknown_retriever_returns_400():
    """A config whose retriever is unknown maps the registry KeyError to 400, not 500."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def _raising_retriever_factory(name, **kwargs):
        raise KeyError(f"retrieval '{name}' not found")

    deps = ChatDeps(
        store=QdrantStore(client=QdrantClient(":memory:")),
        session_factory=session_factory,
        chat_model_factory=lambda name: object(),
        embedder_factory=lambda name, **kw: object(),
        retriever_factory=_raising_retriever_factory,
    )
    app = create_app()
    app.dependency_overrides[get_chat_deps] = lambda: deps
    c = TestClient(app)
    cid = c.post("/chat-configs", json={
        "name": "bad", "base": "viagem", "chunking": "recursive", "embedding": "gemini",
        "retriever": "bogus", "llm": "gemini", "persona": "travel_guide",
    }).json()["id"]
    resp = c.post("/chat", json={"config_id": cid, "messages": [{"role": "user", "content": "Oi"}]})
    assert resp.status_code == 400


def test_create_config_persists_rag(client):
    resp = client.post("/chat-configs", json={
        "name": "with-rag", "base": "viagem", "chunking": "recursive", "embedding": "gemini",
        "retriever": "similarity", "rag": "naive", "llm": "gemini", "persona": "travel_guide",
    })
    assert resp.status_code == 200
    listed = client.get("/chat-configs").json()
    assert any(c["name"] == "with-rag" and c["rag"] == "naive" for c in listed)
