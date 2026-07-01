"""Prompt management: file-backed templates per technique with defaults."""
from app.core.prompts.loader import (
    DEFAULT_PROMPTS,
    PROMPT_SPECS,
    load_all,
    load_prompt,
    load_technique,
    prompts_dir,
    save_prompt,
    validate_placeholders,
)

__all__ = [
    "DEFAULT_PROMPTS",
    "PROMPT_SPECS",
    "load_all",
    "load_prompt",
    "load_technique",
    "prompts_dir",
    "save_prompt",
    "validate_placeholders",
]
