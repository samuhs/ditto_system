"""File-backed persona system prompts with built-in defaults."""
import re
from pathlib import Path

from app.core.prompts import prompts_dir

_VALID_NAME = re.compile(r"^[\w-]+$")

DEFAULT_PERSONAS: dict[str, str] = {
    "travel_guide": (
        "Você é um guia de viagem simpático e prestativo. Responda em português, "
        "de forma conversacional, ajudando o usuário a planejar e conhecer o destino. "
        "Baseie as informações específicas sobre o destino na informação de apoio "
        "que acompanha a mensagem. Se ela não bastar, diga o que sabe e seja honesto "
        "sobre os limites."
    ),
    "assistant": (
        "Você é um assistente prestativo e objetivo. Responda em português. "
        "Quando a pergunta depender de informações específicas do domínio, baseie "
        "a resposta na informação de apoio que acompanha a mensagem."
    ),
}


def personas_dir() -> Path:
    """Directory holding persona .md files (under the shared prompts dir)."""
    return prompts_dir() / "personas"


def list_personas() -> list[str]:
    """Persona names: built-in defaults plus any .md files present."""
    names = set(DEFAULT_PERSONAS)
    directory = personas_dir()
    if directory.exists():
        names.update(p.stem for p in directory.glob("*.md"))
    return sorted(names)


def load_persona(name: str) -> str:
    """Return a persona's system prompt; file wins over default. KeyError if unknown."""
    path = personas_dir() / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").rstrip("\n")
    if name in DEFAULT_PERSONAS:
        return DEFAULT_PERSONAS[name]
    raise KeyError(f"unknown persona: {name}")


def save_persona(name: str, text: str) -> None:
    """Write a persona's .md file. Raises ValueError for an invalid name."""
    if not _VALID_NAME.match(name):
        raise ValueError(f"invalid persona name: {name}")
    path = personas_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
