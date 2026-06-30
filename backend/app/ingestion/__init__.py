"""Ingestion package."""
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig, IngestResult

__all__ = ["ingest_documents", "Document", "IngestConfig", "IngestResult"]
