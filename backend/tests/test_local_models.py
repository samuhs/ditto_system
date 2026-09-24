"""Listing models on the local LLM server: Ollama's /api/tags or OpenAI's /v1/models."""
import httpx
import pytest

from app.core.llm import ollama


class _Resp:
    def __init__(self, status: int, payload: dict) -> None:
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self) -> dict:
        return self._payload


def _fake_get(routes: dict):
    def get(url, timeout):
        return routes.get(url, _Resp(404, {}))
    return get


def test_lists_ollama_models_from_api_tags(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({
        "http://srv:11434/api/tags": _Resp(200, {"models": [{"name": "qwen2.5:3b-instruct"}]}),
    }))
    assert ollama.list_ollama_models("http://srv:11434/v1") == ["qwen2.5:3b-instruct"]


def test_falls_back_to_openai_models_endpoint(monkeypatch):
    # MLX / llama.cpp servers have no /api/tags but list models at /v1/models.
    monkeypatch.setattr(httpx, "get", _fake_get({
        "http://host:11436/v1/models": _Resp(200, {"data": [{"id": "mlx-community/Qwen2.5-3B-Instruct-4bit"}]}),
    }))
    assert ollama.list_ollama_models("http://host:11436/v1") == ["mlx-community/Qwen2.5-3B-Instruct-4bit"]


def test_raises_when_the_server_is_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({}))
    with pytest.raises(httpx.HTTPStatusError):
        ollama.list_ollama_models("http://nowhere:1/v1")
