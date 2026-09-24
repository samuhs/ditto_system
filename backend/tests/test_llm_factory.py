"""Tests for resolve_llm and the dynamic /options llms."""
import pytest
from fastapi.testclient import TestClient

from app.api.options import get_ollama_lister, get_store
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


def test_resolve_llm_gemini_model_name(cfg_dir):
    llm = resolve_llm("gemini-2.5-flash-lite", client=object())
    assert isinstance(llm, GeminiLLM)


def test_resolve_llm_ollama_model_name(cfg_dir):
    llm = resolve_llm("qwen2.5:3b-instruct", client=object())
    assert isinstance(llm, OllamaLLM)


def _options(lister):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: _FakeStore()
    app.dependency_overrides[get_ollama_lister] = lambda: lister
    return TestClient(app).get("/options").json()


def test_options_lists_real_model_names_with_location(cfg_dir):
    runtime.set_ollama_models([{"id": "qwen", "model": "qwen2.5:3b-instruct"}], reserved=set())
    body = _options(lambda: ["qwen2.5:3b-instruct", "llama3.2:latest"])
    assert body["llm_options"] == [
        {"value": "gemini-2.5-flash-lite", "label": "gemini-2.5-flash-lite", "location": "remote"},
        {"value": "qwen2.5:3b-instruct", "label": "qwen2.5:3b-instruct", "location": "local"},
        {"value": "llama3.2:latest", "label": "llama3.2:latest", "location": "local"},
    ]
    assert body["llms"] == [o["value"] for o in body["llm_options"]]


def test_options_survives_ollama_outage(cfg_dir):
    def _down():
        raise ConnectionError("ollama down")

    body = _options(_down)
    assert body["llms"] == ["gemini-2.5-flash-lite"]
