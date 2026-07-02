"""File-backed prompts for the conversation graph nodes, with defaults + validation."""
import re
from pathlib import Path

from app.core.prompts import prompts_dir

FLOW_PROMPT_SPECS: dict[str, set[str]] = {
    "guardrail": {"question"},
    "triage": {"question"},
    "memory": {"history"},
    "persona_compose": {"persona", "question"},
}

DEFAULT_FLOW_PROMPTS: dict[str, str] = {
    "guardrail": (
        "Você é um filtro de segurança e escopo de um assistente conversacional. "
        "Responda APENAS com 'OK' se a mensagem for apropriada e dentro do escopo, "
        "ou 'BLOCK: <motivo>' se for insegura ou claramente fora do escopo.\n\n"
        "Mensagem: {question}"
    ),
    "triage": (
        "Classifique a mensagem do usuário. Responda APENAS com uma palavra:\n"
        "'RAG' se responder bem exige buscar informação no material do domínio, ou\n"
        "'DIRECT' se é saudação/conversa/algo respondível sem buscar.\n\n"
        "Mensagem: {question}"
    ),
    "memory": (
        "Resuma em poucas frases o histórico de conversa abaixo, mantendo o que "
        "importa para continuar o diálogo. Se estiver vazio, responda com vazio.\n\n"
        "Histórico:\n{history}"
    ),
    "persona_compose": (
        "{persona}\n\n"
        "Resumo da conversa até aqui: {summary}\n\n"
        "Informação de apoio: {context}\n\n"
        "Responda à mensagem do usuário na sua persona, de forma natural e útil.\n\n"
        "Mensagem: {question}"
    ),
}

_PLACEHOLDER_RE = re.compile(r"{(\w+)}")


def conversation_dir() -> Path:
    """Directory holding conversation node prompt files."""
    return prompts_dir() / "conversation"


def _check_known(node: str) -> None:
    if node not in FLOW_PROMPT_SPECS:
        raise KeyError(f"unknown flow node: {node}")


def load_flow_prompt(node: str) -> str:
    """Read a node prompt's .md; fall back to the built-in default when absent."""
    _check_known(node)
    path = conversation_dir() / f"{node}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").rstrip("\n")
    return DEFAULT_FLOW_PROMPTS[node]


def load_flow_prompts() -> dict[str, str]:
    """All node prompts in the manifest."""
    return {node: load_flow_prompt(node) for node in FLOW_PROMPT_SPECS}


def validate_flow_placeholders(node: str, text: str) -> None:
    """Raise ValueError if a required placeholder is missing from text."""
    _check_known(node)
    present = set(_PLACEHOLDER_RE.findall(text))
    missing = FLOW_PROMPT_SPECS[node] - present
    if missing:
        raise ValueError(
            f"flow prompt {node} missing required placeholder(s): "
            + ", ".join("{" + m + "}" for m in sorted(missing))
        )


def save_flow_prompt(node: str, text: str) -> None:
    """Validate placeholders and write the node prompt's .md file."""
    _check_known(node)
    validate_flow_placeholders(node, text)
    path = conversation_dir() / f"{node}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
