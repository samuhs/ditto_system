"""Tests for LLM names, providers, resolve_llm, /options and the provider endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.api.options import get_ollama_lister, get_store
from app.core.config import runtime
from app.core.llm import providers
from app.core.llm.chat_model import ChatModelLLM
from app.core.llm.factory import is_local_llm, resolve_llm
from app.main import create_app


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    from app.core.config.settings import get_settings

    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("ENV_FILE", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()  # no key from the project .env leaks into the test
    yield tmp_path
    get_settings.cache_clear()


class _FakeStore:
    def list_collections(self):
        return []


OPENROUTER = {"kind": "custom", "base_url": "https://openrouter.ai/api/v1", "api_key": "sk-test",
              "models": ["qwen/qwen3.5-9b", "z-ai/glm-5.3-flash"],
              "params": {"extra_body": {"reasoning": {"enabled": False}}}}


@pytest.mark.parametrize("name, provider_id, model", [
    ("gemini", "gemini", providers.DEFAULT_GEMINI_MODEL),
    ("gemini-2.5-flash-lite", "gemini", "gemini-2.5-flash-lite"),
    ("qwen2.5:3b-instruct", "local", "qwen2.5:3b-instruct"),
    ("mlx-community/Qwen2.5-3B-Instruct-4bit", "local", "mlx-community/Qwen2.5-3B-Instruct-4bit"),
])
def test_bare_names_keep_their_old_meaning(cfg_dir, name, provider_id, model):
    provider, resolved = providers.split_llm_name(name)
    assert (provider.id, resolved) == (provider_id, model)


def test_a_provider_name_selects_a_configured_provider(cfg_dir):
    providers.save_provider("openrouter", OPENROUTER)
    provider, model = providers.split_llm_name("openrouter::qwen/qwen3.5-9b")
    assert provider.id == "openrouter" and model == "qwen/qwen3.5-9b"
    assert provider.resolved_key() == "sk-test"


def test_unknown_names_raise(cfg_dir):
    with pytest.raises(KeyError):
        resolve_llm("nope", client=object())
    with pytest.raises(KeyError):
        resolve_llm("missing::model", client=object())


def test_resolve_llm_builds_the_one_generic_llm(cfg_dir):
    assert isinstance(resolve_llm("qwen3:1.7b", client=object()), ChatModelLLM)
    providers.save_provider("openrouter", OPENROUTER)
    assert isinstance(resolve_llm("openrouter::qwen/qwen3.5-9b", client=object()), ChatModelLLM)


def test_the_local_server_keeps_max_tokens_in_the_body_and_the_settings_url(cfg_dir):
    llm = resolve_llm("qwen3:1.7b", temperature=0, max_tokens=256, timeout=12.5)
    client = llm._client
    assert client.extra_body == {"max_tokens": 256}
    assert client.request_timeout == 12.5
    assert client.temperature == 0


def test_resolve_llm_forwards_the_timeout_to_gemini(cfg_dir):
    runtime.set_gemini_key("test-key")
    assert resolve_llm("gemini-2.5-flash-lite", timeout=12.5)._client.timeout == 12.5


def test_without_a_timeout_the_client_default_stays(cfg_dir):
    assert resolve_llm("qwen3:1.7b")._client.request_timeout is None


def test_locality_follows_the_provider(cfg_dir):
    providers.save_provider("openrouter", OPENROUTER)
    providers.save_provider("lab", {"kind": "custom", "base_url": "http://gpu:8000/v1", "local": True})
    assert is_local_llm("mlx-community/Qwen2.5-3B-Instruct-4bit") is True
    assert is_local_llm("gemini-2.5-flash-lite") is False
    assert is_local_llm("openrouter::qwen/qwen3.5-9b") is False
    assert is_local_llm("lab::any") is True
    assert is_local_llm("missing::model") is True  # unknown: conservative


@pytest.mark.parametrize("provider_id, data, message", [
    ("Bad Id", {"kind": "custom", "base_url": "http://h/v1"}, "id"),
    ("local", {"kind": "custom", "base_url": "http://h/v1"}, "reservado"),
    ("x", {"kind": ""}, "tipo"),
    ("x", {"kind": "custom"}, "base_url"),
    ("x", {"kind": "openai", "params": {"api_key": "k"}}, "params"),
    ("x", {"kind": "openai", "models": ["a::b"]}, "::"),
])
def test_invalid_providers_are_refused(cfg_dir, provider_id, data, message):
    with pytest.raises(ValueError, match=message):
        providers.save_provider(provider_id, data)


def test_saving_without_a_key_keeps_the_stored_one_and_empty_clears_it(cfg_dir):
    providers.save_provider("openrouter", OPENROUTER)
    providers.save_provider("openrouter", {**OPENROUTER, "api_key": None, "models": ["m"]})
    assert providers.get_provider("openrouter").resolved_key() == "sk-test"
    providers.save_provider("openrouter", {**OPENROUTER, "api_key": ""})
    assert providers.get_provider("openrouter").resolved_key() is None


def _client(lister=lambda: []):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: _FakeStore()
    app.dependency_overrides[get_ollama_lister] = lambda: lister
    return TestClient(app)


def test_options_lists_gemini_providers_and_the_local_server(cfg_dir):
    runtime.set_gemini_key("test-key")
    providers.save_provider("openrouter", OPENROUTER)
    body = _client(lambda: ["qwen2.5:3b-instruct"]).get("/options").json()
    assert body["llm_options"] == [
        {"value": "gemini-2.5-flash-lite", "label": "gemini-2.5-flash-lite", "location": "remote"},
        {"value": "openrouter::qwen/qwen3.5-9b", "label": "qwen/qwen3.5-9b (openrouter)", "location": "remote"},
        {"value": "openrouter::z-ai/glm-5.3-flash", "label": "z-ai/glm-5.3-flash (openrouter)", "location": "remote"},
        {"value": "qwen2.5:3b-instruct", "label": "qwen2.5:3b-instruct", "location": "local"},
    ]


def test_options_hide_remote_providers_without_a_key_and_survive_an_ollama_outage(cfg_dir):
    providers.save_provider("nokey", {"kind": "custom", "base_url": "http://h/v1", "models": ["m"]})

    def _down():
        raise ConnectionError("ollama down")

    assert _client(_down).get("/options").json()["llm_options"] == []


def test_provider_endpoints_never_return_the_key(cfg_dir):
    client = _client()
    saved = client.put("/settings/llm-providers/openrouter", json=OPENROUTER).json()
    assert saved["api_key_set"] is True and "api_key" not in saved
    listed = {p["id"]: p for p in client.get("/settings/llm-providers").json()}
    assert set(listed) >= {"local", "gemini", "openrouter"}
    assert "sk-test" not in str(listed)
    assert client.put("/settings/llm-providers/local", json=OPENROUTER).status_code == 422
    assert client.delete("/settings/llm-providers/gemini").status_code == 422
    assert client.delete("/settings/llm-providers/openrouter").json() == {"deleted": "openrouter"}
    assert client.delete("/settings/llm-providers/openrouter").status_code == 404


def test_provider_test_endpoint_reports_answer_usage_or_error(cfg_dir, monkeypatch):
    import langchain.chat_models as chat_models

    class _Msg:
        content = "OK"
        usage_metadata = {"input_tokens": 9, "output_tokens": 1}

    class _Model:
        def invoke(self, prompt):
            return _Msg()

    monkeypatch.setattr(chat_models, "init_chat_model", lambda *a, **k: _Model())
    client = _client()
    client.put("/settings/llm-providers/openrouter", json=OPENROUTER)
    ok = client.post("/settings/llm-providers/openrouter/test", json={"model": "qwen/qwen3.5-9b"}).json()
    assert ok["ok"] is True and ok["answer"] == "OK"
    assert ok["usage"] == {"calls": 1, "input_tokens": 9, "output_tokens": 1, "reasoning_tokens": 0}

    def _boom(*a, **k):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(chat_models, "init_chat_model", _boom)
    bad = client.post("/settings/llm-providers/openrouter/test", json={"model": "m"}).json()
    assert bad["ok"] is False and "401" in bad["error"]


def test_requests_per_minute_is_stored_validated_and_public(cfg_dir):
    saved = providers.save_provider("capped", {**OPENROUTER, "requests_per_minute": 18})
    assert saved.requests_per_minute == 18
    assert providers.get_provider("capped").public()["requests_per_minute"] == 18
    with pytest.raises(ValueError, match="requests_per_minute"):
        providers.save_provider("capped", {**OPENROUTER, "requests_per_minute": 0})
