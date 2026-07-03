"""Tests for the settings endpoints (hermetic, file-backed)."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.core.config.settings import get_settings

    get_settings.cache_clear()
    yield TestClient(create_app())
    get_settings.cache_clear()


def test_get_settings_masks_key(client):
    body = client.get("/settings").json()
    assert body["gemini_api_key_set"] is False
    assert body["ollama_models"] == []
    assert "gemini_api_key" not in body


def test_put_gemini_key_persists_and_never_exposes_raw(client):
    resp = client.put("/settings/gemini-key", json={"key": "secret"})
    assert resp.status_code == 200 and resp.json()["gemini_api_key_set"] is True
    assert client.get("/settings").json()["gemini_api_key_set"] is True
    assert "secret" not in client.get("/settings").text


def test_put_ollama_models_persists(client):
    resp = client.put(
        "/settings/ollama-models",
        json={"models": [{"id": "qwen", "model": "qwen2.5:3b-instruct"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["ollama_models"] == [{"id": "qwen", "model": "qwen2.5:3b-instruct"}]


def test_put_ollama_models_rejects_collision(client):
    resp = client.put("/settings/ollama-models", json={"models": [{"id": "gemini", "model": "x"}]})
    assert resp.status_code == 422
