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


def _ref(answer, reference):
    return EvalSample(question="q", answer=answer, contexts=[], reference_answer=reference)


def test_token_f1_ignores_case_punctuation_and_portuguese_articles():
    from app.core.evaluation.overlap_metrics import TokenF1

    sample = _ref("A Rua da Gastronomia!", "rua da gastronomia")
    assert TokenF1().score(sample) == 1.0


def test_token_f1_counts_shared_tokens_as_a_multiset():
    from app.core.evaluation.overlap_metrics import TokenF1

    # shared: {praça, matriz}; precision 2/4, recall 2/2
    sample = _ref("praça matriz praça centro", "praça matriz")
    assert TokenF1().score(sample) == 2 * 0.5 * 1.0 / 1.5


def test_token_f1_disjoint_or_empty_is_zero():
    from app.core.evaluation.overlap_metrics import TokenF1

    assert TokenF1().score(_ref("alfa beta", "gama delta")) == 0.0
    assert TokenF1().score(_ref("...", "gama")) == 0.0


def test_chrf_gives_partial_credit_to_inflected_words():
    from app.core.evaluation.overlap_metrics import ChrF, TokenF1

    sample = _ref("restaurantes típicos", "restaurante típico")
    assert TokenF1().score(sample) == 0.0
    assert 0.5 < ChrF().score(sample) < 1.0


def test_chrf_identical_is_one_and_scaled_to_unit_interval():
    from app.core.evaluation.overlap_metrics import ChrF

    assert ChrF().score(_ref("Praça da Matriz", "Praça da Matriz")) == 1.0


def test_new_lexical_metrics_are_registered_and_need_a_reference():
    from app.core.evaluation.overlap_metrics import ChrF, TokenF1

    assert {"token_f1", "chrf"} <= set(evaluation_registry.names())
    assert TokenF1.requires_reference and ChrF.requires_reference
