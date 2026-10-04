"""Endpoints for the Bases: list them with their Índices and Grafos, delete one."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.api.ingest import get_store
from app.core.catalog import BaseSummary, list_bases
from app.core.db.base import SessionLocal
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.usage import bases_in_use

router = APIRouter()


def get_session_factory() -> sessionmaker[Session]:
    """FastAPI dependency providing the database session factory."""
    return SessionLocal


@router.get("/bases", response_model=list[BaseSummary])
def bases(
    store: QdrantStore = Depends(get_store),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> list[BaseSummary]:
    """Every Base with its Índices, their Grafos de conhecimento, and whether it is in use."""
    with session_factory() as session:
        in_use = bases_in_use(session)
    return [
        summary.model_copy(update={"in_use": in_use.get(summary.name)})
        for summary in list_bases(store)
    ]


@router.delete("/bases/{base}")
def delete_base(
    base: str,
    store: QdrantStore = Depends(get_store),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> dict:
    """Delete a Base: its Índices and every Grafo de conhecimento built from them.

    Refused (409) while an experiment or a Grafo build is using the Base.
    """
    with session_factory() as session:
        reason = bases_in_use(session).get(base)
    if reason is not None:
        raise HTTPException(status_code=409, detail=reason)
    deleted = store.delete_base(base)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"base not found: {base}")
    return {"base": base, "deleted": deleted}
