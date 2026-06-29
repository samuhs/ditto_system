"""Tests for the LLM provider interface and implementations."""
from app.core.llm.base import LLM, build_llm, llm_registry
from app.core.llm.custom import CustomLLM
from app.core.llm.gemini import GeminiLLM


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


def test_custom_generate_uses_injected_client():
    client = _FakeClient()
    llm = CustomLLM(model="qwen2", base_url="http://localhost:11434/v1", client=client)
    assert llm.generate("hi") == "generated answer"


def test_providers_registered():
    assert set(llm_registry.names()) >= {"gemini", "custom"}


def test_build_llm_constructs_provider():
    client = _FakeClient()
    llm = build_llm("gemini", client=client)
    assert isinstance(llm, GeminiLLM)
    assert isinstance(llm, LLM)
    assert llm.generate("x") == "generated answer"

    custom = build_llm(
        "custom", model="qwen2", base_url="http://localhost:11434/v1", client=_FakeClient()
    )
    assert isinstance(custom, CustomLLM)
    assert custom.generate("y") == "generated answer"
