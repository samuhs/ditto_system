"""RAG technique interface, result model, registry, and helpers."""
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.registry import Registry


class RAGResult(BaseModel):
    """Answer produced by a RAG technique, with its supporting contexts."""

    answer: str
    contexts: list[dict]


def format_context(contexts: list[dict]) -> str:
    """Join the contexts' text into a single prompt-ready block."""
    return "\n\n".join(context.get("text", "") for context in contexts)


class RAG(ABC):
    """Minimal interface every RAG technique implements."""

    @abstractmethod
    def answer(self, query: str) -> RAGResult:
        """Answer a question, returning the answer and its contexts."""


rag_registry: Registry[type[RAG]] = Registry("rag")


def build_rag(name: str, **kwargs) -> RAG:
    """Instantiate a registered RAG technique by name."""
    return rag_registry.get(name)(**kwargs)
