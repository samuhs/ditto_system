"""File-backed prompt templates with built-in defaults and placeholder validation."""
import os
import re
from pathlib import Path

# Required placeholders per technique/key.
PROMPT_SPECS: dict[str, dict[str, set[str]]] = {
    "naive": {"answer": {"context", "question"}},
    "agentic": {
        "decide": {"question", "context"},
        "answer": {"context", "question"},
    },
    "multi_query": {"generate": {"n", "question"}},
    "hyde": {"hypothesis": {"question"}, "answer": {"context", "question"}},
}

# Built-in fallbacks (used when a .md file is absent).
DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "naive": {
        "answer": (
            "Use the context below to answer the question. If the context is not "
            "enough, say what you can.\n\nContext:\n{context}\n\n"
            "Question: {question}\n\nAnswer:"
        ),
    },
    "agentic": {
        "decide": (
            "You are answering a question using retrieved context. Based on the "
            "context so far, decide your next action. Reply with exactly one line:\n"
            "'SEARCH: <a better search query>' if you need more information, or\n"
            "'ANSWER: <your final answer>' if the context is sufficient.\n\n"
            "Question: {question}\n\nContext so far:\n{context}"
        ),
        "answer": (
            "Answer the question using the context.\n\nContext:\n{context}\n\n"
            "Question: {question}\n\nAnswer:"
        ),
    },
    "multi_query": {
        "generate": (
            "Generate {n} alternative search queries, one per line, that rephrase "
            "the following question to improve document retrieval. Question: {question}"
        ),
    },
    "hyde": {
        "hypothesis": (
            "Escreva um paragrafo hipotetico, como se fosse um trecho de documento, "
            "que responderia a pergunta abaixo. Escreva como um texto informativo "
            "direto, sem dizer que e hipotetico.\n\nPergunta: {question}\n\nParagrafo:"
        ),
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
}

_PLACEHOLDER_RE = re.compile(r"{(\w+)}")


def prompts_dir() -> Path:
    """Root directory of prompt files (env PROMPTS_DIR overrides the default)."""
    env = os.environ.get("PROMPTS_DIR")
    if env:
        return Path(env)
    # loader.py is at <root>/app/core/prompts/loader.py -> root is parents[3]
    return Path(__file__).resolve().parents[3] / "prompts"


def _check_known(technique: str, key: str) -> None:
    if technique not in PROMPT_SPECS or key not in PROMPT_SPECS[technique]:
        raise KeyError(f"unknown prompt: {technique}/{key}")


def load_prompt(technique: str, key: str) -> str:
    """Read a prompt's .md; fall back to the built-in default when absent."""
    _check_known(technique, key)
    path = prompts_dir() / technique / f"{key}.md"
    if path.exists():
        # rstrip trailing newlines so file-loaded text matches DEFAULT_PROMPTS
        # and roundtrips (save then load) are deterministic.
        return path.read_text(encoding="utf-8").rstrip("\n")
    return DEFAULT_PROMPTS[technique][key]


def load_technique(technique: str) -> dict[str, str]:
    """All prompts for one technique."""
    if technique not in PROMPT_SPECS:
        raise KeyError(f"unknown technique: {technique}")
    return {key: load_prompt(technique, key) for key in PROMPT_SPECS[technique]}


def load_all() -> dict[str, dict[str, str]]:
    """All prompts for every technique in the manifest."""
    return {technique: load_technique(technique) for technique in PROMPT_SPECS}


def validate_placeholders(technique: str, key: str, text: str) -> None:
    """Raise ValueError if any required placeholder is missing from text."""
    _check_known(technique, key)
    present = set(_PLACEHOLDER_RE.findall(text))
    missing = PROMPT_SPECS[technique][key] - present
    if missing:
        raise ValueError(
            f"prompt {technique}/{key} missing required placeholder(s): "
            + ", ".join("{" + m + "}" for m in sorted(missing))
        )


def save_prompt(technique: str, key: str, text: str) -> None:
    """Validate placeholders and write the prompt's .md file."""
    _check_known(technique, key)
    validate_placeholders(technique, key, text)
    path = prompts_dir() / technique / f"{key}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
