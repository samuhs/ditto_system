"""Run a selected set of evaluation metrics over one sample."""
import inspect

from app.core.embedding.base import Embedder
from app.core.evaluation.base import EvalSample, evaluation_registry


class _MemoEmbedder:
    """Embeds each distinct text once; the metrics of one sample share the vectors.

    The answer alone appears in three metrics and the question in two, so this
    roughly halves the embedding calls without changing any score.
    """

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._vectors: dict[str, list[float]] = {}

    def embed_query(self, text: str) -> list[float]:
        if text not in self._vectors:
            self._vectors[text] = self._embedder.embed_query(text)
        return self._vectors[text]


def _needs_embedder(metric_class) -> bool:
    return "embedder" in inspect.signature(metric_class.__init__).parameters


def metrics_need_embedder(metric_names: list[str]) -> bool:
    """Whether any of the metrics compares embeddings (so an eval embedder must load)."""
    return any(_needs_embedder(evaluation_registry.get(name)) for name in metric_names)


def evaluate_sample(
    sample: EvalSample,
    metric_names: list[str],
    embedder: Embedder | None = None,
) -> dict[str, float]:
    """Score a sample with the named metrics, skipping those whose references are absent."""
    memo = _MemoEmbedder(embedder) if embedder is not None else None
    scores: dict[str, float] = {}
    for name in metric_names:
        metric_class = evaluation_registry.get(name)
        if metric_class.requires_reference and sample.reference_answer is None:
            continue
        if metric_class.requires_reference_contexts and not sample.reference_contexts:
            continue
        if metric_class.requires_contexts and not sample.contexts:
            continue
        if _needs_embedder(metric_class):
            if memo is None:
                raise ValueError(f"metric '{name}' requires an embedder")
            metric = metric_class(embedder=memo)
        else:
            metric = metric_class()
        scores[name] = metric.score(sample)
    return scores
