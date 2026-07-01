"""Endpoints to view and edit prompt templates per technique."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.prompts import PROMPT_SPECS, load_all, save_prompt

router = APIRouter()


class PromptUpdate(BaseModel):
    """Body for updating a prompt template."""

    text: str


@router.get("/prompts")
def list_prompts() -> dict:
    """Return every technique's prompts and their required placeholders."""
    texts = load_all()
    return {
        technique: {
            key: {
                "text": texts[technique][key],
                "required_placeholders": sorted(PROMPT_SPECS[technique][key]),
            }
            for key in PROMPT_SPECS[technique]
        }
        for technique in PROMPT_SPECS
    }


@router.put("/prompts/{technique}/{key}")
def update_prompt(technique: str, key: str, body: PromptUpdate) -> dict:
    """Validate placeholders and persist a prompt template."""
    if technique not in PROMPT_SPECS or key not in PROMPT_SPECS.get(technique, {}):
        raise HTTPException(status_code=404, detail=f"unknown prompt: {technique}/{key}")
    try:
        save_prompt(technique, key, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"technique": technique, "key": key, "text": body.text}
