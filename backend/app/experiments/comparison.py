"""Comparação: Combinações of one or more Experimentos measured against a Linha de base.

Items of the Linha de base's Base are paired by question text, on the questions
both answered with a valid score in the main metric; each gets the mean paired
difference with its bootstrap CI (see `app.experiments.stats`).
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session, selectinload

from app.core.db.models import Experiment, ExperimentRun
from app.experiments.orchestrator import ERROR_PREFIX
from app.experiments.stats import paired_diff_ci

DEFAULT_METRIC = "answer_correctness"


class ComparisonError(ValueError):
    """A request that cannot be answered (unknown Experimento, baseline not among items)."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ItemId:
    """Experimento × Combinação: the same Combinação may run in several Experimentos."""

    experiment_id: int
    run_id: int

    @classmethod
    def parse(cls, text: str) -> "ItemId":
        try:
            experiment, run = text.split(":")
            return cls(int(experiment), int(run))
        except ValueError as exc:
            raise ComparisonError(f"item inválido: '{text}' (use experimento:combinação)") from exc

    def __str__(self) -> str:
        return f"{self.experiment_id}:{self.run_id}"


@dataclass
class _Item:
    id: ItemId
    experiment: Experiment
    run: ExperimentRun
    # question -> metric -> mean score over that question's valid answers, in answer order.
    scores: dict[str, dict[str, float]]

    @property
    def base(self) -> str:
        return (self.experiment.config or {}).get("base", "")

    def values(self, metric: str) -> dict[str, float]:
        return {q: s[metric] for q, s in self.scores.items() if metric in s}

    def mean(self, metric: str) -> float | None:
        values = list(self.values(metric).values())
        return sum(values) / len(values) if values else None

    def metrics(self) -> list[str]:
        return list(dict.fromkeys(m for s in self.scores.values() for m in s))


def _question_scores(run: ExperimentRun) -> dict[str, dict[str, float]]:
    """Valid scores per question; answers that failed or were never scored are left out."""
    collected: dict[str, dict[str, list[float]]] = {}
    for result in sorted(run.results, key=lambda r: r.id):
        if result.generated_answer.startswith(ERROR_PREFIX):
            continue
        for metric, value in (result.scores or {}).items():
            if isinstance(value, (int, float)):
                collected.setdefault(result.question, {}).setdefault(metric, []).append(float(value))
    return {
        q: {m: sum(vs) / len(vs) for m, vs in by_metric.items()}
        for q, by_metric in collected.items()
    }


def _load(session: Session, ids: list[ItemId]) -> tuple[list[_Item], list[dict]]:
    experiments = {
        e.id: e
        for e in session.query(Experiment)
        .filter(Experiment.id.in_({i.experiment_id for i in ids}))
        .options(selectinload(Experiment.runs).selectinload(ExperimentRun.results))
    }
    items, excluded = [], []
    for item_id in dict.fromkeys(ids):
        experiment = experiments.get(item_id.experiment_id)
        if experiment is None:
            raise ComparisonError(f"Experimento {item_id.experiment_id} não existe", status=404)
        run = next((r for r in experiment.runs if r.id == item_id.run_id), None)
        if run is None:
            excluded.append({"id": str(item_id), "reason": (
                f"a Combinação {item_id.run_id} não existe no Experimento {experiment.name}"
            )})
            continue
        items.append(_Item(item_id, experiment, run, _question_scores(run)))
    return items, excluded


def _default_metric(baseline: _Item) -> str:
    metrics = baseline.metrics()
    if DEFAULT_METRIC in metrics:
        return DEFAULT_METRIC
    configured = (baseline.experiment.config or {}).get("metrics", [])
    return next((m for m in configured if m in metrics), metrics[0] if metrics else DEFAULT_METRIC)


def _describe(item: _Item, metrics: list[str]) -> dict:
    run = item.run
    return {
        "id": str(item.id),
        "experiment_id": item.experiment.id,
        "experiment_name": item.experiment.name,
        "run_id": run.id,
        "base": item.base,
        "chunking": run.chunking,
        "embedding": run.embedding,
        "rag": run.rag_technique,
        "retriever": run.retriever,
        "llm": run.llm or "gemini",
        "partial": item.experiment.status != "done",
        "means": {m: item.mean(m) for m in metrics},
    }


def compare(
    session: Session, item_ids: list[str], baseline: str | None = None, metric: str | None = None,
) -> dict:
    """The Comparação of these items (`experiment:run`) against the Linha de base."""
    ids = [ItemId.parse(i) for i in item_ids]
    if not ids:
        raise ComparisonError("escolha ao menos uma Combinação")
    baseline_id = ItemId.parse(baseline) if baseline else ids[0]
    if baseline_id not in ids:
        raise ComparisonError(f"a Linha de base {baseline_id} não está entre as Combinações")
    items, excluded = _load(session, ids)
    reference = next((i for i in items if i.id == baseline_id), None)
    if reference is None:
        raise ComparisonError(f"a Linha de base {baseline_id} não existe", status=404)
    metric = metric or _default_metric(reference)
    reference_values = reference.values(metric)

    paired: list[tuple[_Item, int, object]] = []
    for item in items:
        if item is reference:
            paired.append((item, len(reference_values), None))
            continue
        if item.base != reference.base:
            excluded.append({"id": str(item.id), "reason": f"outra Base ({item.base})"})
            continue
        values = item.values(metric)
        common = [q for q in reference_values if q in values]
        if not common:
            excluded.append({"id": str(item.id), "reason": (
                f"nenhuma pergunta em comum com a Linha de base com nota em {metric}"
            )})
            continue
        diff = paired_diff_ci([values[q] - reference_values[q] for q in common])
        paired.append((item, len(common), diff))

    metrics = list(dict.fromkeys(m for item, _, _ in paired for m in item.metrics()))
    rows = []
    for item, n, diff in paired:
        row = _describe(item, metrics)
        row["n"] = n
        row["diff"] = None if diff is None else {
            "mean": diff.mean, "low": diff.low, "high": diff.high, "significant": diff.significant,
        }
        rows.append(row)
    return {
        "baseline": str(baseline_id),
        "metric": metric,
        "metrics": metrics,
        "base": reference.base,
        "items": rows,
        "excluded": excluded,
    }
