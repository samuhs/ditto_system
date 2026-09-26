"""Retrieval metrics against annotated reference evidence (no LLM, no embedder).

Each question may carry evidence passages copied from the source document. A
retrieved chunk counts as relevant when it holds one of them, found by fuzzy
text alignment rather than by chunk id, so the same annotation works for every
chunker (the mechanism of RAGAS' non-LLM context recall).
"""
import re

from rapidfuzz import fuzz

from app.core.evaluation.base import EvalSample, Evaluator, evaluation_registry

# partial_ratio (0-100) at or above which a chunk is taken to hold the evidence.
MATCH_THRESHOLD = 80
# A chunk shorter than this share of the evidence holds too little of it to count.
MIN_LENGTH_SHARE = 0.5

_NON_WORD = re.compile(r"[\W_]+")


def _normalize(text: str) -> str:
    """Lowercase and reduce markdown, punctuation and whitespace to single spaces."""
    return _NON_WORD.sub(" ", text.lower()).strip()


def evidence_found_in(evidence: str, chunk: str) -> bool:
    """Whether the chunk holds the evidence passage (or most of it, if it was split)."""
    target, candidate = _normalize(evidence), _normalize(chunk)
    if not target or len(candidate) < MIN_LENGTH_SHARE * len(target):
        return False
    return fuzz.partial_ratio(target, candidate) >= MATCH_THRESHOLD


def _relevant_ranks(sample: EvalSample) -> list[int]:
    """1-based ranks of the retrieved chunks that hold any evidence passage."""
    evidence = sample.reference_contexts or []
    return [
        rank
        for rank, chunk in enumerate(sample.contexts, start=1)
        if any(evidence_found_in(passage, chunk) for passage in evidence)
    ]


class ContextHit(Evaluator):
    """1 if any retrieved chunk holds reference evidence, else 0 (hit rate at k)."""

    requires_reference_contexts = True
    requires_contexts = True

    def score(self, sample: EvalSample) -> float:
        """Return 1.0 on a hit among the retrieved chunks."""
        return 1.0 if _relevant_ranks(sample) else 0.0


class ContextMRR(Evaluator):
    """Reciprocal rank of the first retrieved chunk that holds reference evidence."""

    requires_reference_contexts = True
    requires_contexts = True

    def score(self, sample: EvalSample) -> float:
        """Return 1/rank of the first relevant chunk, 0 when none is retrieved."""
        ranks = _relevant_ranks(sample)
        return 1 / ranks[0] if ranks else 0.0


class ContextRecallGold(Evaluator):
    """Share of the reference evidence passages found in some retrieved chunk."""

    requires_reference_contexts = True
    requires_contexts = True

    def score(self, sample: EvalSample) -> float:
        """Return found passages / annotated passages."""
        evidence = sample.reference_contexts or []
        if not evidence:
            return 0.0
        found = sum(
            any(evidence_found_in(passage, chunk) for chunk in sample.contexts)
            for passage in evidence
        )
        return found / len(evidence)


evaluation_registry.register("context_hit", ContextHit)
evaluation_registry.register("context_mrr", ContextMRR)
evaluation_registry.register("context_recall_gold", ContextRecallGold)
