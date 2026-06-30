"""Retrieval package. Importing it registers the built-in retrievers."""
from app.core.retrieval.base import (
    Retriever,
    build_retriever,
    cosine_similarity,
    retrieval_registry,
)
from app.core.retrieval.mmr import MMRRetriever
from app.core.retrieval.multi_query import MultiQueryRetriever
from app.core.retrieval.parent_document import ParentDocumentRetriever
from app.core.retrieval.similarity import SimilarityRetriever

__all__ = [
    "Retriever",
    "build_retriever",
    "cosine_similarity",
    "retrieval_registry",
    "SimilarityRetriever",
    "MMRRetriever",
    "MultiQueryRetriever",
    "ParentDocumentRetriever",
]
