"""Overlap-based evaluation metrics (ROUGE-L via longest common subsequence)."""
from app.core.evaluation.base import EvalSample, Evaluator, evaluation_registry


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


evaluation_registry.register("rouge_l", RougeL)
