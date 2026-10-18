"""The one LLM implementation: a LangChain chat model built by `init_chat_model`.

Nothing here knows any provider. The provider's configuration (kind, URL, key, extra
arguments) goes to `init_chat_model`, which returns the matching LangChain chat model; the
same `generate` then works for a local MLX server, OpenRouter, Gemini or any other.
"""
from app.core.llm import usage
from app.core.llm.base import LLM, llm_registry, sampling_kwargs
from app.core.llm.providers import Provider


def build_chat_model(provider: Provider, model: str, *, temperature: float | None = None,
                     max_tokens: int | None = None, timeout: float | None = None):
    """A LangChain chat model for `model` served by `provider`."""
    from langchain.chat_models import init_chat_model

    kwargs = dict(provider.params)
    # Unset sampling (None) falls back to the provider's defaults.
    kwargs.update(sampling_kwargs(temperature=temperature))
    if max_tokens is not None:
        if provider.tokens_in_body():
            kwargs["extra_body"] = {**kwargs.get("extra_body", {}), "max_tokens": max_tokens}
        else:
            kwargs["max_tokens"] = max_tokens
    if provider.base_url:
        kwargs["base_url"] = provider.base_url
    key = provider.resolved_key()
    if key:
        kwargs["api_key"] = key
    if timeout is not None:
        # Travamento/2 (#20): a hard timeout so a stuck call fails into the usual retry
        # path instead of hanging the worker thread.
        kwargs["timeout"] = timeout
    model_provider = "openai" if provider.kind == "custom" else provider.kind
    return init_chat_model(model, model_provider=model_provider, **kwargs)


def _text(content) -> str:
    """The answer text of a chat message's content (a string, or a list of content blocks)."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


class ChatModelLLM(LLM):
    """Generates answers with any LangChain chat model."""

    def __init__(self, client) -> None:
        self._client = client

    def generate(self, prompt: str) -> str:
        """Return the model's answer, recording the call's token usage."""
        message = self._client.invoke(prompt)
        usage.record(getattr(message, "usage_metadata", None))
        return _text(message.content)


llm_registry.register("chat_model", ChatModelLLM)
