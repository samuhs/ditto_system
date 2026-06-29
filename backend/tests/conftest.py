"""Shared test fixtures."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db.base import Base
from app.main import create_app


@pytest.fixture
def client():
    """Test client for the FastAPI application."""
    return TestClient(create_app())


@pytest.fixture
def db_session():
    """Isolated SQLAlchemy session backed by an in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
