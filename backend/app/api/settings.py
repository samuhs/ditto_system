"""Endpoints for runtime-editable app settings (Gemini key, LLM providers, evaluation embedder)."""
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config.runtime import (
    get_eval_embedding,
    get_gemini_key,
    get_stall_limit_s,
    set_eval_embedding,
    set_gemini_key,
    set_stall_limit_s,
)
from app.core.embedding.base import embedding_registry
from app.core.evaluation.base import evaluation_registry
from app.core.evaluation.runner import metrics_need_embedder
from app.core.llm import providers as llm_providers
from app.core.llm import usage
from app.core.llm.chat_model import ChatModelLLM, build_chat_model
from app.core.memory.manager import is_local_embedding

router = APIRouter()


class GeminiKeyBody(BaseModel):
    key: str


class EvalEmbeddingBody(BaseModel):
    name: str


class StallLimitBody(BaseModel):
    minutes: float


class ProviderBody(BaseModel):
    kind: str
    base_url: str | None = None
    # None keeps the stored key; "" clears it.
    api_key: str | None = None
    api_key_env: str | None = None
    models: list[str] = []
    params: dict = {}
    local: bool = False
    max_tokens_in_body: bool | None = None


class ProviderTestBody(BaseModel):
    model: str
    prompt: str = "Responda apenas: OK"
    max_tokens: int = 16


@router.get("/settings")
def get_settings_view() -> dict:
    """Return non-secret settings state for the UI."""
    return {
        "gemini_api_key_set": get_gemini_key() is not None,
        "stall_limit_minutes": get_stall_limit_s() / 60,
    }


@router.put("/settings/stall-limit")
def update_stall_limit(body: StallLimitBody) -> dict:
    """Set the Travamento limit (minutes a run may go without a heartbeat)."""
    if body.minutes <= 0:
        raise HTTPException(status_code=422, detail="minutes must be positive")
    set_stall_limit_s(body.minutes * 60)
    return {"stall_limit_minutes": get_stall_limit_s() / 60}


@router.put("/settings/gemini-key")
def update_gemini_key(body: GeminiKeyBody) -> dict:
    """Set or clear (empty string) the Gemini API key."""
    set_gemini_key(body.key)
    return {"gemini_api_key_set": get_gemini_key() is not None}


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


@router.get("/settings/llm-providers")
def list_llm_providers() -> list[dict]:
    """Every LLM provider (built-in and configured), without secrets."""
    return [p.public() for p in llm_providers.all_providers().values()]


@router.put("/settings/llm-providers/{provider_id}")
def save_llm_provider(provider_id: str, body: ProviderBody) -> dict:
    """Create or replace a provider. Omit api_key to keep the stored one; send "" to clear it."""
    try:
        provider = llm_providers.save_provider(provider_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return provider.public()


@router.delete("/settings/llm-providers/{provider_id}")
def delete_llm_provider(provider_id: str) -> dict:
    """Remove a configured provider (built-ins cannot be removed)."""
    if provider_id in llm_providers.RESERVED_IDS:
        raise HTTPException(status_code=422, detail="provedores embutidos não podem ser removidos")
    if not llm_providers.delete_provider(provider_id):
        raise HTTPException(status_code=404, detail=f"provedor {provider_id!r} não existe")
    return {"deleted": provider_id}


@router.post("/settings/llm-providers/{provider_id}/test")
def test_llm_provider(provider_id: str, body: ProviderTestBody) -> dict:
    """Make one short call to check the URL, key and model; reports the answer and token usage."""
    try:
        provider = llm_providers.get_provider(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    start = time.perf_counter()
    try:
        llm = ChatModelLLM(build_chat_model(provider, body.model, temperature=0, max_tokens=body.max_tokens,
                                            timeout=60))
        with usage.track() as totals:
            answer = llm.generate(body.prompt)
    except Exception as exc:  # noqa: BLE001  any provider error is the test's answer
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
    return {"ok": True, "answer": answer, "latency_ms": int((time.perf_counter() - start) * 1000),
            "usage": dict(totals)}
