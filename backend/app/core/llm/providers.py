"""LLM providers as configuration: any model behind any provider, with no provider classes.

A provider is data: a kind, a base URL, an API key, the models it offers and the extra
LangChain keyword arguments its requests need. `kind` is either "custom" (any
OpenAI-compatible endpoint, such as OpenRouter, vLLM, a DeepSeek or GLM API, or a local
MLX/Ollama server) or the name of a LangChain chat-model provider ("openai",
"google_genai", "anthropic", "mistralai", ...), which `init_chat_model` builds directly.

Two providers are built in and need no configuration: "local" (the MLX/Ollama server of
the settings) and "gemini" (when a Gemini key is set). Users add the others; they live in
the runtime settings file (owner-only permissions), and a key may instead come from an
environment variable named in `api_key_env`.

An LLM is named "<provider>::<model>" (e.g. "openrouter::qwen/qwen3.5-9b"). Bare names keep
their old meaning, so stored experiments still resolve: "gemini" or "gemini-*" -> the
Gemini provider; "<model>:<tag>" or "<org>/<repo>" -> the local server.
"""
import os
import re
from dataclasses import dataclass, field

from app.core.config import runtime
from app.core.config.settings import get_settings

SEPARATOR = "::"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
RESERVED_IDS = ("local", "gemini")
KINDS_HELP = "custom (OpenAI-compatible URL) or a LangChain provider name (openai, google_genai, anthropic, ...)"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
# Constructor arguments the provider's own fields set; `params` may not override them.
_FIELD_ARGS = {"model", "model_provider", "api_key", "base_url"}


@dataclass(frozen=True)
class Provider:
    id: str
    kind: str
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    models: tuple[str, ...] = ()
    # Extra LangChain constructor kwargs, e.g. {"extra_body": {"reasoning": {"enabled": False}}}.
    params: dict = field(default_factory=dict)
    local: bool = False
    # Send max_tokens in the raw request body instead of the typed argument. Ollama ignores
    # the max_completion_tokens that langchain-openai sends for a typed max_tokens; most
    # OpenAI-compatible servers read max_tokens. None: in the body for "custom", typed otherwise.
    max_tokens_in_body: bool | None = None
    builtin: bool = False

    def resolved_key(self) -> str | None:
        """The API key: the stored one, else the named environment variable (or .env entry)."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env) or _dotenv_value(self.api_key_env)
        return None

    def tokens_in_body(self) -> bool:
        return self.kind == "custom" if self.max_tokens_in_body is None else self.max_tokens_in_body

    def public(self) -> dict:
        """The provider without its secret, for the API."""
        return {
            "id": self.id, "kind": self.kind, "base_url": self.base_url, "api_key_env": self.api_key_env,
            "api_key_set": self.resolved_key() is not None, "models": list(self.models),
            "params": self.params, "local": self.local, "max_tokens_in_body": self.max_tokens_in_body,
            "builtin": self.builtin,
        }


def _dotenv_value(name: str) -> str | None:
    """A key from the project .env, for an API started without exporting it."""
    env_file = os.environ.get("ENV_FILE", ".env")
    if not env_file:
        return None
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - python-dotenv ships with pydantic-settings
        return None
    for path in (env_file, os.path.join("..", env_file)):
        if os.path.exists(path):
            value = dotenv_values(path).get(name)
            if value:
                return value
    return None


def builtin_providers() -> dict[str, Provider]:
    settings = get_settings()
    local = Provider(
        id="local", kind="custom", base_url=settings.ollama_base_url, api_key="ollama",
        local=True, max_tokens_in_body=True, builtin=True,
    )
    gemini = Provider(
        id="gemini", kind="google_genai", api_key=runtime.get_gemini_key(),
        models=(DEFAULT_GEMINI_MODEL,), builtin=True,
    )
    return {"local": local, "gemini": gemini}


def _from_dict(provider_id: str, data: dict) -> Provider:
    return Provider(
        id=provider_id, kind=data["kind"], base_url=data.get("base_url") or None,
        api_key=data.get("api_key") or None, api_key_env=data.get("api_key_env") or None,
        models=tuple(data.get("models") or ()), params=dict(data.get("params") or {}),
        local=bool(data.get("local", False)), max_tokens_in_body=data.get("max_tokens_in_body"),
    )


def user_providers() -> dict[str, Provider]:
    stored = runtime.load_config().get("llm_providers") or {}
    return {pid: _from_dict(pid, data) for pid, data in sorted(stored.items())}


def all_providers() -> dict[str, Provider]:
    return {**builtin_providers(), **user_providers()}


def get_provider(provider_id: str) -> Provider:
    providers = all_providers()
    if provider_id not in providers:
        raise KeyError(f"unknown LLM provider: {provider_id!r}")
    return providers[provider_id]


def validate(provider_id: str, data: dict) -> None:
    """Raise ValueError if the provider definition is unusable."""
    if not _ID_RE.match(provider_id):
        raise ValueError("o id do provedor usa só letras minúsculas, números e hífen (até 40)")
    if provider_id in RESERVED_IDS:
        raise ValueError(f"o id {provider_id!r} é reservado a um provedor embutido")
    kind = (data.get("kind") or "").strip()
    if not kind:
        raise ValueError(f"informe o tipo do provedor: {KINDS_HELP}")
    if kind == "custom" and not data.get("base_url"):
        raise ValueError("um provedor custom precisa da base_url do endpoint compatível com OpenAI")
    clash = _FIELD_ARGS & set(data.get("params") or {})
    if clash:
        raise ValueError(f"params não pode definir {sorted(clash)}: use os campos do provedor")
    if any(not isinstance(m, str) or not m.strip() or SEPARATOR in m for m in data.get("models") or []):
        raise ValueError("cada modelo é um nome não vazio, sem '::'")


def save_provider(provider_id: str, data: dict) -> Provider:
    """Create or replace a user provider. An absent api_key keeps the stored one; "" clears it."""
    validate(provider_id, data)
    config = runtime.load_config()
    stored = config.setdefault("llm_providers", {})
    previous = stored.get(provider_id, {})
    entry = {
        "kind": data["kind"].strip(), "base_url": (data.get("base_url") or "").strip() or None,
        "api_key_env": (data.get("api_key_env") or "").strip() or None,
        "models": [m.strip() for m in data.get("models") or []], "params": data.get("params") or {},
        "local": bool(data.get("local", False)), "max_tokens_in_body": data.get("max_tokens_in_body"),
    }
    if "api_key" in data and data["api_key"] is not None:
        if data["api_key"]:
            entry["api_key"] = data["api_key"]
    elif previous.get("api_key"):
        entry["api_key"] = previous["api_key"]
    stored[provider_id] = entry
    runtime.save_config(config)
    return _from_dict(provider_id, entry)


def delete_provider(provider_id: str) -> bool:
    config = runtime.load_config()
    stored = config.get("llm_providers") or {}
    if provider_id not in stored:
        return False
    del stored[provider_id]
    runtime.save_config(config)
    return True


def split_llm_name(name: str) -> tuple[Provider, str]:
    """(provider, model) for an LLM name; KeyError if no provider serves it."""
    if SEPARATOR in name:
        provider_id, model = name.split(SEPARATOR, 1)
        return get_provider(provider_id), model
    if name == "gemini":
        return get_provider("gemini"), DEFAULT_GEMINI_MODEL
    if name.startswith("gemini-"):
        return get_provider("gemini"), name
    if ":" in name or "/" in name:
        return get_provider("local"), name
    raise KeyError(f"unknown LLM: {name!r} (use <provedor>::<modelo>)")


def llm_name(provider_id: str, model: str) -> str:
    return f"{provider_id}{SEPARATOR}{model}"
