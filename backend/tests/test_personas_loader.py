"""Tests for the file-backed persona loader."""
import pytest

from app.core.personas import DEFAULT_PERSONAS, list_personas, load_persona


@pytest.fixture(autouse=True)
def personas_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    return tmp_path / "personas"


def test_load_persona_falls_back_to_default():
    assert load_persona("travel_guide") == DEFAULT_PERSONAS["travel_guide"]


def test_list_personas_includes_defaults():
    assert "travel_guide" in list_personas()
    assert "assistant" in list_personas()


def test_list_personas_includes_files(personas_tmp):
    personas_tmp.mkdir(parents=True)
    (personas_tmp / "sac.md").write_text("Você é um atendente de SAC.", encoding="utf-8")
    names = list_personas()
    assert "sac" in names
    assert "travel_guide" in names  # defaults still present


def test_load_persona_reads_file(personas_tmp):
    personas_tmp.mkdir(parents=True)
    (personas_tmp / "travel_guide.md").write_text("CUSTOM guide", encoding="utf-8")
    assert load_persona("travel_guide") == "CUSTOM guide"


def test_unknown_persona_raises_keyerror():
    with pytest.raises(KeyError):
        load_persona("does_not_exist")
