"""Shared test fixtures."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import models  # noqa: F401  registers models on Base.metadata
from app.core.db.base import Base
from app.main import create_app


@pytest.fixture(autouse=True)
def _disable_dotenv(monkeypatch):
    """Prevent the project .env from being loaded during tests.

    Tests that need specific env values should set them explicitly via
    monkeypatch.setenv. This avoids real secrets leaking into assertions.
    """
    monkeypatch.setenv("ENV_FILE", "")


@pytest.fixture(autouse=True)
def _no_ollama_server(monkeypatch):
    """Keep /options from querying a real Ollama server; tests see none by default."""
    from app.api import options

    monkeypatch.setattr(options, "list_ollama_models", lambda: [])


@pytest.fixture(autouse=True)
def _no_llm_probe(monkeypatch):
    """Tests never talk to a real LLM server: none is resident, unloads are no-ops."""
    from app.core.llm import ollama

    monkeypatch.setattr(ollama, "local_llm_resident", lambda *a, **k: False)
    monkeypatch.setattr(ollama, "unload_local_llm", lambda *a, **k: False)


@pytest.fixture(autouse=True)
def _no_mlx_perplexity(monkeypatch, tmp_path):
    """Tests never start the MLX perplexity process: its Python is not found."""
    monkeypatch.setenv("DITTO_HOME", str(tmp_path / "no-ditto-home"))


@pytest.fixture
def client():
    """Test client for the FastAPI application."""
    return TestClient(create_app())


@pytest.fixture
def db_session():
    """Isolated SQLAlchemy session backed by an in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
