"""FastAPI dependencies shared by the ingestion, Bases and Grafo build endpoints."""
from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from app.core.db.base import SessionLocal
from app.core.embedding.base import Embedder, build_embedder
from app.core.graph.jobs import GraphBuildDeps, GraphBuilds, graph_builds
from app.core.llm.factory import resolve_llm
from app.core.memory.manager import ModelManager, get_model_manager
from app.core.memory.profile import active_profile
from app.core.vectorstore.qdrant import QdrantStore


def get_store() -> QdrantStore:
    """The vector store."""
    return QdrantStore()


def get_embedder_factory() -> Callable[..., Embedder]:
    """The embedder factory."""
    return build_embedder


def get_models(
    embedder_factory: Callable[..., Embedder] = Depends(get_embedder_factory),
) -> ModelManager:
    """The shared model cache; a test-injected factory gets a private one."""
    if embedder_factory is build_embedder:
        return get_model_manager()
    return ModelManager(embedder_factory, max_local=active_profile().max_local_models)


def get_session_factory() -> sessionmaker[Session]:
    """The database session factory."""
    return SessionLocal


def get_llm_factory() -> Callable:
    """Builds an LLM by name (the LLM extrator of a Grafo build)."""
    return resolve_llm


def get_graph_builds() -> GraphBuilds:
    """The process's Grafo de conhecimento build jobs."""
    return graph_builds


def get_graph_build_deps(
    store: QdrantStore = Depends(get_store),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    models: ModelManager = Depends(get_models),
    llm_factory: Callable = Depends(get_llm_factory),
) -> GraphBuildDeps:
    """What a Grafo build job runs with."""
    return GraphBuildDeps(
        store=store, session_factory=session_factory, models=models, llm_factory=llm_factory
    )
