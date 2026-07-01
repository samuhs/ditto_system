"""File-backed persona system prompts with built-in defaults."""
from pathlib import Path

from app.core.prompts import prompts_dir

DEFAULT_PERSONAS: dict[str, str] = {
    "travel_guide": (
        "Você é um guia de viagem simpático e prestativo. Responda em português, "
        "de forma conversacional, ajudando o usuário a planejar e conhecer o destino. "
        "Sempre que precisar de informações específicas sobre o destino, use a "
        "ferramenta de busca disponível e baseie a resposta no que encontrar. "
        "Se não houver informação suficiente, diga o que sabe e seja honesto sobre limites."
    ),
    "assistant": (
        "Você é um assistente prestativo e objetivo. Responda em português. "
        "Use a ferramenta de busca para fundamentar respostas quando a pergunta "
        "depender de informações específicas do domínio."
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
