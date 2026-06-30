"""Tests for overlap-based evaluation metrics (ROUGE-L)."""
from app.core.evaluation.base import EvalSample, evaluation_registry
from app.core.evaluation.overlap_metrics import RougeL


def test_rouge_l_identical_is_one():
    metric = RougeL()
    sample = EvalSample(
        question="q", answer="the cat sat", contexts=[], reference_answer="the cat sat"
    )
    assert metric.score(sample) == 1.0


def test_rouge_l_partial_overlap_between_zero_and_one():
    metric = RougeL()
    sample = EvalSample(
        question="q",
        answer="the cat sat on the mat",
        contexts=[],
        reference_answer="the dog sat",
    )
    score = metric.score(sample)
    assert 0.0 < score < 1.0


def test_rouge_l_disjoint_is_zero():
    metric = RougeL()
    sample = EvalSample(
        question="q", answer="alpha beta", contexts=[], reference_answer="gamma delta"
    )
    assert metric.score(sample) == 0.0


def test_rouge_l_requires_reference_and_registered():
    assert "rouge_l" in evaluation_registry.names()
    assert RougeL.requires_reference is True
