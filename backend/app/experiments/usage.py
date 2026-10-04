"""Which Bases are in use now, so they are not deleted from under a run."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.models import Experiment
from app.experiments.orchestrator import graph_build_progress

# Statuses of an experiment that will still read its Base: running or queued.
_ACTIVE = ("running", "pending")


def bases_in_use(session: Session) -> dict[str, str]:
    """Base -> why it is in use (PT-BR, shown to the user), for every Base in use now.

    A Base is in use while an experiment on it runs or waits in the queue; a
    Grafo de conhecimento being built for one is named as such.
    """
    experiments = session.scalars(
        select(Experiment).where(Experiment.status.in_(_ACTIVE)).order_by(Experiment.id)
    )
    reasons: dict[str, str] = {}
    for experiment in experiments:
        base = (experiment.config or {}).get("base")
        if not base or base in reasons:
            continue
        if graph_build_progress(experiment.id) is not None:
            reasons[base] = (
                f'Um Grafo de conhecimento da base "{base}" está sendo construído pelo '
                f'experimento "{experiment.name}". Aguarde terminar ou pause o experimento.'
            )
        elif experiment.status == "running":
            reasons[base] = (
                f'O experimento "{experiment.name}" está rodando sobre a base "{base}". '
                "Aguarde terminar ou pause o experimento."
            )
        else:
            reasons[base] = (
                f'O experimento "{experiment.name}" está na fila para usar a base "{base}". '
                "Aguarde terminar ou pause o experimento."
            )
    return reasons
