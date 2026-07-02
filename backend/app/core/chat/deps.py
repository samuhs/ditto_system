"""Injectable dependencies for the chat service (overridable in tests)."""
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.chat.agent import build_chat_model, run_agent
from app.core.embedding.base import build_embedder
from app.core.retrieval.base import build_retriever
from app.core.vectorstore.qdrant import QdrantStore


@dataclass
class ChatDeps:
    """Dependencies for handling a chat turn / persisting dialogues."""

    store: QdrantStore
    session_factory: Callable[[], Session]
    chat_model_factory: Callable = build_chat_model
    embedder_factory: Callable = build_embedder
    retriever_factory: Callable = build_retriever
    agent_runner: Callable = run_agent
