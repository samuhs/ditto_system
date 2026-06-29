"""Gemini embedding provider (via langchain-google-genai)."""
from app.core.config.settings import get_settings
from app.core.embedding.base import Embedder, embedding_registry


class GeminiEmbedder(Embedder):
    """Embeds text with a Google Gemini embedding model."""

    def __init__(
        self,
        model: str = "text-embedding-004",
        api_key: str | None = None,
        client=None,
    ) -> None:
        if client is None:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            client = GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=api_key or get_settings().gemini_api_key,
            )
        self._client = client
        self._dimension: int | None = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return self._client.embed_query(text)

    @property
    def dimension(self) -> int:
        """Vector length, derived once from a probe query and cached."""
        if self._dimension is None:
            self._dimension = len(self.embed_query("dimension probe"))
        return self._dimension


embedding_registry.register("gemini", GeminiEmbedder)
