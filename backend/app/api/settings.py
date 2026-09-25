"""Endpoints for runtime-editable app settings (Gemini key, named Ollama models)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config.runtime import (
    get_eval_embedding,
    get_gemini_key,
    get_ollama_models,
    set_eval_embedding,
    set_gemini_key,
    set_ollama_models,
)
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.evaluation.runner import metrics_need_embedder
from app.core.llm.base import llm_registry
from app.core.memory.manager import is_local_embedding

router = APIRouter()


class GeminiKeyBody(BaseModel):
    key: str


class OllamaModelBody(BaseModel):
    id: str
    model: str


class OllamaModelsBody(BaseModel):
    models: list[OllamaModelBody]


class EvalEmbeddingBody(BaseModel):
    name: str


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


@router.get("/settings/evaluation")
def get_evaluation_settings() -> dict:
    """The default evaluation embedder, the candidates, and what each metric depends on."""
    return {
        "eval_embedding": get_eval_embedding(),
        "embeddings": [
            {"name": name, "local": is_local_embedding(name)} for name in embedding_registry.names()
        ],
        "metrics": [
            {
                "name": name,
                "uses_embedding": metrics_need_embedder([name]),
                "requires_reference": evaluation_registry.get(name).requires_reference,
            }
            for name in evaluation_registry.names()
        ],
    }


@router.put("/settings/eval-embedding")
def update_eval_embedding(body: EvalEmbeddingBody) -> dict:
    """Set the embedder that scores experiments that do not name one."""
    if body.name not in embedding_registry.names():
        raise HTTPException(status_code=422, detail=f"unknown embedding: {body.name!r}")
    set_eval_embedding(body.name)
    return {"eval_embedding": get_eval_embedding()}
