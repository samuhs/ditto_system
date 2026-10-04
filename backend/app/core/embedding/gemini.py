"""Gemini embedding provider (via langchain-google-genai)."""
from app.core.config.runtime import get_gemini_key
from app.core.embedding.base import Embedder, embedding_registry


class GeminiEmbedder(Embedder):
    """Embeds text with a Google Gemini embedding model."""

    def __init__(
        self,
        model: str = "gemini-embedding-001",
        api_key: str | None = None,
        client=None,
        timeout: float | None = None,
    ) -> None:
        if client is None:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            # Travamento/2 (#20): a hard timeout on the HTTP client, so a stuck
            # embedding call fails into the usual retry path.
            client_args = {"timeout": timeout} if timeout is not None else None
            client = GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=api_key or get_gemini_key(),
                client_args=client_args,
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
