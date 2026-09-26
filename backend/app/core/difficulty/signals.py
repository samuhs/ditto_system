"""Built-in difficulty signals (Portuguese question patterns, IDF, score shape)."""
import re
import statistics

from app.core.difficulty.base import (
    QuestionSignal,
    RetrievalSignal,
    question_signal_registry,
    retrieval_signal_registry,
)
from app.core.difficulty.corpus import CorpusStats
from app.core.evaluation.overlap_metrics import normalize_pt_tokens


class _PatternSignal(QuestionSignal):
    """1.0 when the lowercased question matches the pattern, else 0.0."""

    pattern: re.Pattern

    def compute(self, question: str, corpus: CorpusStats | None) -> float:
        return 1.0 if self.pattern.search(question.lower()) else 0.0


class QuestionLength(QuestionSignal):
    """Number of normalised tokens in the question."""

    def compute(self, question: str, corpus: CorpusStats | None) -> float:
        return float(len(normalize_pt_tokens(question)))


class SubQuestions(QuestionSignal):
    """Number of question marks, at least 1 (several questions in one)."""

    def compute(self, question: str, corpus: CorpusStats | None) -> float:
        return float(max(1, question.count("?")))


class Temporal(_PatternSignal):
    """Asks about time: schedules, dates, opening hours."""

    pattern = re.compile(
        r"\b(quando|hor[aá]rios?|que horas|datas?|[eé]poca|abre|fecha|funcionamento)\b"
    )


class Numeric(_PatternSignal):
    """Asks for a quantity, price or distance."""

    pattern = re.compile(
        r"\b(quant[oa]s?|pre[cç]os?|custa|custo|valor|dist[aâ]ncia|km|quil[oô]metros?)\b"
    )


class Negation(_PatternSignal):
    """Contains a negation, which small models often read past."""

    pattern = re.compile(r"\b(n[aã]o|nunca|nenhum|nenhuma|sem)\b")


class Aggregation(_PatternSignal):
    """Asks for a list or several items, which may span several passages."""

    pattern = re.compile(r"\b(quais|principais|liste|todos|todas|op[cç][oõ]es)\b")


class YesNo(_PatternSignal):
    """Opens with a verb, as a yes/no question does ("Tem...", "Dá para...")."""

    pattern = re.compile(r"^\W*(tem|h[aá]|[eé]|d[aá]|pode|posso|existe|vale)\b")


class _CorpusSignal(QuestionSignal):
    requires_corpus = True


class MeanIdf(_CorpusSignal):
    """Mean IDF of the question's tokens (pre-retrieval specificity)."""

    def compute(self, question: str, corpus: CorpusStats | None) -> float:
        tokens = normalize_pt_tokens(question)
        return sum(corpus.idf(t) for t in tokens) / len(tokens) if tokens else 0.0


class MaxIdf(_CorpusSignal):
    """Highest IDF among the question's tokens (its rarest term)."""

    def compute(self, question: str, corpus: CorpusStats | None) -> float:
        return max((corpus.idf(t) for t in normalize_pt_tokens(question)), default=0.0)


class OutOfCorpus(_CorpusSignal):
    """Share of the question's tokens that never occur in the corpus."""

    def compute(self, question: str, corpus: CorpusStats | None) -> float:
        tokens = normalize_pt_tokens(question)
        if not tokens:
            return 0.0
        return sum(t not in corpus.doc_freq for t in tokens) / len(tokens)


class TopScore(RetrievalSignal):
    """Similarity score of the best retrieved chunk."""

    def compute(self, scores: list[float]) -> float:
        return scores[0]


class ScoreGap(RetrievalSignal):
    """Best minus second-best score: a clear winner suggests an easy retrieval."""

    def compute(self, scores: list[float]) -> float:
        return scores[0] - scores[1] if len(scores) > 1 else 0.0


class ScoreSpread(RetrievalSignal):
    """Standard deviation of the scores (the idea behind NQC)."""

    def compute(self, scores: list[float]) -> float:
        return statistics.pstdev(scores)


question_signal_registry.register("question_length", QuestionLength)
question_signal_registry.register("sub_questions", SubQuestions)
question_signal_registry.register("temporal", Temporal)
question_signal_registry.register("numeric", Numeric)
question_signal_registry.register("negation", Negation)
question_signal_registry.register("aggregation", Aggregation)
question_signal_registry.register("yes_no", YesNo)
question_signal_registry.register("mean_idf", MeanIdf)
question_signal_registry.register("max_idf", MaxIdf)
question_signal_registry.register("out_of_corpus", OutOfCorpus)
retrieval_signal_registry.register("top_score", TopScore)
retrieval_signal_registry.register("score_gap", ScoreGap)
retrieval_signal_registry.register("score_spread", ScoreSpread)
