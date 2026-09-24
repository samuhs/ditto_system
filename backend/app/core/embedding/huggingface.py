"""Local sentence-transformers embedding providers (multilingual)."""
from app.core.embedding.base import Embedder, embedding_registry


class HuggingFaceEmbedder(Embedder):
    """Embeds text with a local SentenceTransformer model."""

    is_local = True

    def __init__(self, model_name: str, model=None, device: str | None = None) -> None:
        if model is None:
            from sentence_transformers import SentenceTransformer

            # "auto" (or None) lets sentence-transformers pick the device.
            model = SentenceTransformer(model_name, device=None if device in (None, "auto") else device)
        self._model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""
        return [list(map(float, vector)) for vector in self._model.encode(texts)]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return list(map(float, self._model.encode(text)))

    @property
    def dimension(self) -> int:
        """Vector length reported by the underlying model."""
        return self._model.get_sentence_embedding_dimension()


class E5Embedder(HuggingFaceEmbedder):
    """Local embedder using multilingual-e5-small."""

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("intfloat/multilingual-e5-small", model=model, device=device)


class ParaphraseEmbedder(HuggingFaceEmbedder):
    """Local embedder using paraphrase-multilingual-MiniLM."""

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("paraphrase-multilingual-MiniLM-L12-v2", model=model, device=device)


embedding_registry.register("e5", E5Embedder)
embedding_registry.register("paraphrase", ParaphraseEmbedder)
