"""Tests for the runtime settings store."""
import stat

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


def test_stall_limit_defaults_to_600s(cfg_dir):
    assert runtime.get_stall_limit_s() == 600.0


def test_stall_limit_persists(cfg_dir):
    runtime.set_stall_limit_s(120.0)
    assert runtime.get_stall_limit_s() == 120.0


def test_stall_limit_rejects_non_positive_values(cfg_dir):
    with pytest.raises(ValueError):
        runtime.set_stall_limit_s(0)
    with pytest.raises(ValueError):
        runtime.set_stall_limit_s(-5)


def test_config_file_has_owner_only_permissions(cfg_dir):
    """The settings file may hold the Gemini key in plain text: restrict it to 600."""
    runtime.set_gemini_key("super-secret")
    path = cfg_dir / "app_settings.json"
    assert path.exists()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_config_file_permissions_fixed_even_if_already_looser(cfg_dir):
    """An older file saved before this change (default umask) gets locked down too."""
    runtime.set_eval_embedding("e5")
    path = cfg_dir / "app_settings.json"
    path.chmod(0o644)
    runtime.set_stall_limit_s(300.0)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
