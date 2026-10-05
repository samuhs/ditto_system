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


def test_experiment_config_rejects_base_colliding_with_graph_marker():
    """A Base named with the Grafo marker could hide an Índice as if it were a Grafo
    collection (parse_collection_name/collection_base would misread it)."""
    from pydantic import ValidationError

    base = dict(chunkings=["recursive"], embeddings=["e5"], rags=["naive"],
                retrievers=["similarity"], metrics=["answer_relevancy"], llms=["qwen3:1.7b"])
    with pytest.raises(ValidationError):
        ExperimentConfig(base="cidade__kg_x", **base)
    with pytest.raises(ValidationError):
        ExperimentConfig(base="cidade__outraBase", **base)


def test_experiment_config_accepts_current_style_base_names():
    base = dict(chunkings=["recursive"], embeddings=["e5"], rags=["naive"],
                retrievers=["similarity"], metrics=["answer_relevancy"], llms=["qwen3:1.7b"])
    for name in ["viagem", "b", "Santo Antônio da Alegria", "guia-de-viagem"]:
        assert ExperimentConfig(base=name, **base).base == name


def test_experiment_config_parses_llms_list():
    from app.experiments.schemas import ExperimentConfig

    cfg = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
        llms=["gemini", "ollama"],
    )
    assert cfg.llms == ["gemini", "ollama"]


# The techniques that existed before GraphRAG; the combination rule must not move for them.
_PRE_GRAPH_TECHNIQUES = [
    "naive", "closed_book", "oracle", "agentic", "hyde", "rerank", "crag", "compression",
]


def _pre_graph_combinations(config):
    """The combination rule as it was before GraphRAG (frozen copy, the golden master)."""
    import itertools

    from app.core.rag.base import rag_registry
    from app.experiments.schemas import index_pairs

    pairs = index_pairs(config)
    first = (pairs[0], config.retrievers[0])
    for llm, pair, rag, retriever in itertools.product(
        config.llms, pairs, config.rags, config.retrievers
    ):
        if rag_registry.get(rag).uses_retrieval or (pair, retriever) == first:
            yield llm, pair, rag, retriever


def _matrix(**overrides):
    import app.core.rag  # noqa: F401  registers the techniques

    fields = dict(
        base="viagem", chunkings=["recursive", "markdown"], embeddings=["e5", "gemini"],
        rags=_PRE_GRAPH_TECHNIQUES, retrievers=["similarity", "mmr"],
        metrics=["rouge_l"], llms=["qwen3:1.7b", "gemini"],
    )
    return ExperimentConfig(**{**fields, **overrides})


def test_current_techniques_keep_exactly_the_same_combinations():
    from app.experiments.schemas import combinations

    config = _matrix()
    runs = list(combinations(config))
    assert runs == list(_pre_graph_combinations(config))
    # 6 retrieving techniques x 4 indexes x 2 retrievers, plus closed book and oracle once, per LLM.
    assert len(runs) == 2 * (6 * 4 * 2 + 2)


def test_graph_runs_once_per_index_and_llm_without_multiplying_by_retrievers():
    from app.experiments.schemas import combination_count, combinations

    config = _matrix(rags=["graph"], retrievers=["similarity", "mmr", "hybrid"])
    runs = list(combinations(config))
    assert combination_count(config) == len(runs) == 2 * 4
    assert {(llm, pair) for llm, pair, _, _ in runs} == {
        (llm, (c, e))
        for llm in ["qwen3:1.7b", "gemini"]
        for c in ["recursive", "markdown"]
        for e in ["e5", "gemini"]
    }
