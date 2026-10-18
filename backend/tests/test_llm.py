"""Tests for the generic LLM: one LangChain chat model for every provider."""
import pytest

from app.core.llm import usage
from app.core.llm.base import LLM, build_llm, llm_registry
from app.core.llm.chat_model import ChatModelLLM, build_chat_model
from app.core.llm.providers import Provider


class _FakeMessage:
    def __init__(self, content, usage_metadata=None) -> None:
        self.content = content
        self.usage_metadata = usage_metadata


class _FakeClient:
    """Stands in for a LangChain chat model."""

    def __init__(self, content="generated answer", usage_metadata=None) -> None:
        self.last_prompt: str | None = None
        self._message = _FakeMessage(content, usage_metadata)

    def invoke(self, prompt: str) -> _FakeMessage:
        self.last_prompt = prompt
        return self._message


def test_generate_uses_the_injected_client():
    client = _FakeClient()
    llm = ChatModelLLM(client)
    assert llm.generate("question?") == "generated answer"
    assert client.last_prompt == "question?"


def test_generate_joins_the_text_blocks_of_a_list_content():
    """Some providers return content blocks (text plus reasoning); only text is the answer."""
    client = _FakeClient([{"type": "reasoning", "reasoning": "hmm"}, {"type": "text", "text": "Sim"},
                          {"type": "text", "text": "."}])
    assert ChatModelLLM(client).generate("x") == "Sim."


def test_the_one_llm_is_registered():
    assert "chat_model" in llm_registry.names()
    llm = build_llm("chat_model", client=_FakeClient())
    assert isinstance(llm, LLM)
    assert llm.generate("y") == "generated answer"


def test_usage_sums_the_calls_inside_a_scope():
    meta = {"input_tokens": 100, "output_tokens": 20, "output_token_details": {"reasoning": 5}}
    llm = ChatModelLLM(_FakeClient(usage_metadata=meta))
    with usage.track() as totals:
        llm.generate("a")
        llm.generate("b")
    assert totals == {"calls": 2, "input_tokens": 200, "output_tokens": 40, "reasoning_tokens": 10}


def test_usage_counts_calls_without_metadata_and_ignores_calls_outside_a_scope():
    llm = ChatModelLLM(_FakeClient())
    llm.generate("outside")  # no scope: nothing to record, no error
    with usage.track() as totals:
        llm.generate("inside")
    assert totals == {"calls": 1, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}


def _capture_init(monkeypatch):
    """Replace init_chat_model and capture what it receives."""
    import langchain.chat_models as chat_models

    captured = {}

    def _fake(model, model_provider=None, **kwargs):
        captured.update(model=model, model_provider=model_provider, **kwargs)
        return _FakeClient()

    monkeypatch.setattr(chat_models, "init_chat_model", _fake)
    return captured


def test_a_custom_provider_is_an_openai_compatible_endpoint(monkeypatch):
    captured = _capture_init(monkeypatch)
    provider = Provider(id="openrouter", kind="custom", base_url="https://openrouter.ai/api/v1", api_key="k",
                        params={"extra_body": {"reasoning": {"enabled": False}}})
    build_chat_model(provider, "qwen/qwen3.5-9b", temperature=0, max_tokens=512, timeout=30)
    assert captured["model"] == "qwen/qwen3.5-9b"
    assert captured["model_provider"] == "openai"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["api_key"] == "k"
    assert captured["temperature"] == 0
    assert captured["timeout"] == 30
    # custom: max_tokens in the raw body, next to the provider's own extras
    assert captured["extra_body"] == {"reasoning": {"enabled": False}, "max_tokens": 512}
    assert "max_tokens" not in captured


def test_a_named_provider_goes_to_langchain_with_typed_arguments(monkeypatch):
    captured = _capture_init(monkeypatch)
    provider = Provider(id="gemini", kind="google_genai", api_key="k")
    build_chat_model(provider, "gemini-2.5-flash-lite", temperature=0, max_tokens=128)
    assert captured["model_provider"] == "google_genai"
    assert captured["max_tokens"] == 128
    assert "extra_body" not in captured and "base_url" not in captured


def test_unset_sampling_and_timeout_are_left_to_the_provider(monkeypatch):
    captured = _capture_init(monkeypatch)
    build_chat_model(Provider(id="x", kind="openai", api_key="k"), "m")
    assert not {"temperature", "max_tokens", "timeout", "extra_body"} & set(captured)


def test_the_key_can_come_from_an_environment_variable(monkeypatch):
    captured = _capture_init(monkeypatch)
    monkeypatch.setenv("MY_PROVIDER_KEY", "from-env")
    build_chat_model(Provider(id="x", kind="custom", base_url="http://h/v1", api_key_env="MY_PROVIDER_KEY"), "m")
    assert captured["api_key"] == "from-env"


def test_real_langchain_models_are_built_without_provider_classes():
    """The real init_chat_model builds each provider's LangChain model from the same call."""
    openai_like = build_chat_model(
        Provider(id="r", kind="custom", base_url="https://openrouter.ai/api/v1", api_key="k"),
        "qwen/qwen3.5-9b", temperature=0, max_tokens=64, timeout=12.5,
    )
    assert openai_like.openai_api_base == "https://openrouter.ai/api/v1"
    assert openai_like.request_timeout == 12.5
    assert openai_like.extra_body == {"max_tokens": 64}
    gemini = build_chat_model(Provider(id="gemini", kind="google_genai", api_key="k"), "gemini-2.5-flash-lite",
                              temperature=0, max_tokens=128, timeout=12.5)
    assert gemini.max_output_tokens == 128
    assert gemini.timeout == 12.5


@pytest.mark.parametrize("in_body", [True, False])
def test_max_tokens_placement_can_be_forced(monkeypatch, in_body):
    captured = _capture_init(monkeypatch)
    build_chat_model(Provider(id="x", kind="custom", base_url="http://h/v1", max_tokens_in_body=in_body), "m",
                     max_tokens=10)
    assert ("max_tokens" in captured.get("extra_body", {})) is in_body
    assert ("max_tokens" in captured) is not in_body
