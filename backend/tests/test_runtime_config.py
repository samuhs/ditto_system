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


def test_ollama_models_roundtrip(cfg_dir):
    assert runtime.get_ollama_models() == []
    runtime.set_ollama_models(
        [{"id": "qwen", "model": "qwen2.5:3b-instruct"}], reserved={"gemini"}
    )
    assert runtime.get_ollama_models() == [{"id": "qwen", "model": "qwen2.5:3b-instruct"}]


def test_validate_ollama_models_rejects_bad_entries(cfg_dir):
    with pytest.raises(ValueError):
        runtime.validate_ollama_models([{"id": "bad id", "model": "m"}], reserved=set())
    with pytest.raises(ValueError):
        runtime.validate_ollama_models([{"id": "qwen", "model": ""}], reserved=set())
    with pytest.raises(ValueError):
        runtime.validate_ollama_models([{"id": "gemini", "model": "m"}], reserved={"gemini"})
    with pytest.raises(ValueError):
        runtime.validate_ollama_models(
            [{"id": "x", "model": "m"}, {"id": "x", "model": "n"}], reserved=set()
        )
