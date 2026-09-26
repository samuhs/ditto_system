"""Observed difficulty of each question across an experiment's configurations.

Read-time aggregation over stored results (nothing new is persisted): for each
question and LLM, the mean and spread of every metric over the retrieval
configurations, the closed-book baseline, and, when reference evidence was
annotated, the metrics split by whether retrieval brought the evidence back
(context_hit). That split separates "retrieval missed it" from "the evidence
was in the context and this LLM still answered badly".
"""
import statistics

from app.core.db.models import Experiment
from app.core.rag.base import rag_registry

HIT_METRIC = "context_hit"
_ERROR_PREFIX = "[ERRO: "


def _uses_retrieval(rag: str) -> bool:
    return rag not in rag_registry.names() or rag_registry.get(rag).uses_retrieval


def _summary(values: list[float]) -> dict:
    return {
        "mean": statistics.fmean(values),
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "n": len(values),
    }


def _metric_summaries(score_dicts: list[dict]) -> dict[str, dict]:
    by_metric: dict[str, list[float]] = {}
    for scores in score_dicts:
        for metric, value in scores.items():
            by_metric.setdefault(metric, []).append(value)
    return {metric: _summary(values) for metric, values in sorted(by_metric.items())}


def _means(score_dicts: list[dict]) -> dict[str, float]:
    return {m: s["mean"] for m, s in _metric_summaries(score_dicts).items()}


def question_difficulty(experiment: Experiment) -> dict:
    """Per-question signals and observed difficulty, per LLM."""
    profiles = {p.question: p.signals for p in experiment.question_profiles}
    llms: list[str] = []
    metrics: set[str] = set()
    grouped: dict[str, dict[str, dict[str, list]]] = {}
    signals: dict[str, list[dict]] = {}
    for run in experiment.runs:
        llm = run.llm or "gemini"
        kind = "retrieval" if _uses_retrieval(run.rag_technique) else "closed_book"
        for result in run.results:
            if not result.scores or result.generated_answer.startswith(_ERROR_PREFIX):
                continue
            if llm not in llms:
                llms.append(llm)
            metrics.update(result.scores)
            slot = grouped.setdefault(result.question, {}).setdefault(
                llm, {"retrieval": [], "closed_book": []}
            )
            slot[kind].append(result.scores)
            if result.retrieval_signals:
                signals.setdefault(result.question, []).append(result.retrieval_signals)

    questions = []
    for question in dict.fromkeys([*profiles, *grouped]):
        by_llm = {}
        for llm, slot in grouped.get(question, {}).items():
            retrieval = slot["retrieval"]
            hits = [s for s in retrieval if s.get(HIT_METRIC) == 1.0]
            misses = [s for s in retrieval if s.get(HIT_METRIC) == 0.0]
            by_llm[llm] = {
                "retrieval": _metric_summaries(retrieval),
                "closed_book": _means(slot["closed_book"]),
                "hit_rate": len(hits) / (len(hits) + len(misses)) if hits or misses else None,
                "with_evidence": _means(hits),
                "without_evidence": _means(misses),
            }
        questions.append({
            "question": question,
            "signals": profiles.get(question, {}),
            "retrieval_signals": _means(signals.get(question, [])),
            "by_llm": by_llm,
        })
    return {"llms": llms, "metrics": sorted(metrics), "questions": questions}
