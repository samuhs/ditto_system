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
