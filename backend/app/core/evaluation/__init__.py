"""Evaluation package. Importing it registers the built-in metrics."""
from app.core.evaluation.base import (
    EvalSample,
    Evaluator,
    build_evaluator,
    evaluation_registry,
)
from app.core.evaluation.embedding_metrics import (
    AnswerRelevancy,
    ContextPrecision,
    Faithfulness,
)

__all__ = [
    "EvalSample",
    "Evaluator",
    "build_evaluator",
    "evaluation_registry",
    "AnswerRelevancy",
    "ContextPrecision",
    "Faithfulness",
]
