"""Endpoints for the Bases: list them with their Índices and Grafos, delete one."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.api.ingest import get_store
from app.core.catalog import BaseSummary, list_bases
from app.core.db.base import SessionLocal
from app.core.vectorstore.qdrant import QdrantStore

router = APIRouter()


def get_session_factory() -> sessionmaker[Session]:
    """FastAPI dependency providing the database session factory."""
    return SessionLocal


@router.get("/bases", response_model=list[BaseSummary])
def bases(store: QdrantStore = Depends(get_store)) -> list[BaseSummary]:
    """Every Base with its Índices and the Grafos de conhecimento built from them."""
    return list_bases(store)


@router.delete("/bases/{base}")
def delete_base(base: str, store: QdrantStore = Depends(get_store)) -> dict:
    """Delete a Base: its Índices and every Grafo de conhecimento built from them."""
    deleted = store.delete_base(base)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"base not found: {base}")
    return {"base": base, "deleted": deleted}
