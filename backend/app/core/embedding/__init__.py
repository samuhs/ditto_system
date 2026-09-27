"""Embedding providers package. Importing it registers the built-in providers."""
from app.core.embedding.base import Embedder, build_embedder, embedding_registry
from app.core.embedding.gemini import GeminiEmbedder
from app.core.embedding.huggingface import (
    E5Embedder,
    EmbeddingGemmaEmbedder,
    GraniteEmbedder,
    HuggingFaceEmbedder,
    ParaphraseEmbedder,
)

__all__ = [
    "Embedder",
    "build_embedder",
    "embedding_registry",
    "GeminiEmbedder",
    "HuggingFaceEmbedder",
    "E5Embedder",
    "ParaphraseEmbedder",
    "EmbeddingGemmaEmbedder",
    "GraniteEmbedder",
]
