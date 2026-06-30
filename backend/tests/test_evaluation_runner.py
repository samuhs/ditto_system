"""Tests for the evaluation runner."""
from app.core.evaluation.base import EvalSample
from app.core.evaluation.runner import evaluate_sample


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [1.0, 0.0] if "square" in text.lower() else [0.0, 1.0]

    @property
    def dimension(self) -> int:
        return 2


def test_runner_computes_selected_metrics():
    sample = EvalSample(
        question="Where is the square?",
        answer="The square is downtown.",
        contexts=["The main square map."],
        reference_answer="The square plaza.",
    )
    scores = evaluate_sample(
        sample,
        ["answer_relevancy", "faithfulness", "rouge_l"],
        embedder=_FakeEmbedder(),
    )
    assert set(scores) == {"answer_relevancy", "faithfulness", "rouge_l"}
    assert all(isinstance(v, float) for v in scores.values())


def test_runner_skips_reference_metrics_without_reference():
    sample = EvalSample(
        question="Where is the square?",
        answer="The square is downtown.",
        contexts=["The main square map."],
        reference_answer=None,
    )
    scores = evaluate_sample(
        sample,
        ["answer_relevancy", "answer_correctness", "rouge_l"],
        embedder=_FakeEmbedder(),
    )
    assert set(scores) == {"answer_relevancy"}  # reference-based ones skipped
