"""Injectable dependencies for the chat service (overridable in tests)."""
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.chat.graph import run_flow
from app.core.embedding.base import build_embedder
from app.core.llm.factory import resolve_llm
from app.core.memory.manager import ModelManager
from app.core.memory.profile import active_profile
from app.core.rag.base import build_rag
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore


@dataclass
class ChatDeps:
    """Dependencies for handling a chat turn / persisting dialogues."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    llm_factory: Callable = resolve_llm
    embedder_factory: Callable = build_embedder
    retriever_factory: Callable = build_retriever
    rag_factory: Callable = build_rag
    agent_runner: Callable = run_flow
    # Shared embedder cache; None builds a private one around embedder_factory.
    models: ModelManager | None = None

    def __post_init__(self) -> None:
        if self.models is None:
            self.models = ModelManager(self.embedder_factory, max_local=active_profile().max_local_models)
