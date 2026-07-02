"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.core.chunking  # noqa: F401  registers chunking strategies
import app.core.embedding  # noqa: F401  registers embedding providers
import app.core.evaluation  # noqa: F401  registers evaluation metrics
import app.core.llm  # noqa: F401  registers LLM providers
import app.core.rag  # noqa: F401  registers RAG techniques
import app.core.retrieval  # noqa: F401  registers retrievers
from app.api import chat, experiments, health, ingest, options, prompts
from app.core.db import models  # noqa: F401  registers models on Base.metadata
from app.core.db.base import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    create_all()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI instance."""
    app = FastAPI(title="Ditto - Fatia A", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(options.router)
    app.include_router(ingest.router)
    app.include_router(experiments.router)
    app.include_router(prompts.router)
    app.include_router(chat.router)
    return app


app = create_app()
