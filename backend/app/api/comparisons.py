"""Endpoint of the Comparação: Combinações of one or more Experimentos side by side."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.experiments import get_experiment_deps
from app.experiments.comparison import ComparisonError, compare
from app.experiments.orchestrator import ExperimentDeps

router = APIRouter()


@router.get("/comparisons")
def get_comparison(
    items: str = Query(..., description="experiment:run pairs, comma separated"),
    baseline: str | None = Query(None, description="the Linha de base; the first item by default"),
    metric: str | None = Query(None, description="main metric; answer_correctness by default"),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Each item against the Linha de base, paired by question, with a 95% bootstrap CI."""
    session = deps.session_factory()
    try:
        return compare(session, [i for i in items.split(",") if i], baseline, metric)
    except ComparisonError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    finally:
        session.close()
