"""Endpoint de verificacao de saude."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Retorna o estado da aplicacao."""
    return {"status": "ok"}
