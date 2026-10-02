"""Evaluation package. Importing it registers the built-in metrics."""
from app.core.evaluation import (  # noqa: F401  registers the built-ins
    embedding_metrics,
    gold_metrics,
    overlap_metrics,
)
