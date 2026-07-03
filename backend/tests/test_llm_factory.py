"""Tests for resolve_llm and the dynamic /options llms."""
import pytest
from fastapi.testclient import TestClient

from app.api.options import get_store
from app.core.config import runtime
from app.core.llm.factory import resolve_llm
from app.core.llm.gemini import GeminiLLM
from app.core.llm.ollama import OllamaLLM
from app.main import create_app


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    return tmp_path


class _FakeStore:
    def list_collections(self):
        return []


def test_resolve_llm_named_ollama_model(cfg_dir):
    runtime.set_ollama_models([{"id": "qwen", "model": "qwen2.5:3b-instruct"}], reserved=set())
    llm = resolve_llm("qwen", client=object())
    assert isinstance(llm, OllamaLLM)


def test_resolve_llm_registry_name(cfg_dir):
    assert isinstance(resolve_llm("gemini", client=object()), GeminiLLM)


def test_resolve_llm_unknown_raises(cfg_dir):
    with pytest.raises(KeyError):
        resolve_llm("nope", client=object())


def test_options_llms_includes_named_models(cfg_dir):
    runtime.set_ollama_models([{"id": "qwen", "model": "qwen2.5:3b-instruct"}], reserved=set())
    app = create_app()
    app.dependency_overrides[get_store] = lambda: _FakeStore()
    client = TestClient(app)
    llms = client.get("/options").json()["llms"]
    assert "qwen" in llms
    assert "gemini" in llms
