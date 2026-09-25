"""Overlap-based evaluation metrics against the reference answer.

ROUGE-L (longest common subsequence), SQuAD-style token F1 and chrF.
"""
import unicodedata
from collections import Counter

import sacrebleu

from app.core.evaluation.base import EvalSample, Evaluator, evaluation_registry

# Portuguese counterpart of the English articles the SQuAD script drops.
_PT_ARTICLES = frozenset({"o", "a", "os", "as", "um", "uma", "uns", "umas"})


def normalize_pt_tokens(text: str) -> list[str]:
    """Lowercase, drop punctuation/symbols and Portuguese articles, split on whitespace."""
    cleaned = "".join(
        " " if unicodedata.category(ch)[0] in "PS" else ch for ch in text.lower()
    )
    return [token for token in cleaned.split() if token not in _PT_ARTICLES]


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Return the length of the longest common subsequence of two token lists."""
    rows = len(a) + 1
    cols = len(b) + 1
    table = [[0] * cols for _ in range(rows)]
    for i in range(1, rows):
        for j in range(1, cols):
            if a[i - 1] == b[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
            else:
                table[i][j] = max(table[i - 1][j], table[i][j - 1])
    return table[-1][-1]


class RougeL(Evaluator):
    """ROUGE-L F-measure between the answer and the reference answer."""

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Return the LCS-based F1 between answer and reference tokens."""
        if sample.reference_answer is None:
            return 0.0
        answer_tokens = sample.answer.lower().split()
        reference_tokens = sample.reference_answer.lower().split()
        if not answer_tokens or not reference_tokens:
            return 0.0
        lcs = _lcs_length(answer_tokens, reference_tokens)
        if lcs == 0:
            return 0.0
        precision = lcs / len(answer_tokens)
        recall = lcs / len(reference_tokens)
        return 2 * precision * recall / (precision + recall)


class TokenF1(Evaluator):
    """SQuAD-style token F1 between answer and reference, normalised for Portuguese.

    Shared tokens are counted as a multiset. Long answers lose precision, so a
    verbose but correct answer scores below 1.
    """

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Return the harmonic mean of token precision and recall."""
        if sample.reference_answer is None:
            return 0.0
        answer_tokens = normalize_pt_tokens(sample.answer)
        reference_tokens = normalize_pt_tokens(sample.reference_answer)
        shared = sum((Counter(answer_tokens) & Counter(reference_tokens)).values())
        if shared == 0:
            return 0.0
        precision = shared / len(answer_tokens)
        recall = shared / len(reference_tokens)
        return 2 * precision * recall / (precision + recall)


class ChrF(Evaluator):
    """chrF (character 6-grams, beta=2) from sacrebleu, scaled to 0..1.

    Character n-grams give partial credit to inflected forms
    ("restaurante"/"restaurantes"), which token overlap misses.
    """

    requires_reference = True

    def score(self, sample: EvalSample) -> float:
        """Return sacrebleu's sentence-level chrF divided by 100."""
        if sample.reference_answer is None:
            return 0.0
        return sacrebleu.sentence_chrf(sample.answer, [sample.reference_answer]).score / 100


evaluation_registry.register("rouge_l", RougeL)
evaluation_registry.register("token_f1", TokenF1)
evaluation_registry.register("chrf", ChrF)
