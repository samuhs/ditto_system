"""Chunking package. Importing it registers the built-in strategies."""
from app.core.chunking.base import Chunker, build_chunker, chunking_registry
from app.core.chunking.markdown import MarkdownHeaderChunker
from app.core.chunking.semantic import SemanticChunker
from app.core.chunking.splitters import (
    FixedSizeChunker,
    RecursiveChunker,
    TokenChunker,
)

__all__ = [
    "Chunker",
    "build_chunker",
    "chunking_registry",
    "FixedSizeChunker",
    "RecursiveChunker",
    "TokenChunker",
    "SemanticChunker",
    "MarkdownHeaderChunker",
]
