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
    assert "gemini_api_key" not in body


def test_put_gemini_key_persists_and_never_exposes_raw(client):
    resp = client.put("/settings/gemini-key", json={"key": "secret"})
    assert resp.status_code == 200 and resp.json()["gemini_api_key_set"] is True
    assert client.get("/settings").json()["gemini_api_key_set"] is True
    assert "secret" not in client.get("/settings").text


def test_get_settings_empty_env_key_is_not_set(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config.settings import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        assert c.get("/settings").json()["gemini_api_key_set"] is False
    finally:
        get_settings.cache_clear()


def test_evaluation_settings_default_to_a_local_embedder(client):
    body = client.get("/settings/evaluation").json()
    assert body["eval_embedding"] == "paraphrase"
    embeddings = {e["name"]: e["local"] for e in body["embeddings"]}
    assert embeddings["gemini"] is False
    assert embeddings["paraphrase"] is True
    metrics = {m["name"]: m for m in body["metrics"]}
    assert metrics["rouge_l"]["uses_embedding"] is False
    assert metrics["answer_relevancy"]["uses_embedding"] is True
    assert metrics["answer_correctness"]["requires_reference"] is True


def test_put_eval_embedding_persists(client):
    resp = client.put("/settings/eval-embedding", json={"name": "gemini"})
    assert resp.status_code == 200 and resp.json() == {"eval_embedding": "gemini"}
    assert client.get("/settings/evaluation").json()["eval_embedding"] == "gemini"


def test_put_eval_embedding_rejects_unknown_name(client):
    resp = client.put("/settings/eval-embedding", json={"name": "nope"})
    assert resp.status_code == 422


def test_get_settings_includes_the_stall_limit_default(client):
    body = client.get("/settings").json()
    assert body["stall_limit_minutes"] == 10.0  # 600s default


def test_put_stall_limit_persists_in_minutes(client):
    resp = client.put("/settings/stall-limit", json={"minutes": 5})
    assert resp.status_code == 200 and resp.json() == {"stall_limit_minutes": 5.0}
    assert client.get("/settings").json()["stall_limit_minutes"] == 5.0

    from app.core.config.runtime import get_stall_limit_s

    assert get_stall_limit_s() == 300.0


def test_put_stall_limit_rejects_non_positive_minutes(client):
    resp = client.put("/settings/stall-limit", json={"minutes": 0})
    assert resp.status_code == 422
