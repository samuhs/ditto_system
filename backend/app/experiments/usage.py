"""Which Bases are in use now, so they are not deleted from under a run or a build."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.models import Experiment
from app.core.graph.jobs import GraphBuildJob, GraphBuilds, graph_builds

# Statuses of an experiment that will still read its Base: running or queued.
_ACTIVE = ("running", "pending")


def _experiment_reason(experiment: Experiment, base: str) -> str:
    if experiment.status == "running":
        doing = f'O experimento "{experiment.name}" está rodando sobre a base "{base}".'
    else:
        doing = f'O experimento "{experiment.name}" está na fila para usar a base "{base}".'
    return doing + " Aguarde terminar ou pause o experimento."


def _build_reason(job: GraphBuildJob) -> str:
    if job.status == "running":
        doing = (
            f'Um Grafo de conhecimento da base "{job.base}" está sendo construído '
            f"(LLM extrator {job.extractor})."
        )
    else:
        doing = (
            f'Um Grafo de conhecimento da base "{job.base}" está na fila para ser construído '
            f"(LLM extrator {job.extractor})."
        )
    return doing + " Aguarde terminar ou pause a construção."


def bases_in_use(session: Session, builds: GraphBuilds = graph_builds) -> dict[str, str]:
    """Base -> why it is in use (PT-BR, shown to the user), for every Base in use now.

    A Base is in use while a Grafo de conhecimento build or an experiment on it
    runs or waits in the queue; a build is named first.
    """
    reasons: dict[str, str] = {}
    for job in builds.active():
        reasons.setdefault(job.base, _build_reason(job))
    experiments = session.scalars(
        select(Experiment).where(Experiment.status.in_(_ACTIVE)).order_by(Experiment.id)
    )
    for experiment in experiments:
        base = (experiment.config or {}).get("base")
        if base and base not in reasons:
            reasons[base] = _experiment_reason(experiment, base)
    return reasons
