"""Tests for application startup behaviour."""
from unittest.mock import patch


def test_create_all_called_on_startup():
    """Assert that create_all is called exactly once when the app starts."""
    with patch("app.main.create_all") as mock_create:
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()):
            pass
        mock_create.assert_called_once()
