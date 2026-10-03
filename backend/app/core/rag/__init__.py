"""RAG package. Importing it registers the built-in techniques."""
from app.core.rag import (  # noqa: F401  registers the built-ins
    agentic,
    closed_book,
    compression,
    crag,
    graph,
    hyde,
    naive,
    oracle,
    rerank,
)
