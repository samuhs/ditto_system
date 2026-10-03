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

    # False for techniques that never search a Retriever: an experiment does not
    # multiply them by the Retrievers it lists.
    uses_retrieval: bool = True
    # False for techniques that never read an Índice (closed book, oracle): an
    # experiment runs them once per LLM instead of once per Índice.
    uses_index: bool = True
    # True for techniques that answer from the Índice's Grafo de conhecimento: an
    # experiment builds the graph first and passes it as graph=..., embedder=...
    uses_graph: bool = False
    # True for techniques that answer from the question's reference evidence
    # (oracle): they are called as answer(query, evidence=[...]).
    uses_evidence: bool = False

    @abstractmethod
    def answer(self, query: str) -> RAGResult:
        """Answer a question, returning the answer and its contexts."""


rag_registry: Registry[type[RAG]] = Registry("rag")


def technique_class(name: str) -> type[RAG] | None:
    """The registered technique, or None for a name the registry does not know."""
    return rag_registry.get(name) if name in rag_registry.names() else None


def build_rag(name: str, **kwargs) -> RAG:
    """Instantiate a registered RAG technique by name."""
    return rag_registry.get(name)(**kwargs)
