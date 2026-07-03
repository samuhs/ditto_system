"""RAG package. Importing it registers the built-in techniques."""
from app.core.rag.agentic import AgenticRAG
from app.core.rag.base import RAG, RAGResult, build_rag, format_context, rag_registry
from app.core.rag.hyde import HydeRAG
from app.core.rag.naive import NaiveRAG
from app.core.rag.rerank import RerankRAG

__all__ = [
    "RAG",
    "RAGResult",
    "build_rag",
    "format_context",
    "rag_registry",
    "NaiveRAG",
    "AgenticRAG",
    "HydeRAG",
    "RerankRAG",
]
