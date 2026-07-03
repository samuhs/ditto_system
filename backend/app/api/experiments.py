"""Endpoints to create and inspect experiments."""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.db.base import SessionLocal
from app.core.db.models import Experiment
from app.core.prompts import PROMPT_SPECS, load_technique
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.naming import generate_experiment_name
from app.experiments.orchestrator import ExperimentDeps, _pause_requested, request_pause, run_experiment
from app.experiments.schemas import ExperimentConfig

router = APIRouter()


def _snapshot_prompts(config: ExperimentConfig) -> dict[str, dict[str, str]]:
    """Capture the current prompts of every technique the experiment uses."""
    techniques = list(config.rags)
    if "multi_query" in config.retrievers:
        techniques.append("multi_query")
    return {t: load_technique(t) for t in techniques if t in PROMPT_SPECS}


def get_experiment_deps() -> ExperimentDeps:
    """FastAPI dependency providing the production experiment dependencies."""
    return ExperimentDeps(store=QdrantStore(), session_factory=SessionLocal)


@router.post("/experiments")
async def create_experiment(
    background_tasks: BackgroundTasks,
    config: str = Form(...),
    questions: UploadFile = File(...),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Create an experiment and run it in the background."""
    try:
        parsed = ExperimentConfig.model_validate_json(config)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if not parsed.name:
        parsed.name = generate_experiment_name()
    raw = await questions.read()
    try:
        csv_text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="questions file is not valid UTF-8") from exc
    try:
        items = parse_questions_csv(csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session = deps.session_factory()
    try:
        config_dump = parsed.model_dump()
        config_dump["prompts"] = _snapshot_prompts(parsed)
        experiment = Experiment(name=parsed.name, status="pending", config=config_dump)
        session.add(experiment)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=409, detail=f"experiment name already exists: {parsed.name}"
            ) from exc
        session.refresh(experiment)
        experiment_id = experiment.id
        name = experiment.name
    finally:
        session.close()

    background_tasks.add_task(run_experiment, experiment_id, parsed, items, deps)
    return {"id": experiment_id, "name": name, "status": "pending"}


@router.post("/experiments/{experiment_id}/pause")
def pause_experiment(
    experiment_id: int,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Request a running experiment to pause at its next checkpoint."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        if experiment.status not in ("running", "pending"):
            raise HTTPException(
                status_code=409,
                detail=f"experiment is not running (status: {experiment.status})",
            )
    finally:
        session.close()
    request_pause(experiment_id)
    return {"id": experiment_id, "status": "pausing"}


@router.get("/experiments")
def list_experiments(deps: ExperimentDeps = Depends(get_experiment_deps)) -> list[dict]:
    """List experiments, most recent first."""
    session = deps.session_factory()
    try:
        rows = session.query(Experiment).order_by(Experiment.id.desc()).all()
        return [{"id": e.id, "name": e.name, "status": e.status} for e in rows]
    finally:
        session.close()


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: int,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """Return an experiment with its per-question results."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        results = []
        for run in experiment.runs:
            for result in run.results:
                results.append(
                    {
                        "chunking": run.chunking,
                        "embedding": run.embedding,
                        "rag": run.rag_technique,
                        "retriever": run.retriever,
                        "llm": run.llm or "gemini",
                        "question": result.question,
                        "answer": result.generated_answer,
                        "scores": result.scores,
                        "latency_ms": result.latency_ms,
                        "tokens": result.tokens,
                    }
                )
        cfg = experiment.config or {}
        n_llms = len(cfg.get("llms", [])) or 1
        total_combos = (
            len(cfg.get("chunkings", []))
            * len(cfg.get("embeddings", []))
            * len(cfg.get("rags", []))
            * len(cfg.get("retrievers", []))
            * n_llms
        )
        completed_combos = sum(1 for run in experiment.runs if run.status == "done")
        return {
            "id": experiment.id,
            "name": experiment.name,
            "status": experiment.status,
            "pause_requested": _pause_requested(experiment_id),
            "error": cfg.get("error") or None,
            "progress": {"completed": completed_combos, "total": total_combos},
            "prompts": cfg.get("prompts"),
            "results": results,
        }
    finally:
        session.close()
