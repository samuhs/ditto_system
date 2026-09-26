"""File-backed prompt templates with built-in defaults and placeholder validation."""
import os
import re
from pathlib import Path

# Required placeholders per technique/key.
PROMPT_SPECS: dict[str, dict[str, set[str]]] = {
    "naive": {"answer": {"context", "question"}},
    "closed_book": {"answer": {"question"}},
    "oracle": {"answer": {"context", "question"}},
    "agentic": {
        "decide": {"question", "context"},
        "answer": {"context", "question"},
    },
    "multi_query": {"generate": {"n", "question"}},
    "hyde": {"hypothesis": {"question"}, "answer": {"context", "question"}},
    "rerank": {"rerank": {"question", "documents"}, "answer": {"context", "question"}},
    "crag": {
        "grade": {"question", "context"},
        "rewrite": {"question"},
        "answer": {"context", "question"},
    },
    "compression": {
        "compress": {"question", "context"},
        "answer": {"context", "question"},
    },
}

# Built-in fallbacks (used when a .md file is absent).
DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "naive": {
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
    "closed_book": {
        "answer": (
            "Responda a pergunta com o que voce sabe. Se nao souber, diga que nao "
            "sabe.\n\nPergunta: {question}\n\nResposta:"
        ),
    },
    "oracle": {
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
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
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
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
    "rerank": {
        "rerank": (
            "Abaixo ha documentos numerados. Ordene-os do mais relevante ao menos "
            "relevante para responder a pergunta. Responda apenas com os numeros "
            "separados por virgula, do mais para o menos relevante (ex.: 2,0,1)."
            "\n\nPergunta: {question}\n\nDocumentos:\n{documents}\n\nOrdem:"
        ),
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
    "crag": {
        "grade": (
            "Avalie se o contexto abaixo e suficiente para responder a pergunta. "
            "Responda comecando exatamente com 'SUFICIENTE' ou 'INSUFICIENTE', "
            "seguido de uma breve justificativa.\n\nPergunta: {question}\n\n"
            "Contexto:\n{context}\n\nAvaliacao:"
        ),
        "rewrite": (
            "A busca anterior nao trouxe contexto suficiente. Reescreva a pergunta "
            "como uma consulta de busca melhor e mais especifica. Responda apenas "
            "com a nova consulta.\n\nPergunta: {question}\n\nNova consulta:"
        ),
        "answer": (
            "Use o contexto abaixo para responder a pergunta. Se o contexto nao for "
            "suficiente, diga o que for possivel.\n\nContexto:\n{context}\n\n"
            "Pergunta: {question}\n\nResposta:"
        ),
    },
    "compression": {
        "compress": (
            "Extraia do contexto abaixo apenas as partes relevantes para responder "
            "a pergunta, descartando o que for irrelevante. Preserve os fatos; nao "
            "invente. Responda apenas com o extrato condensado.\n\n"
            "Pergunta: {question}\n\nContexto:\n{context}\n\nExtrato relevante:"
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
