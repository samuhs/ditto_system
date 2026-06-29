"""Ponto de entrada da aplicacao FastAPI."""
from fastapi import FastAPI

from app.api import health


def create_app() -> FastAPI:
    """Cria e configura a instancia FastAPI."""
    app = FastAPI(title="Ditto - Fatia A")
    app.include_router(health.router)
    return app


app = create_app()
