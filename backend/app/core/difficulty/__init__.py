"""Question-difficulty signals. Importing it registers the built-in signals."""
from app.core.difficulty import signals  # noqa: F401  registers the built-ins
from app.core.difficulty.base import (
    QuestionSignal,
    RetrievalSignal,
    question_profile,
    question_signal_registry,
    retrieval_profile,
    retrieval_signal_registry,
)
from app.core.difficulty.corpus import CorpusStats, corpus_stats_for_base

__all__ = [
    "QuestionSignal",
    "RetrievalSignal",
    "question_profile",
    "question_signal_registry",
    "retrieval_profile",
    "retrieval_signal_registry",
    "CorpusStats",
    "corpus_stats_for_base",
]
