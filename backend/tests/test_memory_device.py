"""Where local embedders run: never on the GPU a local LLM is using."""
import httpx
import pytest

from app.core.llm.factory import is_local_llm
from app.core.llm.ollama import local_llm_resident
from app.core.memory.device import resolve_embedding_device
from app.core.memory.profile import PROFILES

LOW, STANDARD = PROFILES["low"], PROFILES["standard"]


def _never_called():
    raise AssertionError("probe should not run")


@pytest.mark.parametrize(
    ("name", "local"),
    [("gemini", False), ("gemini-2.5-flash-lite", False), ("qwen3:1.7b", True),
     ("mlx-community/Qwen2.5-3B-Instruct-4bit", True), ("ollama", True), ("custom", True)],
)
def test_is_local_llm(name, local):
    assert is_local_llm(name) is local


def test_low_profile_is_always_cpu():
    assert resolve_embedding_device(LOW, ["gemini"], _never_called) == "cpu"


def test_standard_with_a_local_llm_is_cpu():
    assert resolve_embedding_device(STANDARD, ["gemini", "qwen3:1.7b"], _never_called) == "cpu"


def test_standard_with_remote_llm_and_idle_server_uses_gpu():
    assert resolve_embedding_device(STANDARD, ["gemini"], lambda: False) == "auto"


def test_standard_with_a_resident_local_model_is_cpu():
    assert resolve_embedding_device(STANDARD, [], lambda: True) == "cpu"


class _Resp:
    def __init__(self, status, payload=None, raw=False):
        self.status_code, self._payload, self._raw = status, payload, raw

    def json(self):
        if self._raw:
            raise ValueError("not json")
        return self._payload


def _fake_get(routes):
    def get(url, timeout):
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                return resp
        raise httpx.ConnectError("no route")
    return get


def test_ollama_with_loaded_models_is_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(200, {"models": [{"name": "q"}]})}))
    assert local_llm_resident("http://x/v1") is True


def test_ollama_with_nothing_loaded_is_not_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(200, {"models": []})}))
    assert local_llm_resident("http://x/v1") is False


def test_mlx_server_counts_as_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(404), "/v1/models": _Resp(200, {})}))
    assert local_llm_resident("http://x/v1") is True


def test_malformed_reply_counts_as_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(200, raw=True)}))
    assert local_llm_resident("http://x/v1") is True


def test_unreachable_server_is_not_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({}))
    assert local_llm_resident("http://x/v1") is False
