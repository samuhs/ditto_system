"""Fixtures compartilhadas dos testes."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Cliente de teste da aplicacao FastAPI."""
    return TestClient(create_app())
