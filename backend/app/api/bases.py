"""Endpoints for the Bases: list them with their Índices and Grafos, delete one."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_graph_builds, get_session_factory, get_store
from app.core.catalog import BaseSummary, list_bases
from app.core.graph.jobs import GraphBuilds
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.usage import bases_in_use

router = APIRouter()


@router.get("/bases", response_model=list[BaseSummary])
def bases(
    store: QdrantStore = Depends(get_store),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    builds: GraphBuilds = Depends(get_graph_builds),
) -> list[BaseSummary]:
    """Every Base with its Índices, their Grafos, its Grafo builds, and whether it is in use."""
    with session_factory() as session:
        in_use = bases_in_use(session, builds)
    jobs = builds.list_jobs()
    return [
        summary.model_copy(update={
            "in_use": in_use.get(summary.name),
            # Builds still running, queued or paused, with their progress.
            "graph_builds": [
                j for j in jobs if j.base == summary.name and j.status in ("pending", "running", "paused")
            ],
        })
        for summary in list_bases(store)
    ]


@router.delete("/bases/{base}")
def delete_base(
    base: str,
    store: QdrantStore = Depends(get_store),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    builds: GraphBuilds = Depends(get_graph_builds),
) -> dict:
    """Delete a Base: its Índices and every Grafo de conhecimento built from them.

    Refused (409) while an experiment or a Grafo build is using the Base.
    """
    with session_factory() as session:
        reason = bases_in_use(session, builds).get(base)
    if reason is not None:
        raise HTTPException(status_code=409, detail=reason)
    deleted = store.delete_base(base)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"base not found: {base}")
    return {"base": base, "deleted": deleted}
