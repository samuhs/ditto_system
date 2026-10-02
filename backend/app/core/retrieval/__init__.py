"""Retrieval package. Importing it registers the built-in retrievers."""
from app.core.retrieval import (  # noqa: F401  registers the built-ins
    mmr,
    multi_query,
    parent_document,
    similarity,
)
