"""Question-difficulty signals: interfaces, registries and profile builders.

Signals are recorded raw and never fused into one difficulty score: which of
them predict a bad answer (for small models, in PT-BR) is what a large
experiment has to show first. Two kinds exist:

- QuestionSignal: known before retrieval, from the question text and the
  base's corpus statistics (query performance prediction, pre-retrieval).
- EvidenceSignal: from the question and its annotated reference evidence
  (how many passages it needs, how far the question is from them). Absent
  when the question has no evidence.
- RetrievalSignal: known after retrieval, from the retrieved chunks' scores
  (post-retrieval QPP). Scores are raw; their scale depends on the embedder.
"""
from abc import ABC, abstractmethod

from app.core.difficulty.corpus import CorpusStats
from app.core.registry import Registry
from app.core.vector_math import cosine_similarity


class QuestionSignal(ABC):
    """A difficulty signal computed from the question alone (plus corpus stats)."""

    requires_corpus: bool = False

    @abstractmethod
    def compute(self, question: str, corpus: CorpusStats | None) -> float:
        """Return the signal's value for the question."""


class EvidenceSignal(ABC):
    """A difficulty signal computed from the question and its reference evidence."""

    @abstractmethod
    def compute(self, question: str, evidence: list[str]) -> float:
        """Return the signal's value for a question with non-empty evidence."""


class RetrievalSignal(ABC):
    """A difficulty signal computed from the retrieved chunks' scores, best first."""

    @abstractmethod
    def compute(self, scores: list[float]) -> float:
        """Return the signal's value for a non-empty score list."""


question_signal_registry: Registry[type[QuestionSignal]] = Registry("question_signal")
evidence_signal_registry: Registry[type[EvidenceSignal]] = Registry("evidence_signal")
retrieval_signal_registry: Registry[type[RetrievalSignal]] = Registry("retrieval_signal")


def question_profile(
    question: str, corpus: CorpusStats | None = None, evidence: list[str] | None = None
) -> dict[str, float]:
    """Every registered question signal; corpus- and evidence-based ones only when given."""
    profile = {}
    for name in question_signal_registry.names():
        signal = question_signal_registry.get(name)()
        if signal.requires_corpus and corpus is None:
            continue
        profile[name] = signal.compute(question, corpus)
    if evidence:
        for name in evidence_signal_registry.names():
            profile[name] = evidence_signal_registry.get(name)().compute(question, evidence)
    return profile


def evidence_distance(embedder, question: str, evidence: list[str]) -> float:
    """GRADE's retrieval-side difficulty: 1 - the lowest question-evidence cosine.

    The passage least similar to the question is the one retrieval is most
    likely to miss (Lee, Kwon & Jin, Findings EMNLP 2025, arXiv 2508.16994).
    """
    question_vec = embedder.embed_query(question)
    similarities = [cosine_similarity(question_vec, embedder.embed_query(p)) for p in evidence]
    return 1.0 - min(similarities)


def retrieval_profile(contexts: list[dict]) -> dict[str, float]:
    """Every registered retrieval signal over the contexts' 'score' values.

    Empty when nothing carries a score (no retrieval, or a technique such as
    compression that replaces the chunks with generated text).
    """
    scores = sorted(
        (float(c["score"]) for c in contexts if isinstance(c.get("score"), (int, float))),
        reverse=True,
    )
    if not scores or all(c.get("source") == "compression" for c in contexts):
        return {}
    return {
        name: retrieval_signal_registry.get(name)().compute(scores)
        for name in retrieval_signal_registry.names()
    }
