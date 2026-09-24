"""Memory profile selection and env overrides."""
import pytest

from app.core.config.settings import get_settings
from app.core.memory.profile import PROFILES, active_profile


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_profile_is_standard():
    assert active_profile() == PROFILES["standard"]


def test_low_profile_limits(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    profile = active_profile()
    assert (profile.name, profile.max_local_models, profile.embedding_device, profile.max_concurrency) == (
        "low", 1, "cpu", 2,
    )


def test_profile_name_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", " Low ")
    assert active_profile().name == "low"


def test_unknown_profile_falls_back_to_standard(monkeypatch, caplog):
    monkeypatch.setenv("MEMORY_PROFILE", "lwo")
    assert active_profile().name == "standard"
    assert "lwo" in caplog.text


def test_explicit_env_values_override_the_profile(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    monkeypatch.setenv("MAX_LOCAL_MODELS", "2")
    monkeypatch.setenv("MAX_EXPERIMENT_CONCURRENCY", "4")
    profile = active_profile()
    assert (profile.max_local_models, profile.max_concurrency) == (2, 4)


def test_empty_env_values_mean_unset(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    monkeypatch.setenv("MAX_LOCAL_MODELS", "")
    monkeypatch.setenv("EMBEDDING_DEVICE", "")
    assert active_profile() == PROFILES["low"]


def test_embedding_device_cannot_force_the_gpu(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    monkeypatch.setenv("EMBEDDING_DEVICE", "mps")
    assert active_profile().embedding_device == "cpu"
    monkeypatch.setenv("MEMORY_PROFILE", "standard")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    get_settings.cache_clear()
    assert active_profile().embedding_device == "cpu"
