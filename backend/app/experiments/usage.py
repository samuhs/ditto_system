"""Which Bases are in use now, so they are not deleted from under a run."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.models import Experiment
from app.experiments.orchestrator import graph_build_progress

# Statuses of an experiment that will still read its Base: running or queued.
_ACTIVE = ("running", "pending")

_WAIT = " Aguarde terminar ou pause o experimento."


def _reason(experiment: Experiment, base: str, building: bool) -> str:
    if building:
        doing = (
            f'Um Grafo de conhecimento da base "{base}" está sendo construído pelo '
            f'experimento "{experiment.name}".'
        )
    elif experiment.status == "running":
        doing = f'O experimento "{experiment.name}" está rodando sobre a base "{base}".'
    else:
        doing = f'O experimento "{experiment.name}" está na fila para usar a base "{base}".'
    return doing + _WAIT


def bases_in_use(session: Session) -> dict[str, str]:
    """Base -> why it is in use (PT-BR, shown to the user), for every Base in use now.

    A Base is in use while an experiment on it runs or waits in the queue; a
    Grafo de conhecimento being built for it is named first. Every build runs
    inside an experiment today: a build started elsewhere must be added here.
    """
    experiments = session.scalars(
        select(Experiment).where(Experiment.status.in_(_ACTIVE)).order_by(Experiment.id)
    )
    reasons: dict[str, str] = {}
    building_bases: set[str] = set()
    for experiment in experiments:
        base = (experiment.config or {}).get("base")
        if not base or base in building_bases:
            continue
        building = graph_build_progress(experiment.id) is not None
        if building:
            building_bases.add(base)
        elif base in reasons:
            continue
        reasons[base] = _reason(experiment, base, building)
    return reasons
