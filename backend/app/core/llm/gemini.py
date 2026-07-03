"""Gemini LLM provider (via langchain-google-genai)."""
from app.core.config.runtime import get_gemini_key
from app.core.llm.base import LLM, llm_registry


class GeminiLLM(LLM):
    """Generates answers with a Google Gemini chat model."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash-lite",
        api_key: str | None = None,
        client=None,
    ) -> None:
        if client is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            client = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key or get_gemini_key(),
            )
        self._client = client

    def generate(self, prompt: str) -> str:
        """Return the Gemini answer for the prompt."""
        return self._client.invoke(prompt).content


llm_registry.register("gemini", GeminiLLM)
