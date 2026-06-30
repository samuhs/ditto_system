"""Embedding-based evaluation metrics (cosine similarity of meanings)."""
from app.core.embedding.base import Embedder
from app.core.evaluation.base import EvalSample, Evaluator, evaluation_registry
from app.core.vector_math import cosine_similarity


def _clamp(value: float) -> float:
    """Clamp a similarity to the non-negative [0, 1] range used for scores."""
    return max(0.0, value)


class _EmbeddingMetric(Evaluator):
    """Base class for metrics that embed text and compare with cosine similarity."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder


class AnswerRelevancy(_EmbeddingMetric):
    """How well the answer addresses the question."""

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the answer and the question."""
        answer_vec = self._embedder.embed_query(sample.answer)
        question_vec = self._embedder.embed_query(sample.question)
        return _clamp(cosine_similarity(answer_vec, question_vec))


class Faithfulness(_EmbeddingMetric):
    """How grounded the answer is in the retrieved context."""

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the answer and the joined contexts."""
        if not sample.contexts:
            return 0.0
        answer_vec = self._embedder.embed_query(sample.answer)
        context_vec = self._embedder.embed_query(" ".join(sample.contexts))
        return _clamp(cosine_similarity(answer_vec, context_vec))


class ContextPrecision(_EmbeddingMetric):
    """How relevant the retrieved contexts are to the question."""

    def score(self, sample: EvalSample) -> float:
        """Mean cosine similarity between the question and each context."""
        if not sample.contexts:
            return 0.0
        question_vec = self._embedder.embed_query(sample.question)
        scores = [
            cosine_similarity(question_vec, self._embedder.embed_query(context))
            for context in sample.contexts
        ]
        return _clamp(sum(scores) / len(scores))


evaluation_registry.register("answer_relevancy", AnswerRelevancy)
evaluation_registry.register("faithfulness", Faithfulness)
evaluation_registry.register("context_precision", ContextPrecision)
