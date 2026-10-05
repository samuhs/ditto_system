"""Pydantic schemas for ingestion."""
from pydantic import BaseModel, field_validator

from app.core.graph.jobs import GraphBuildJob
from app.core.vectorstore.qdrant import validate_base_name


class Document(BaseModel):
    """A source document to ingest."""

    name: str
    text: str


class IngestConfig(BaseModel):
    """Configuration for an ingestion run."""

    base: str
    chunkings: list[str]
    embeddings: list[str]

    @field_validator("base")
    @classmethod
    def _valid_base(cls, value: str) -> str:
        validate_base_name(value)
        return value


class IngestResult(BaseModel):
    """Outcome of an ingestion run."""

    collections: list[str]
    total_chunks: int
    # The Grafo de conhecimento build queued after the Índices; None without one.
    graph_build: GraphBuildJob | None = None
