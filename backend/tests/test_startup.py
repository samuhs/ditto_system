"""Tests for application startup behaviour."""
from unittest.mock import patch


def test_create_all_called_on_startup():
    """Assert that create_all is called exactly once when the app starts."""
    with (
        patch("app.main.create_all") as mock_create,
        patch("app.main.recover_interrupted_experiments"),
    ):
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()):
            pass
        mock_create.assert_called_once()


def test_recover_interrupted_experiments_called_after_create_all_on_startup():
    """#18: the lifespan recovers Experimentos interrupted by a restart, right
    after creating tables, passing it the app's own session factory."""
    with (
        patch("app.main.create_all"),
        patch("app.main.recover_interrupted_experiments") as mock_recover,
        patch("app.main.SessionLocal", "fake-session-factory"),
    ):
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()):
            pass
        mock_recover.assert_called_once_with("fake-session-factory")
