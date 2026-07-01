"""Tests for the prompts endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return TestClient(create_app())


def test_list_prompts_returns_manifest_and_text(client):
    body = client.get("/prompts").json()
    assert "naive" in body
    assert "answer" in body["naive"]
    assert "{context}" in body["naive"]["answer"]["text"]
    assert "context" in body["naive"]["answer"]["required_placeholders"]


def test_update_prompt_persists_and_is_returned(client):
    new_text = "Answer with {context} and {question} now."
    resp = client.put("/prompts/naive/answer", json={"text": new_text})
    assert resp.status_code == 200
    assert client.get("/prompts").json()["naive"]["answer"]["text"] == new_text


def test_update_prompt_missing_placeholder_returns_422(client):
    resp = client.put("/prompts/naive/answer", json={"text": "no placeholders"})
    assert resp.status_code == 422


def test_update_unknown_prompt_returns_404(client):
    resp = client.put("/prompts/naive/nope", json={"text": "x"})
    assert resp.status_code == 404
