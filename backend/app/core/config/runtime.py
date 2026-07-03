"""Runtime-editable app settings, backed by a JSON file (env fallback for secrets)."""
import json
import os
import re
from pathlib import Path

from app.core.config.settings import get_settings

_ID_RE = re.compile(r"^[\w-]+$")


def config_dir() -> Path:
    """Directory holding the runtime settings file (env APP_CONFIG_DIR overrides)."""
    env = os.environ.get("APP_CONFIG_DIR")
    if env:
        return Path(env)
    # runtime.py is at <root>/app/core/config/runtime.py -> backend root is parents[3]
    return Path(__file__).resolve().parents[3] / "config"


def _config_path() -> Path:
    return config_dir() / "app_settings.json"


def load_config() -> dict:
    """Read the settings file; return {} if absent or unreadable."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict) -> None:
    """Persist the whole settings dict as pretty JSON."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_gemini_key() -> str | None:
    """The runtime Gemini key if set (non-empty), else the env default (or None)."""
    key = load_config().get("gemini_api_key") or get_settings().gemini_api_key
    return key or None


def set_gemini_key(key: str | None) -> None:
    """Set (or clear, when falsy) the runtime Gemini key."""
    data = load_config()
    if key:
        data["gemini_api_key"] = key
    else:
        data.pop("gemini_api_key", None)
    save_config(data)


def get_ollama_models() -> list[dict]:
    """The list of named Ollama models ([{id, model}, ...])."""
    return load_config().get("ollama_models", [])


def validate_ollama_models(models: list[dict], reserved: set[str]) -> None:
    """Raise ValueError if any entry is malformed, duplicated, or reserved."""
    seen: set[str] = set()
    for entry in models:
        mid = entry.get("id", "")
        model = entry.get("model", "")
        if not _ID_RE.match(mid):
            raise ValueError(f"invalid model id: {mid!r}")
        if not model:
            raise ValueError(f"empty model for id: {mid!r}")
        if mid in reserved:
            raise ValueError(f"id conflicts with a built-in provider: {mid!r}")
        if mid in seen:
            raise ValueError(f"duplicate model id: {mid!r}")
        seen.add(mid)


def set_ollama_models(models: list[dict], reserved: set[str] | None = None) -> None:
    """Validate and persist the named Ollama models."""
    validate_ollama_models(models, reserved or set())
    data = load_config()
    data["ollama_models"] = [{"id": m["id"], "model": m["model"]} for m in models]
    save_config(data)
