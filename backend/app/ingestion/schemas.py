"""Pydantic schemas for ingestion."""
from pydantic import BaseModel


class Document(BaseModel):
    """A source document to ingest."""

    name: str
    text: str


class IngestConfig(BaseModel):
    """Configuration for an ingestion run."""

    base: str
    chunkings: list[str]
    embeddings: list[str]


class IngestResult(BaseModel):
    """Outcome of an ingestion run."""

    collections: list[str]
    total_chunks: int
