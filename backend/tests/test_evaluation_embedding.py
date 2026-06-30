"""Tests for embedding-based evaluation metrics (no reference needed)."""
from app.core.evaluation.base import EvalSample, build_evaluator, evaluation_registry
from app.core.evaluation.embedding_metrics import (
    AnswerRelevancy,
    ContextPrecision,
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


def test_embedding_metrics_registered_and_no_reference():
    assert {"answer_relevancy", "faithfulness", "context_precision"} <= set(
        evaluation_registry.names()
    )
    metric = build_evaluator("faithfulness", embedder=_FakeEmbedder())
    assert metric.requires_reference is False
