"""Local sentence-transformers embedding providers (multilingual)."""
from app.core.embedding.base import Embedder, embedding_registry

_BATCH_SIZE = 32


def _floats(values):
    """Vectors as plain Python floats (numpy's tolist is one fast call)."""
    if hasattr(values, "tolist"):
        return values.tolist()
    return [float(v) if isinstance(v, (int, float)) else _floats(v) for v in values]


class HuggingFaceEmbedder(Embedder):
    """Embeds text with a local SentenceTransformer model."""

    is_local = True
    # Instruction prefixes some models were trained with (e5: "query: "/"passage: ").
    document_prefix = ""
    query_prefix = ""

    def __init__(self, model_name: str, model=None, device: str | None = None) -> None:
        if model is None:
            from sentence_transformers import SentenceTransformer

            # "auto" (or None) lets sentence-transformers pick the device.
            model = SentenceTransformer(model_name, device=None if device in (None, "auto") else device)
        self._model = model

    def _encode(self, texts: list[str], prefix: str) -> list[list[float]]:
        """Encode a batch, each text behind the given prefix."""
        prefixed = [prefix + text for text in texts]
        return _floats(self._model.encode(prefixed, batch_size=_BATCH_SIZE, convert_to_numpy=True))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""
        return self._encode(texts, self.document_prefix)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed several queries in one batched call."""
        return self._encode(texts, self.query_prefix)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return _floats(self._model.encode(self.query_prefix + text, convert_to_numpy=True))

    @property
    def dimension(self) -> int:
        """Vector length reported by the underlying model."""
        return self._model.get_sentence_embedding_dimension()


class E5Embedder(HuggingFaceEmbedder):
    """Local embedder using multilingual-e5-small.

    Its model card asks for "query: " or "passage: " before every input, and
    "query: " for symmetric tasks such as comparing two answers.
    """

    document_prefix = "passage: "
    query_prefix = "query: "

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("intfloat/multilingual-e5-small", model=model, device=device)


class ParaphraseEmbedder(HuggingFaceEmbedder):
    """Local embedder using paraphrase-multilingual-MiniLM."""

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("paraphrase-multilingual-MiniLM-L12-v2", model=model, device=device)


embedding_registry.register("e5", E5Embedder)
embedding_registry.register("paraphrase", ParaphraseEmbedder)
