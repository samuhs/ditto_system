"""Endpoints to build Grafos de conhecimento in the background and follow the jobs.

POST /graph-builds is the one entry point: the ingestion calls the same
start_graph_build after creating the Índices, and a Base that already exists
gets a Grafo by posting here, with no re-ingestion.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_graph_build_deps, get_graph_builds
from app.core.graph.jobs import ACTIVE, GraphBuildDeps, GraphBuildJob, GraphBuilds
from app.core.vectorstore.qdrant import parse_collection_name
from app.experiments.schemas import IndexPair

router = APIRouter()


class GraphBuildRequest(BaseModel):
    """Build the Grafos of these Índices of a Base with this LLM extrator."""

    base: str
    extractor: str
    # None: every Índice of the Base.
    indexes: list[IndexPair] | None = None


def check_extractor(extractor: str, deps: GraphBuildDeps) -> str:
    """The LLM extrator's name, stripped; 422 if it is empty or no LLM answers to it."""
    extractor = extractor.strip()
    if not extractor:
        raise HTTPException(status_code=422, detail="Escolha o LLM extrator do Grafo.")
    try:
        deps.llm_factory(extractor)
    except Exception as exc:  # noqa: BLE001  an unknown or unusable model name
        raise HTTPException(
            status_code=422, detail=f"LLM extrator indisponível: {extractor} ({exc})"
        ) from exc
    return extractor


def start_graph_build(
    base: str,
    extractor: str,
    indexes: list[tuple[str, str]] | None,
    builds: GraphBuilds,
    deps: GraphBuildDeps,
    background_tasks: BackgroundTasks,
) -> GraphBuildJob:
    """Validate, queue the job and run it after the response (422 with a PT-BR reason).

    A Grafo already current for an Índice is kept; the others are built, asking
    the LLM extrator only for chunks the extraction cache does not hold.
    """
    extractor = check_extractor(extractor, deps)
    existing = [
        (parsed[1], parsed[2])
        for parsed in map(parse_collection_name, sorted(deps.store.list_collections()))
        if parsed is not None and parsed[0] == base
    ]
    if not existing:
        raise HTTPException(status_code=422, detail=f'A base "{base}" não tem Índices.')
    chosen = existing if indexes is None else list(dict.fromkeys(indexes))
    missing = [f"{c} × {e}" for c, e in chosen if (c, e) not in existing]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f'A base "{base}" não tem estes Índices: {", ".join(missing)}.',
        )
    job = builds.create(base, extractor, chosen)
    background_tasks.add_task(builds.run, job.id, deps)
    return job


@router.post("/graph-builds", status_code=202, response_model=GraphBuildJob)
def create_graph_build(
    body: GraphBuildRequest,
    background_tasks: BackgroundTasks,
    builds: GraphBuilds = Depends(get_graph_builds),
    deps: GraphBuildDeps = Depends(get_graph_build_deps),
) -> GraphBuildJob:
    """Build the Grafos de conhecimento of a Base's Índices in the background."""
    indexes = None if body.indexes is None else [(i.chunking, i.embedding) for i in body.indexes]
    return start_graph_build(body.base, body.extractor, indexes, builds, deps, background_tasks)


@router.get("/graph-builds", response_model=list[GraphBuildJob])
def list_graph_builds(
    base: str | None = None, builds: GraphBuilds = Depends(get_graph_builds)
) -> list[GraphBuildJob]:
    """The build jobs of this API process (of one Base, if given), newest first."""
    return builds.list_jobs(base)


def _job(builds: GraphBuilds, job_id: int) -> GraphBuildJob:
    job = builds.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="graph build not found")
    return job


@router.get("/graph-builds/{job_id}", response_model=GraphBuildJob)
def get_graph_build(job_id: int, builds: GraphBuilds = Depends(get_graph_builds)) -> GraphBuildJob:
    """A job: its status and, per Índice, chunks extracted / total."""
    return _job(builds, job_id)


@router.post("/graph-builds/{job_id}/pause", response_model=GraphBuildJob)
def pause_graph_build(job_id: int, builds: GraphBuilds = Depends(get_graph_builds)) -> GraphBuildJob:
    """Stop the job at its next chunk; the chunks already extracted stay cached."""
    job = _job(builds, job_id)
    if job.status not in ACTIVE:
        raise HTTPException(
            status_code=409, detail=f"A construção não está em andamento (status: {job.status})."
        )
    builds.request_pause(job_id)
    return _job(builds, job_id)


@router.post("/graph-builds/{job_id}/resume", status_code=202, response_model=GraphBuildJob)
def resume_graph_build(
    job_id: int,
    background_tasks: BackgroundTasks,
    builds: GraphBuilds = Depends(get_graph_builds),
    deps: GraphBuildDeps = Depends(get_graph_build_deps),
) -> GraphBuildJob:
    """Run a paused (or failed) job again: only chunks not yet extracted go to the LLM."""
    job = _job(builds, job_id)
    if job.status not in ("paused", "failed"):
        raise HTTPException(
            status_code=409, detail=f"Só uma construção pausada ou com falha pode ser retomada "
            f"(status: {job.status})."
        )
    job = builds.resume(job_id)
    background_tasks.add_task(builds.run, job_id, deps)
    return job
