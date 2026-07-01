"""Tests for the file-backed prompt loader."""
import pytest

from app.core.prompts import (
    DEFAULT_PROMPTS,
    PROMPT_SPECS,
    load_all,
    load_prompt,
    load_technique,
    save_prompt,
    validate_placeholders,
)


@pytest.fixture(autouse=True)
def prompts_tmp(tmp_path, monkeypatch):
    """Point the loader at a temp dir so tests never touch repo files."""
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return tmp_path


def test_load_prompt_falls_back_to_default_when_file_absent():
    assert load_prompt("naive", "answer") == DEFAULT_PROMPTS["naive"]["answer"]


def test_save_then_load_roundtrip(prompts_tmp):
    text = "New answer using {context} and {question}."
    save_prompt("naive", "answer", text)
    assert (prompts_tmp / "naive" / "answer.md").exists()
    assert load_prompt("naive", "answer") == text


def test_load_technique_returns_all_keys():
    result = load_technique("agentic")
    assert set(result) == {"decide", "answer"}


def test_load_all_covers_manifest():
    result = load_all()
    assert set(result) == set(PROMPT_SPECS)
    assert set(result["multi_query"]) == {"generate"}


def test_validate_placeholders_accepts_extra_but_requires_mandatory():
    validate_placeholders("naive", "answer", "{context} {question} {extra}")
    with pytest.raises(ValueError, match="context"):
        validate_placeholders("naive", "answer", "only {question}")


def test_save_prompt_rejects_missing_placeholder(prompts_tmp):
    with pytest.raises(ValueError):
        save_prompt("multi_query", "generate", "no placeholders here")


def test_unknown_prompt_raises_keyerror():
    with pytest.raises(KeyError):
        load_prompt("naive", "nope")
