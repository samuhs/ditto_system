"""Extraction cache: what the LLM extrator read in a chunk, kept across Índices and experiments.

A chunk's extraction depends only on its text, the LLM extrator and the extraction
prompt, never on the embedding: Índices with the same chunking share it, and only
the entity and relation vectors are redone. Each extraction is stored as soon as it
is read, so a build paused halfway resumes without asking the LLM again.
"""
import hashlib
import threading
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db.base import Base
from app.core.graph.extraction import Extraction

# Keys per query: an Índice can have thousands of chunks.
_BATCH = 500


class GraphExtraction(Base):
    """One chunk's extraction by one LLM extrator with one version of the prompt."""

    __tablename__ = "graph_extraction"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    extractor: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(16))
    extraction: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def prompt_version(prompt: str) -> str:
    """Short hash of the extraction prompt: editing the prompt changes it."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def extraction_key(text: str, extractor: str, prompt: str) -> str:
    """Cache key of a chunk: its text, the LLM extrator and the prompt version."""
    raw = "\0".join([prompt_version(prompt), extractor, text])
    return hashlib.sha256(raw.encode()).hexdigest()


class ExtractionCache:
    """Reads and writes extractions through the app's session factory (thread-safe)."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._lock = threading.Lock()  # extraction branches write from worker threads

    def get_many(self, keys: list[str]) -> dict[str, Extraction]:
        """The cached extractions among these keys."""
        found: dict[str, Extraction] = {}
        with self._lock:
            session = self._session_factory()
            try:
                for start in range(0, len(keys), _BATCH):
                    batch = keys[start : start + _BATCH]
                    rows = session.query(GraphExtraction).filter(GraphExtraction.key.in_(batch))
                    found.update({r.key: Extraction.model_validate(r.extraction) for r in rows})
            finally:
                session.close()
        return found

    def put(self, key: str, extractor: str, prompt: str, extraction: Extraction) -> None:
        """Store one chunk's extraction (replacing an older copy)."""
        with self._lock:
            session = self._session_factory()
            try:
                session.merge(
                    GraphExtraction(
                        key=key, extractor=extractor, prompt_version=prompt_version(prompt),
                        extraction=extraction.model_dump(),
                    )
                )
                session.commit()
            finally:
                session.close()
