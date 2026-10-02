"""Tests for the runtime settings store."""
import pytest

from app.core.config import runtime


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_gemini_key_file_overrides_env(cfg_dir, monkeypatch):
    from app.core.config.settings import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    get_settings.cache_clear()
    try:
        assert runtime.get_gemini_key() == "env-key"  # no file yet -> env
        runtime.set_gemini_key("file-key")
        assert runtime.get_gemini_key() == "file-key"  # file overrides
        runtime.set_gemini_key("")
        assert runtime.get_gemini_key() == "env-key"  # cleared -> env
    finally:
        get_settings.cache_clear()


def test_empty_env_gemini_key_is_none(cfg_dir, monkeypatch):
    from app.core.config.settings import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    try:
        assert runtime.get_gemini_key() is None
    finally:
        get_settings.cache_clear()
