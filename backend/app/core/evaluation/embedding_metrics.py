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
            _clamp(cosine_similarity(question_vec, self._embedder.embed_query(context)))
            for context in sample.contexts
        ]
        return sum(scores) / len(scores)


class ContextRecall(_EmbeddingMetric):
    """Whether the retrieved context covers the reference answer."""

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the reference answer and the joined contexts."""
        if not sample.contexts or sample.reference_answer is None:
            return 0.0
        reference_vec = self._embedder.embed_query(sample.reference_answer)
        context_vec = self._embedder.embed_query(" ".join(sample.contexts))
        return _clamp(cosine_similarity(reference_vec, context_vec))


class AnswerCorrectness(_EmbeddingMetric):
    """How close the generated answer is to the reference answer."""

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Cosine similarity between the answer and the reference answer."""
        if sample.reference_answer is None:
            return 0.0
        answer_vec = self._embedder.embed_query(sample.answer)
        reference_vec = self._embedder.embed_query(sample.reference_answer)
        return _clamp(cosine_similarity(answer_vec, reference_vec))


evaluation_registry.register("answer_relevancy", AnswerRelevancy)
evaluation_registry.register("faithfulness", Faithfulness)
evaluation_registry.register("context_precision", ContextPrecision)
evaluation_registry.register("context_recall", ContextRecall)
evaluation_registry.register("answer_correctness", AnswerCorrectness)
