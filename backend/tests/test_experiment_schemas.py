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


def test_parse_questions_csv_splits_reference_evidence_on_pipes():
    content = (
        "pergunta,resposta_referencia,evidencia_referencia\n"
        "Onde fica o centro?,Na praca,Trecho um | Trecho dois |\n"
        "Tem wifi?,,\n"
    )
    items = parse_questions_csv(content)
    assert items[0].evidence == ["Trecho um", "Trecho dois"]
    assert items[1].evidence is None


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
        llms=["qwen3:1.7b"],
    )
    assert config.name is None
    assert config.eval_embedding is None  # the API fills in the saved default


def test_experiment_config_requires_at_least_one_llm():
    """No implicit Gemini: an experiment names its models (local ones need no key)."""
    from pydantic import ValidationError

    base = dict(base="viagem", chunkings=["recursive"], embeddings=["e5"],
                rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"])
    with pytest.raises(ValidationError):
        ExperimentConfig(**base)
    with pytest.raises(ValidationError):
        ExperimentConfig(**base, llms=[])


def test_experiment_config_parses_llms_list():
    from app.experiments.schemas import ExperimentConfig

    cfg = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
        llms=["gemini", "ollama"],
    )
    assert cfg.llms == ["gemini", "ollama"]
