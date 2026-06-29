"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Return the application status."""
    return {"status": "ok"}
