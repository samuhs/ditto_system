"""Memory profiles: how many local models stay resident and how hard the machine is pushed."""
import logging
from dataclasses import dataclass, replace

from app.core.config.settings import get_settings

logger = logging.getLogger(__name__)

CPU = "cpu"
AUTO = "auto"


@dataclass(frozen=True)
class MemoryProfile:
    """Limits one memory profile applies."""

    name: str
    max_local_models: int
    # "cpu" always; "auto" lets the device policy pick the GPU when the LLM leaves it free.
    embedding_device: str
    max_concurrency: int


PROFILES: dict[str, MemoryProfile] = {
    "low": MemoryProfile("low", max_local_models=1, embedding_device=CPU, max_concurrency=2),
    "standard": MemoryProfile("standard", max_local_models=3, embedding_device=AUTO, max_concurrency=32),
}


def active_profile() -> MemoryProfile:
    """The profile named by MEMORY_PROFILE, with explicit env overrides applied."""
    settings = get_settings()
    name = settings.memory_profile.strip().lower()
    if name not in PROFILES:
        logger.warning("unknown MEMORY_PROFILE %r; using 'standard'", settings.memory_profile)
        name = "standard"
    profile = PROFILES[name]
    if settings.max_local_models is not None:
        profile = replace(profile, max_local_models=max(1, settings.max_local_models))
    if settings.max_experiment_concurrency is not None:
        profile = replace(profile, max_concurrency=max(1, settings.max_experiment_concurrency))
    # Only CPU can be forced: the GPU belongs to the LLM (see app.core.memory.device).
    if (settings.embedding_device or "").strip().lower() == CPU:
        profile = replace(profile, embedding_device=CPU)
    return profile
