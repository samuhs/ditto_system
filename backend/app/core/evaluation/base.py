"""Evaluation metric interface, sample model, registry, and factory."""
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.registry import Registry


class EvalSample(BaseModel):
    """One evaluation unit: a question, an answer, its contexts, and optional references.

    reference_contexts holds annotated evidence passages (literal text from the
    source document) that a good retrieval should bring back.
    """

    question: str
    answer: str
    contexts: list[str]
    reference_answer: str | None = None
    reference_contexts: list[str] | None = None


class Evaluator(ABC):
    """Minimal interface every evaluation metric implements."""

    requires_reference: bool = False
    requires_reference_contexts: bool = False
    # Scores the retrieved contexts: skipped when nothing was retrieved (closed book).
    requires_contexts: bool = False

    @abstractmethod
    def score(self, sample: EvalSample) -> float:
        """Return a metric score for the sample."""


evaluation_registry: Registry[type[Evaluator]] = Registry("evaluation")


def build_evaluator(name: str, **kwargs) -> Evaluator:
    """Instantiate a registered evaluation metric by name."""
    return evaluation_registry.get(name)(**kwargs)
