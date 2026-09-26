"""Tests for the observed per-question difficulty aggregation."""
import pytest

from app.core.db.models import Experiment, ExperimentRun, QuestionProfile, RunResult
from app.experiments.difficulty import question_difficulty


def _run(rag, llm, results):
    run = ExperimentRun(chunking="recursive", embedding="e5", rag_technique=rag,
                        retriever="similarity", llm=llm, status="done")
    run.results = [
        RunResult(question=q, generated_answer=a, scores=s, retrieval_signals=sig)
        for q, a, s, sig in results
    ]
    return run


def test_difficulty_splits_retrieval_closed_book_and_evidence(db_session):
    experiment = Experiment(name="d", status="done", config={})
    experiment.question_profiles = [QuestionProfile(question="Q1", signals={"negation": 1.0})]
    experiment.runs = [
        _run("naive", "qwen3:1.7b", [
            ("Q1", "a", {"chrf": 0.8, "context_hit": 1.0}, {"top_score": 0.9}),
            ("Q2", "a", {"chrf": 0.1, "context_hit": 0.0}, {"top_score": 0.5}),
        ]),
        _run("rerank", "qwen3:1.7b", [
            ("Q1", "a", {"chrf": 0.4, "context_hit": 0.0}, {"top_score": 0.7}),
            ("Q1", "[ERRO: timeout]", {}, None),
        ]),
        _run("closed_book", "qwen3:1.7b", [("Q1", "não sei", {"chrf": 0.05}, {})]),
        _run("oracle", "qwen3:1.7b", [("Q1", "a", {"chrf": 0.95}, {})]),
    ]
    db_session.add(experiment)
    db_session.commit()

    report = question_difficulty(experiment)
    assert report["llms"] == ["qwen3:1.7b"]
    assert report["metrics"] == ["chrf", "context_hit"]
    q1 = next(q for q in report["questions"] if q["question"] == "Q1")
    assert q1["signals"] == {"negation": 1.0}
    assert q1["retrieval_signals"]["top_score"] == pytest.approx(0.8)
    cell = q1["by_llm"]["qwen3:1.7b"]
    assert cell["retrieval"]["chrf"]["mean"] == pytest.approx(0.6)
    assert cell["retrieval"]["chrf"]["n"] == 2  # the error row is left out
    assert cell["closed_book"] == {"chrf": 0.05}
    assert cell["oracle"] == {"chrf": 0.95}
    assert cell["hit_rate"] == 0.5
    assert cell["with_evidence"]["chrf"] == 0.8
    assert cell["without_evidence"]["chrf"] == 0.4


def test_hit_rate_is_none_without_gold_metrics(db_session):
    experiment = Experiment(name="d2", status="done", config={})
    experiment.runs = [_run("naive", "gemini", [("Q", "a", {"chrf": 0.5}, None)])]
    db_session.add(experiment)
    db_session.commit()
    cell = question_difficulty(experiment)["questions"][0]["by_llm"]["gemini"]
    assert cell["hit_rate"] is None and cell["with_evidence"] == {}


def test_irt_ranks_questions_on_the_chosen_metric(db_session):
    experiment = Experiment(name="irt", status="done", config={})
    experiment.runs = [
        _run("naive", "gemini", [("Fácil", "a", {"chrf": 0.9, "rouge_l": 0.1}, None),
                                 ("Difícil", "a", {"chrf": 0.2, "rouge_l": 0.8}, None)]),
        _run("rerank", "gemini", [("Fácil", "a", {"chrf": 0.8, "rouge_l": 0.2}, None),
                                  ("Difícil", "a", {"chrf": 0.1, "rouge_l": 0.9}, None)]),
        _run("closed_book", "gemini", [("Fácil", "a", {"chrf": 0.0}, None)]),
    ]
    db_session.add(experiment)
    db_session.commit()

    report = question_difficulty(experiment)
    irt = report["irt"]
    assert report["metric"] == irt["metric"] == "chrf"
    assert irt["difficulty"]["Difícil"] > irt["difficulty"]["Fácil"]
    assert irt["difficulty_by_llm"]["gemini"]["Difícil"] > irt["difficulty_by_llm"]["gemini"]["Fácil"]
    assert irt["n_configurations"] == 2  # closed book is not a respondent
    assert irt["reliable"] is False

    flipped = question_difficulty(experiment, "rouge_l")["irt"]
    assert flipped["difficulty"]["Fácil"] > flipped["difficulty"]["Difícil"]


def test_spearman_handles_ties_and_constants():
    from app.experiments.difficulty import spearman

    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert spearman([1, 2], [1, 2]) is None


def test_signals_are_correlated_with_irt_difficulty(db_session):
    experiment = Experiment(name="corr", status="done", config={})
    scores = {"Q1": 0.9, "Q2": 0.6, "Q3": 0.3, "Q4": 0.1}
    experiment.question_profiles = [
        QuestionProfile(question=q, signals={"question_length": float(i), "negation": 0.0},
                        model_signals={"org/small": {"perplexity": 5.0 + i}})
        for i, q in enumerate(scores)
    ]
    experiment.runs = [
        _run(rag, llm, [(q, "a", {"chrf": s + shift}, {"top_score": 1 - s}) for q, s in scores.items()])
        for rag, shift in [("naive", 0.0), ("rerank", -0.05)]
        for llm in ["org/small", "gemini"]
    ]
    db_session.add(experiment)
    db_session.commit()

    corr = question_difficulty(experiment)["correlations"]
    rows = {(r["kind"], r["signal"]): r for r in corr["rows"]}
    assert rows[("question", "question_length")]["overall"] == pytest.approx(1.0)
    assert rows[("question", "negation")]["overall"] is None  # constant signal
    assert rows[("retrieval", "top_score")]["by_llm"]["gemini"] == pytest.approx(1.0)
    perplexity = rows[("model", "perplexity")]
    assert perplexity["overall"] is None
    assert perplexity["by_llm"]["org/small"] == pytest.approx(1.0)
    assert perplexity["by_llm"]["gemini"] is None
    assert corr["n_questions"] == 4 and corr["reliable"] is False
