"""Local sentence-transformers embedding providers (multilingual)."""
import threading
from contextlib import contextmanager

from app.core.embedding.base import Embedder, embedding_registry

_BATCH_SIZE = 32

# Tokenizers built in this process, by (path, kwargs). Loading one through
# AutoProcessor leaves native memory behind that is never returned (~100-250 MB
# for a 250k-vocab tokenizer), so an embedder evicted and loaded again by the
# ModelManager grew the API on every Experimento. Reusing the built tokenizer
# bounds that to one load per model.
_tokenizers: dict[tuple, object] = {}
_tokenizers_lock = threading.Lock()

# One encode at a time on the GPU, across every embedder: Metal (MPS) aborts the whole
# process ("failed assertion ... MTLCommandBufferStatusCommitted") when two threads encode
# at once, which happens when questions run in parallel and a technique embeds the
# queries the LLM writes (agentic, hyde, crag, multi_query) while another thread scores.
_gpu_lock = threading.Lock()


def _is_gpu_oom(exc: Exception) -> bool:
    text = str(exc).lower()
    return "out of memory" in text and ("mps" in text or "cuda" in text)


def free_gpu_cache() -> None:
    """Hand the GPU memory PyTorch keeps cached back to the system.

    On Apple Silicon the MPS allocator keeps every encode's buffers; over several
    experiments in one process (long contexts, many answers to score) the cache reached
    the unified-memory limit and scoring failed with "MPS backend out of memory".
    """
    try:
        import torch
    except ImportError:  # pragma: no cover - torch ships with sentence-transformers
        return
    if hasattr(torch, "mps") and torch.backends.mps.is_available():
        torch.mps.empty_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@contextmanager
def reuse_tokenizers():
    """While loading a SentenceTransformer, hand back tokenizers already built.

    A no-op on sentence-transformers versions without this module layout.
    """
    try:
        import sentence_transformers.base.modules.transformer as st_transformer
    except ImportError:
        yield
        return

    with _tokenizers_lock:
        original = st_transformer.AutoProcessor

        class _CachedProcessor:
            @staticmethod
            def from_pretrained(path, **kwargs):
                key = (str(path), repr(sorted(kwargs.items())))
                if key not in _tokenizers:
                    _tokenizers[key] = original.from_pretrained(path, **kwargs)
                return _tokenizers[key]

        st_transformer.AutoProcessor = _CachedProcessor
        try:
            yield
        finally:
            st_transformer.AutoProcessor = original


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
            with reuse_tokenizers():
                model = SentenceTransformer(model_name, device=None if device in (None, "auto") else device)
        self._model = model
        self._cpu_lock = threading.Lock()

    def _lock(self) -> threading.Lock:
        """The GPU-wide lock when the model sits on a GPU, else this instance's own."""
        device = str(getattr(self._model, "device", "cpu"))
        return _gpu_lock if device.startswith(("mps", "cuda")) else self._cpu_lock

    def _run(self, inputs, **kwargs):
        lock = self._lock()
        on_gpu = lock is _gpu_lock
        with lock:
            try:
                return self._model.encode(inputs, convert_to_numpy=True, **kwargs)
            except RuntimeError as exc:
                if not (on_gpu and _is_gpu_oom(exc)):
                    raise
                # Free the cache and retry once in small batches before giving up.
                free_gpu_cache()
                kwargs["batch_size"] = max(1, kwargs.get("batch_size", _BATCH_SIZE) // 8)
                return self._model.encode(inputs, convert_to_numpy=True, **kwargs)
            finally:
                if on_gpu:
                    free_gpu_cache()

    def _encode(self, texts: list[str], prefix: str) -> list[list[float]]:
        """Encode a batch, each text behind the given prefix."""
        prefixed = [prefix + text for text in texts]
        return _floats(self._run(prefixed, batch_size=_BATCH_SIZE))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""
        return self._encode(texts, self.document_prefix)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed several queries in one batched call."""
        return self._encode(texts, self.query_prefix)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return _floats(self._run(self.query_prefix + text))

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


class EmbeddingGemmaEmbedder(HuggingFaceEmbedder):
    """Local embedder using EmbeddingGemma-300m (768 dims, best open <1B model on MTEB-BR).

    The repository is gated: HF_TOKEN must belong to an account that accepted
    the Gemma terms. Its model card asks for task prompts, and it does not
    support float16 (sentence-transformers loads it in float32).
    """

    document_prefix = "title: none | text: "
    query_prefix = "task: search result | query: "

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("google/embeddinggemma-300m", model=model, device=device)


class GraniteEmbedder(HuggingFaceEmbedder):
    """Local embedder using IBM granite-embedding-97m-multilingual-r2 (384 dims, no prompts)."""

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("ibm-granite/granite-embedding-97m-multilingual-r2", model=model, device=device)


embedding_registry.register("e5", E5Embedder)
embedding_registry.register("paraphrase", ParaphraseEmbedder)
embedding_registry.register("embeddinggemma", EmbeddingGemmaEmbedder)
embedding_registry.register("granite", GraniteEmbedder)
