"""Custom LLM provider for any OpenAI-compatible endpoint (Ollama, vLLM, etc.)."""
from app.core.llm.base import LLM, llm_registry


class CustomLLM(LLM):
    """Generates answers via an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        model: str = "qwen2",
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "not-needed",
        client=None,
    ) -> None:
        if client is None:
            from langchain_openai import ChatOpenAI

            client = ChatOpenAI(model=model, base_url=base_url, api_key=api_key)
        self._client = client

    def generate(self, prompt: str) -> str:
        """Return the endpoint's answer for the prompt."""
        return self._client.invoke(prompt).content


llm_registry.register("custom", CustomLLM)
