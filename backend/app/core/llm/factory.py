"""LLM factory: resolves an LLM name to a chat model of its provider."""
from app.core.llm.base import LLM
from app.core.llm.chat_model import ChatModelLLM, build_chat_model
from app.core.llm.providers import split_llm_name


def resolve_llm(name: str, client=None, **kwargs) -> LLM:
    """Build the LLM for a name (see app.core.llm.providers for the naming rules).

    `client` injects a ready chat model (tests); otherwise the provider's configuration
    builds one. Raises KeyError for a name no provider serves.
    """
    provider, model = split_llm_name(name)
    if client is not None:
        return ChatModelLLM(client)
    return ChatModelLLM(build_chat_model(provider, model, **kwargs))


def is_local_llm(name: str) -> bool:
    """Whether the named LLM runs on this machine (so it competes for memory and the GPU).

    A name no provider serves counts as local: the memory policy then stays conservative.
    """
    try:
        provider, _ = split_llm_name(name)
    except KeyError:
        return True
    return provider.local
