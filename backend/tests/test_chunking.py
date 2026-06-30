"""Tests for chunking strategies."""
from app.core.chunking.base import Chunker, build_chunker, chunking_registry
from app.core.chunking.splitters import (
    FixedSizeChunker,
    RecursiveChunker,
    TokenChunker,
)

_TEXT = (
    "First paragraph about the city center and the main square.\n\n"
    "Second paragraph about food, restaurants and local cuisine.\n\n"
    "Third paragraph about transport, taxis and walking around town."
)


def test_fixed_chunker_respects_size():
    chunker = FixedSizeChunker(chunk_size=40, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1
    assert all(len(c) <= 60 for c in chunks)


def test_recursive_chunker_produces_chunks():
    chunker = RecursiveChunker(chunk_size=50, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1
    assert "".join(chunks).replace(" ", "").replace("\n", "") != ""


def test_token_chunker_produces_chunks():
    chunker = TokenChunker(chunk_size=8, chunk_overlap=0)
    chunks = chunker.split(_TEXT)
    assert len(chunks) > 1


def test_chunkers_registered_and_built():
    assert {"fixed", "recursive", "token"} <= set(chunking_registry.names())
    chunker = build_chunker("recursive", chunk_size=50, chunk_overlap=0)
    assert isinstance(chunker, Chunker)
    assert len(chunker.split(_TEXT)) > 1
