"""Observed difficulty of each question across an experiment's configurations.

Read-time aggregation over stored results (nothing new is persisted): for each
question and LLM, the mean and spread of every metric over the retrieval
configurations, the closed-book baseline, the oracle (evidence as context)
and, when reference evidence was annotated, the metrics split by whether
retrieval brought the evidence back (context_hit). That split separates
"retrieval missed it" from "the evidence was in the context and this LLM still
answered badly". An IRT fit on one metric gives each question a difficulty,
overall and per LLM, and the signals known before any answer (question text,
corpus, evidence, retrieval scores, perplexity) are correlated with it: which
of them predict difficulty, for which model.
"""
import statistics

import numpy as np

from app.core.db.models import Experiment
from app.core.rag.base import rag_registry
from app.experiments.irt import MIN_RELIABLE_QUESTIONS, fit_rasch

HIT_METRIC = "context_hit"
# Answer-quality metrics tried, in order, when no metric is asked for.
PREFERRED_METRICS = ["chrf", "token_f1", "answer_correctness", "rouge_l"]
_ERROR_PREFIX = "[ERRO: "


def _kind(rag: str) -> str:
    """'retrieval', or the baseline a non-retrieving technique stands for."""
    if rag not in rag_registry.names():
        return "retrieval"
    technique = rag_registry.get(rag)
    if technique.uses_evidence:
        return "oracle"
    return "retrieval" if technique.uses_retrieval else "closed_book"


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


def _irt(responses: dict[tuple[str, str, str], float], llms: list[str], metric: str) -> dict:
    """Rasch fit over every retrieval configuration, and one per LLM."""
    overall, ability = fit_rasch({(c, q): s for (c, _, q), s in responses.items()})
    by_llm = {
        llm: fit_rasch({(c, q): s for (c, l, q), s in responses.items() if l == llm})[0]
        for llm in llms
    }
    return {
        "metric": metric,
        "n_questions": len(overall),
        "n_configurations": len(ability),
        "reliable": len(overall) >= MIN_RELIABLE_QUESTIONS,
        "min_questions": MIN_RELIABLE_QUESTIONS,
        "difficulty": overall,
        "difficulty_by_llm": by_llm,
        "ability": ability,
    }


def _ranks(values: list[float]) -> np.ndarray:
    """Ranks with ties averaged (as Spearman's rho needs)."""
    array = np.asarray(values, dtype=float)
    order = array.argsort(kind="stable")
    ranks = np.empty(len(array))
    ranks[order] = np.arange(len(array), dtype=float)
    for value in np.unique(array):
        tied = array == value
        ranks[tied] = ranks[tied].mean()
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman's rank correlation; None under 3 pairs or when either side is constant."""
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _correlate(signal: dict[str, float], difficulty: dict[str, float]) -> float | None:
    common = [q for q in signal if q in difficulty]
    return spearman([signal[q] for q in common], [difficulty[q] for q in common])


def _signal_correlations(questions: list[dict], irt: dict) -> dict:
    """Spearman's rho of each answer-free signal with the IRT difficulty (positive = harder)."""
    by_signal: dict[tuple[str, str], dict[str, float]] = {}
    for q in questions:
        for name, value in q["signals"].items():
            by_signal.setdefault(("question", name), {})[q["question"]] = value
        for name, value in q["retrieval_signals"].items():
            by_signal.setdefault(("retrieval", name), {})[q["question"]] = value
    rows = [
        {
            "signal": name,
            "kind": kind,
            "overall": _correlate(values, irt["difficulty"]),
            "by_llm": {
                llm: _correlate(values, per_llm) for llm, per_llm in irt["difficulty_by_llm"].items()
            },
        }
        for (kind, name), values in sorted(by_signal.items())
    ]
    # Model signals exist per LLM, so each is compared with that LLM's difficulty only.
    model_names = sorted({n for q in questions for s in q["model_signals"].values() for n in s})
    for name in model_names:
        by_llm = {}
        for llm, per_llm in irt["difficulty_by_llm"].items():
            values = {
                q["question"]: q["model_signals"][llm][name]
                for q in questions
                if name in q["model_signals"].get(llm, {})
            }
            by_llm[llm] = _correlate(values, per_llm) if values else None
        rows.append({"signal": name, "kind": "model", "overall": None, "by_llm": by_llm})
    return {"n_questions": irt["n_questions"], "reliable": irt["reliable"], "rows": rows}


def question_difficulty(experiment: Experiment, metric: str | None = None) -> dict:
    """Per-question signals and observed difficulty, per LLM, plus an IRT fit on one metric."""
    profiles = {p.question: p.signals for p in experiment.question_profiles}
    model_signals = {p.question: p.model_signals or {} for p in experiment.question_profiles}
    llms: list[str] = []
    metrics: set[str] = set()
    grouped: dict[str, dict[str, dict[str, list]]] = {}
    signals: dict[str, list[dict]] = {}
    rows: list[tuple[str, str, str, dict]] = []  # (configuration, llm, question, scores)
    for run in experiment.runs:
        llm = run.llm or "gemini"
        kind = _kind(run.rag_technique)
        config_key = "|".join(
            [run.chunking, run.embedding, run.rag_technique, run.retriever, llm]
        )
        for result in run.results:
            if not result.scores or result.generated_answer.startswith(_ERROR_PREFIX):
                continue
            if llm not in llms:
                llms.append(llm)
            metrics.update(result.scores)
            slot = grouped.setdefault(result.question, {}).setdefault(
                llm, {"retrieval": [], "closed_book": [], "oracle": []}
            )
            slot[kind].append(result.scores)
            if kind == "retrieval":
                rows.append((config_key, llm, result.question, result.scores))
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
                "oracle": _means(slot["oracle"]),
                "hit_rate": len(hits) / (len(hits) + len(misses)) if hits or misses else None,
                "with_evidence": _means(hits),
                "without_evidence": _means(misses),
            }
        questions.append({
            "question": question,
            "signals": profiles.get(question, {}),
            "model_signals": model_signals.get(question, {}),
            "retrieval_signals": _means(signals.get(question, [])),
            "by_llm": by_llm,
        })
    if metric not in metrics:
        metric = next((m for m in PREFERRED_METRICS if m in metrics), min(metrics, default=None))
    responses = {
        (config, llm, question): scores[metric]
        for config, llm, question, scores in rows
        if metric in scores
    }
    irt = _irt(responses, llms, metric) if metric else None
    return {
        "llms": llms,
        "metrics": sorted(metrics),
        "metric": metric,
        "questions": questions,
        "irt": irt,
        "correlations": _signal_correlations(questions, irt) if irt else None,
        "perplexity_skipped": (experiment.config or {}).get("perplexity_skipped", {}),
    }
