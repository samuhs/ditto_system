"""Add, remove or list the named Ollama models in the app settings file.

Usage: python3 scripts/app_models.py add|remove|list [MODEL] [ID]
The API reads backend/config/app_settings.json on every request, so changes
show up in the app without a restart. Stdlib only (runs on the host).
"""
import json
import re
import sys
from pathlib import Path

SETTINGS = Path(__file__).resolve().parents[1] / "backend" / "config" / "app_settings.json"
RESERVED = {"gemini", "ollama", "custom"}  # built-in LLM provider names


def _load() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}


def _save(data: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def add(model: str, mid: str | None = None) -> str:
    model = _normalize(model)
    data = _load()
    models = data.setdefault("ollama_models", [])
    existing = next((m for m in models if m.get("model") == model), None)
    if existing:
        return f"já registrado no app como '{existing['id']}'"
    mid = mid or re.sub(r"[^\w-]", "-", model.removesuffix(":latest"))
    if not re.fullmatch(r"[\w-]+", mid):
        raise SystemExit(f"id inválido: {mid!r} (use letras, números, _ ou -)")
    if mid in RESERVED or any(m.get("id") == mid for m in models):
        mid += "-local"
    models.append({"id": mid, "model": model})
    _save(data)
    return f"registrado no app como '{mid}' (aparece como opção de LLM nos experimentos e no chat)"


def remove(model: str) -> str:
    data = _load()
    models = data.get("ollama_models", [])
    keep = [m for m in models if m.get("model") != _normalize(model) and m.get("id") != model]
    if len(keep) == len(models):
        return "não estava registrado no app"
    data["ollama_models"] = keep
    _save(data)
    return "removido do app"


def list_models() -> str:
    models = _load().get("ollama_models", [])
    if not models:
        return "  (nenhum modelo registrado no app)"
    return "\n".join(f"  {m['id']:<24} {m['model']}" for m in models)


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "add" and args:
        print(add(args[0], args[1] if len(args) > 1 else None))
    elif cmd == "remove" and args:
        print(remove(args[0]))
    elif cmd == "list":
        print(list_models())
    else:
        raise SystemExit(__doc__)
