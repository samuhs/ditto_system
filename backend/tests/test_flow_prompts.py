"""Tests for the conversation node prompt loader."""
import pytest

from app.core.chat.flow_prompts import (
    DEFAULT_FLOW_PROMPTS,
    FLOW_PROMPT_SPECS,
    load_flow_prompt,
    load_flow_prompts,
    save_flow_prompt,
    validate_flow_placeholders,
)


@pytest.fixture(autouse=True)
def prompts_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return tmp_path / "conversation"


def test_load_falls_back_to_default():
    assert load_flow_prompt("triage") == DEFAULT_FLOW_PROMPTS["triage"]


def test_load_all_covers_manifest():
    assert set(load_flow_prompts()) == set(FLOW_PROMPT_SPECS)


def test_save_then_load_roundtrip(prompts_tmp):
    text = "Classifique: responda RAG ou DIRECT. Mensagem: {question}"
    save_flow_prompt("triage", text)
    assert (prompts_tmp / "triage.md").exists()
    assert load_flow_prompt("triage") == text


def test_validate_requires_mandatory_placeholder():
    validate_flow_placeholders("memory", "Resumo de {history} extra {foo}")
    with pytest.raises(ValueError, match="history"):
        validate_flow_placeholders("memory", "sem placeholder")


def test_save_rejects_missing_placeholder():
    with pytest.raises(ValueError):
        save_flow_prompt("persona_compose", "só {persona} sem question")


def test_unknown_node_raises_keyerror():
    with pytest.raises(KeyError):
        load_flow_prompt("nope")
