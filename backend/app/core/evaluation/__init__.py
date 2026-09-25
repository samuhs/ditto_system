"""Evaluation package. Importing it registers the built-in metrics."""
from app.core.evaluation.base import (
    EvalSample,
    Evaluator,
    build_evaluator,
    evaluation_registry,
)
from app.core.evaluation.embedding_metrics import (
    AnswerCorrectness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)
from app.core.evaluation.gold_metrics import ContextHit, ContextMRR, ContextRecallGold
from app.core.evaluation.overlap_metrics import ChrF, RougeL, TokenF1
from app.core.evaluation.runner import evaluate_sample

__all__ = [
    "EvalSample",
    "Evaluator",
    "build_evaluator",
    "evaluation_registry",
    "AnswerRelevancy",
    "ContextPrecision",
    "Faithfulness",
    "ContextRecall",
    "AnswerCorrectness",
    "RougeL",
    "TokenF1",
    "ChrF",
    "ContextHit",
    "ContextMRR",
    "ContextRecallGold",
    "evaluate_sample",
]
