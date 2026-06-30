"""Run a selected set of evaluation metrics over one sample."""
import inspect

from app.core.embedding.base import Embedder
from app.core.evaluation.base import EvalSample, evaluation_registry


def evaluate_sample(
    sample: EvalSample,
    metric_names: list[str],
    embedder: Embedder | None = None,
) -> dict[str, float]:
    """Score a sample with the named metrics, skipping reference-only ones if absent."""
    scores: dict[str, float] = {}
    for name in metric_names:
        metric_class = evaluation_registry.get(name)
        if metric_class.requires_reference and sample.reference_answer is None:
            continue
        if "embedder" in inspect.signature(metric_class.__init__).parameters:
            metric = metric_class(embedder=embedder)
        else:
            metric = metric_class()
        scores[name] = metric.score(sample)
    return scores
