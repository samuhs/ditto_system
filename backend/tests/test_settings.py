import importlib

from app.core.config import settings as settings_module


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/ditto")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    settings_module.get_settings.cache_clear()
    cfg = settings_module.get_settings()
    assert cfg.database_url == "postgresql://u:p@db:5432/ditto"
    assert cfg.qdrant_url == "http://qdrant:6333"
    assert cfg.gemini_api_key == "secret"


def test_gemini_key_optional(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings_module.get_settings.cache_clear()
    cfg = settings_module.get_settings()
    assert cfg.gemini_api_key is None
