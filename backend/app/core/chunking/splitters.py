"""Chunkers backed by langchain-text-splitters."""
from langchain_text_splitters import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)

from app.core.chunking.base import Chunker, chunking_registry


class FixedSizeChunker(Chunker):
    """Splits text into fixed-size character windows with overlap."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100) -> None:
        self._splitter = CharacterTextSplitter(
            separator="",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, text: str) -> list[str]:
        """Split text into fixed-size chunks."""
        return self._splitter.split_text(text)


class RecursiveChunker(Chunker):
    """Splits text respecting paragraph and sentence boundaries."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, text: str) -> list[str]:
        """Split text recursively into chunks."""
        return self._splitter.split_text(text)


class TokenChunker(Chunker):
    """Splits text by token count."""

    def __init__(self, chunk_size: int = 256, chunk_overlap: int = 20) -> None:
        self._splitter = TokenTextSplitter(
            encoding_name="cl100k_base",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, text: str) -> list[str]:
        """Split text into token-bounded chunks."""
        return self._splitter.split_text(text)


chunking_registry.register("fixed", FixedSizeChunker)
chunking_registry.register("recursive", RecursiveChunker)
chunking_registry.register("token", TokenChunker)
