"""Memory telemetry: the active profile, resident models, and process/machine memory."""
from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.core.memory import stats
from app.core.memory.manager import ModelManager, get_model_manager
from app.core.memory.profile import active_profile

router = APIRouter()


@router.get("/system/memory")
def memory(models: ModelManager = Depends(get_model_manager)) -> dict:
    """What the memory profile allows and what is using memory right now."""
    return {
        "profile": asdict(active_profile()),
        "total_bytes": stats.total_memory_bytes(),
        "available_bytes": stats.available_memory_bytes(),
        "process_memory_bytes": stats.process_memory_bytes(),
        "loaded_models": [asdict(m) for m in models.loaded()],
    }
