"""Endpoints for runtime-editable app settings (Gemini key, named Ollama models)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config.runtime import (
    get_gemini_key,
    get_ollama_models,
    set_gemini_key,
    set_ollama_models,
)
from app.core.llm.base import llm_registry

router = APIRouter()


class GeminiKeyBody(BaseModel):
    key: str


class OllamaModelBody(BaseModel):
    id: str
    model: str


class OllamaModelsBody(BaseModel):
    models: list[OllamaModelBody]


@router.get("/settings")
def get_settings_view() -> dict:
    """Return non-secret settings state for the UI."""
    return {
        "gemini_api_key_set": get_gemini_key() is not None,
        "ollama_models": get_ollama_models(),
    }


@router.put("/settings/gemini-key")
def update_gemini_key(body: GeminiKeyBody) -> dict:
    """Set or clear (empty string) the Gemini API key."""
    set_gemini_key(body.key)
    return {"gemini_api_key_set": get_gemini_key() is not None}


@router.put("/settings/ollama-models")
def update_ollama_models(body: OllamaModelsBody) -> dict:
    """Validate and persist the named Ollama models."""
    models = [m.model_dump() for m in body.models]
    try:
        set_ollama_models(models, reserved=set(llm_registry.names()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ollama_models": get_ollama_models()}
