"""Tests for experiment schemas, naming, and CSV parsing."""
import pytest

from app.experiments.csv_loader import parse_questions_csv
from app.experiments.naming import generate_experiment_name
from app.experiments.schemas import ExperimentConfig, QuestionItem


def test_generate_experiment_name_format():
    name = generate_experiment_name()
    parts = name.split("-")
    assert len(parts) == 3
    assert parts[2].isdigit()
    assert len(parts[2]) == 2


def test_parse_questions_csv_missing_column_raises():
    with pytest.raises(ValueError):
        parse_questions_csv("wrong_header\nsome value\n")


def test_generate_experiment_name_varies():
    names = {generate_experiment_name() for _ in range(20)}
    assert len(names) > 1


def test_parse_questions_csv_with_and_without_reference():
    content = (
        "pergunta,resposta_referencia\n"
        "Onde fica o centro?,Na praca da matriz\n"
        "Tem wifi?,\n"
    )
    items = parse_questions_csv(content)
    assert len(items) == 2
    assert items[0] == QuestionItem(text="Onde fica o centro?", reference="Na praca da matriz")
    assert items[1] == QuestionItem(text="Tem wifi?", reference=None)


def test_parse_questions_csv_skips_blank_rows():
    content = "pergunta,resposta_referencia\n,ignored\nValid question?,\n"
    items = parse_questions_csv(content)
    assert [i.text for i in items] == ["Valid question?"]


def test_experiment_config_defaults():
    config = ExperimentConfig(
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    assert config.name is None
    assert config.llms == ["gemini"]
    assert config.eval_embedding == "gemini"


def test_experiment_config_llms_defaults_to_gemini():
    from app.experiments.schemas import ExperimentConfig

    cfg = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
    )
    assert cfg.llms == ["gemini"]


def test_experiment_config_parses_llms_list():
    from app.experiments.schemas import ExperimentConfig

    cfg = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
        llms=["gemini", "ollama"],
    )
    assert cfg.llms == ["gemini", "ollama"]
