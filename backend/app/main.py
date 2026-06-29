"""FastAPI application entry point."""
from fastapi import FastAPI

from app.api import health


def create_app() -> FastAPI:
    """Create and configure the FastAPI instance."""
    app = FastAPI(title="Ditto - Fatia A")
    app.include_router(health.router)
    return app


app = create_app()
