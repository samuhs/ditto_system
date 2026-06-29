"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.db import models  # noqa: F401 — registers models on Base.metadata
from app.core.db.base import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables when the application starts."""
    create_all()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI instance."""
    app = FastAPI(title="Ditto - Fatia A", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
