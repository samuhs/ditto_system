"""Endpoints of the Comparação: Combinações of one or more Experimentos side by side."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.experiments import get_experiment_deps
from app.experiments.comparison import ComparisonError, compare
from app.experiments.comparison_export import to_csv, to_latex
from app.experiments.orchestrator import ExperimentDeps

router = APIRouter()

_ITEMS = Query(..., description="experiment:run pairs, comma separated")
_BASELINE = Query(None, description="the Linha de base; the first item by default")
_METRIC = Query(None, description="main metric; answer_correctness by default")


def _comparison(deps: ExperimentDeps, items: str, baseline: str | None, metric: str | None) -> dict:
    session = deps.session_factory()
    try:
        return compare(session, [i for i in items.split(",") if i], baseline, metric)
    except ComparisonError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    finally:
        session.close()


@router.get("/comparisons")
def get_comparison(
    items: str = _ITEMS,
    baseline: str | None = _BASELINE,
    metric: str | None = _METRIC,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Each item against the Linha de base, paired by question, with a 95% bootstrap CI."""
    return _comparison(deps, items, baseline, metric)


def _download(content: str, media_type: str, filename: str) -> Response:
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/comparisons/export.csv")
def export_comparison_csv(
    items: str = _ITEMS,
    baseline: str | None = _BASELINE,
    metric: str | None = _METRIC,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> Response:
    """The Comparação as CSV: one row per item, the page's columns."""
    # The BOM makes spreadsheet apps read it as UTF-8 (same as the Experimento export).
    content = "\ufeff" + to_csv(_comparison(deps, items, baseline, metric))
    return _download(content, "text/csv; charset=utf-8", "comparacao.csv")


@router.get("/comparisons/export.tex")
def export_comparison_latex(
    items: str = _ITEMS,
    baseline: str | None = _BASELINE,
    metric: str | None = _METRIC,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> Response:
    """The Comparação as LaTeX booktabs tables, in the campaign paper's format."""
    content = to_latex(_comparison(deps, items, baseline, metric))
    return _download(content, "application/x-tex; charset=utf-8", "comparacao.tex")
