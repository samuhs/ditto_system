"""Tests for embedding-based evaluation metrics (no reference needed)."""
from app.core.evaluation.base import EvalSample, build_evaluator, evaluation_registry
from app.core.evaluation.embedding_metrics import (
    AnswerCorrectness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)


class _FakeEmbedder:
    """Embeds text to a 2-dim topic vector: 'square'->[1,0], 'cheese'->[0,1]."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        t = text.lower()
        x = 1.0 if "square" in t else 0.0
        y = 1.0 if "cheese" in t else 0.0
        if x == 0.0 and y == 0.0:
            return [0.5, 0.5]
        return [x, y]

    @property
    def dimension(self) -> int:
        return 2


def test_answer_relevancy_higher_when_on_topic():
    embedder = _FakeEmbedder()
    metric = AnswerRelevancy(embedder)
    on_topic = metric.score(
        EvalSample(question="Where is the square?", answer="The square is downtown.", contexts=[])
    )
    off_topic = metric.score(
        EvalSample(question="Where is the square?", answer="We sell cheese.", contexts=[])
    )
    assert on_topic > off_topic


def test_faithfulness_higher_when_grounded():
    embedder = _FakeEmbedder()
    metric = Faithfulness(embedder)
    grounded = metric.score(
        EvalSample(question="q", answer="The square is here.", contexts=["The main square map."])
    )
    ungrounded = metric.score(
        EvalSample(question="q", answer="The square is here.", contexts=["We sell cheese."])
    )
    assert grounded > ungrounded


def test_context_precision_averages_relevance():
    embedder = _FakeEmbedder()
    metric = ContextPrecision(embedder)
    score = metric.score(
        EvalSample(
            question="Where is the square?",
            answer="a",
            contexts=["The square map.", "The square plaza."],
        )
    )
    assert score > 0.9


def test_answer_correctness_higher_when_matching_reference():
    embedder = _FakeEmbedder()
    metric = AnswerCorrectness(embedder)
    assert metric.requires_reference is True
    close = metric.score(
        EvalSample(question="q", answer="the square", contexts=[], reference_answer="the square plaza")
    )
    far = metric.score(
        EvalSample(question="q", answer="the square", contexts=[], reference_answer="the cheese shop")
    )
    assert close > far


def test_context_recall_uses_reference_and_context():
    embedder = _FakeEmbedder()
    metric = ContextRecall(embedder)
    assert metric.requires_reference is True
    covered = metric.score(
        EvalSample(
            question="q",
            answer="a",
            contexts=["the square map"],
            reference_answer="the square plaza",
        )
    )
    assert covered > 0.9


def test_embedding_metrics_registered_and_no_reference():
    assert {"answer_relevancy", "faithfulness", "context_precision"} <= set(
        evaluation_registry.names()
    )
    metric = build_evaluator("faithfulness", embedder=_FakeEmbedder())
    assert metric.requires_reference is False
