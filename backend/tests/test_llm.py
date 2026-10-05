"""Tests for the LLM provider interface and implementations."""
from app.core.llm.base import LLM, build_llm, llm_registry
from app.core.llm.gemini import GeminiLLM
from app.core.llm.ollama import OllamaLLM


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeClient:
    """Stands in for a LangChain chat client."""

    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def invoke(self, prompt: str) -> _FakeResponse:
        self.last_prompt = prompt
        return _FakeResponse("generated answer")


def test_gemini_generate_uses_injected_client():
    client = _FakeClient()
    llm = GeminiLLM(client=client)
    result = llm.generate("question?")
    assert result == "generated answer"
    assert client.last_prompt == "question?"


def test_providers_registered():
    assert set(llm_registry.names()) >= {"gemini", "ollama"}


def test_build_llm_constructs_provider():
    client = _FakeClient()
    llm = build_llm("gemini", client=client)
    assert isinstance(llm, GeminiLLM)
    assert isinstance(llm, LLM)
    assert llm.generate("x") == "generated answer"

    local = build_llm("ollama", model="qwen2", client=_FakeClient())
    assert isinstance(local, OllamaLLM)
    assert local.generate("y") == "generated answer"


def test_ollama_registered():
    assert "ollama" in llm_registry.names()


def test_ollama_generate_uses_injected_client():
    client = _FakeClient()
    llm = OllamaLLM(client=client)
    assert llm.generate("hi") == "generated answer"
    assert client.last_prompt == "hi"


def test_ollama_uses_settings_defaults(monkeypatch):
    import langchain_openai

    from app.core.config.settings import get_settings

    captured = {}

    class _FakeChatOpenAI:
        def __init__(self, model, base_url, api_key, **kwargs):
            captured["model"] = model
            captured["base_url"] = base_url
            captured["api_key"] = api_key

        def invoke(self, prompt):
            return _FakeResponse("ok")

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    get_settings.cache_clear()
    try:
        llm = OllamaLLM()
        assert captured["model"] == "qwen2.5:3b-instruct"
        assert captured["base_url"] == "http://host.docker.internal:11434/v1"
        assert captured["api_key"] == "ollama"
        assert llm.generate("x") == "ok"
    finally:
        get_settings.cache_clear()


def test_ollama_passes_an_explicit_temperature(monkeypatch):
    import langchain_openai

    captured = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    OllamaLLM(model="m", base_url="http://localhost:11436/v1", temperature=0)
    assert captured["temperature"] == 0


def _capture_kwargs(monkeypatch, module, attr):
    captured = {}

    class _Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(module, attr, _Fake)
    return captured


def test_ollama_passes_max_tokens_and_omits_unset_temperature(monkeypatch):
    import langchain_openai

    captured = _capture_kwargs(monkeypatch, langchain_openai, "ChatOpenAI")
    OllamaLLM(model="m", base_url="http://localhost:11436/v1", max_tokens=256)
    # In the raw body: langchain-openai renames a typed max_tokens to
    # max_completion_tokens, which Ollama silently ignores.
    assert captured["extra_body"] == {"max_tokens": 256}
    assert "max_tokens" not in captured
    assert "temperature" not in captured  # None: the server's default applies


def test_ollama_omits_max_tokens_when_unset(monkeypatch):
    import langchain_openai

    captured = _capture_kwargs(monkeypatch, langchain_openai, "ChatOpenAI")
    OllamaLLM(model="m", base_url="http://localhost:11436/v1", temperature=0)
    assert captured["temperature"] == 0
    assert "max_tokens" not in captured
    assert "extra_body" not in captured


def test_gemini_passes_temperature_zero_and_max_output_tokens(monkeypatch):
    import langchain_google_genai

    captured = _capture_kwargs(monkeypatch, langchain_google_genai, "ChatGoogleGenerativeAI")
    GeminiLLM(model="gemini-2.5-flash-lite", api_key="k", temperature=0, max_tokens=128)
    assert captured["temperature"] == 0
    assert captured["max_output_tokens"] == 128


def test_gemini_omits_unset_sampling(monkeypatch):
    import langchain_google_genai

    captured = _capture_kwargs(monkeypatch, langchain_google_genai, "ChatGoogleGenerativeAI")
    GeminiLLM(model="gemini-2.5-flash-lite", api_key="k")
    assert "temperature" not in captured
    assert "max_output_tokens" not in captured
