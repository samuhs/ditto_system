"""Endpoints to create and inspect experiments."""
import csv
import io
import re
import unicodedata
from datetime import timezone
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.db.base import SessionLocal
from app.core.db.models import Experiment
from app.core.memory.manager import get_model_manager
from app.core.memory.profile import active_profile
from app.core.prompts import PROMPT_SPECS, load_technique
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.naming import generate_experiment_name
from app.experiments.orchestrator import ExperimentDeps, _pause_requested, request_pause, run_experiment
from app.experiments.preflight import memory_warnings
from app.experiments.schemas import ExperimentConfig, index_pairs

router = APIRouter()


def _iso_utc(dt):
    """Serialize a naive-UTC datetime as a tz-aware ISO string (or None)."""
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _result_rows(experiment: Experiment) -> list[dict]:
    """Flatten an experiment's runs into one row per (combination, question)."""
    rows = []
    for run in experiment.runs:
        for result in run.results:
            rows.append(
                {
                    "chunking": run.chunking,
                    "embedding": run.embedding,
                    "rag": run.rag_technique,
                    "retriever": run.retriever,
                    "llm": run.llm or "gemini",
                    "question": result.question,
                    "reference": result.reference_answer,
                    "answer": result.generated_answer,
                    "scores": result.scores,
                    "latency_ms": result.latency_ms,
                    "tokens": result.tokens,
                }
            )
    return rows


def _safe_filename(name: str) -> str:
    """Reduce an experiment name to an ASCII-only, filesystem-safe stem."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("_") or "experiment"


def _results_csv(rows: list[dict]) -> str:
    """Render result rows as CSV with one column per metric plus the row mean."""
    metric_keys = sorted({k for row in rows for k in row["scores"]})
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["chunking", "embedding", "rag", "retriever", "llm",
         "pergunta", "resposta_referencia", "resposta",
         *metric_keys, "media", "latency_ms", "tokens"]
    )
    for row in rows:
        scores = row["scores"]
        mean = sum(scores.values()) / len(scores) if scores else ""
        writer.writerow(
            [row["chunking"], row["embedding"], row["rag"], row["retriever"], row["llm"],
             row["question"], row["reference"] or "", row["answer"],
             *(scores.get(k, "") for k in metric_keys), mean, row["latency_ms"], row["tokens"]]
        )
    return buffer.getvalue()


def _snapshot_prompts(config: ExperimentConfig) -> dict[str, dict[str, str]]:
    """Capture the current prompts of every technique the experiment uses."""
    techniques = list(config.rags)
    if "multi_query" in config.retrievers:
        techniques.append("multi_query")
    return {t: load_technique(t) for t in techniques if t in PROMPT_SPECS}


def get_experiment_deps() -> ExperimentDeps:
    """FastAPI dependency providing the production experiment dependencies."""
    return ExperimentDeps(store=QdrantStore(), session_factory=SessionLocal, models=get_model_manager())


def _check_indexes_exist(config: ExperimentConfig, store: QdrantStore) -> None:
    """Reject index pairs that were never ingested for the base (422)."""
    existing = set(store.list_collections())
    missing = [
        f"{chunking} × {embedding}"
        for chunking, embedding in index_pairs(config)
        if collection_name(config.base, chunking, embedding) not in existing
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"base '{config.base}' has no index for: {', '.join(missing)}",
        )


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
    if parsed.indexes is not None:
        _check_indexes_exist(parsed, deps.store)
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
    warnings = memory_warnings(parsed, active_profile())
    return {"id": experiment_id, "name": name, "status": "pending", "warnings": warnings}


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
def list_experiments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> dict:
    """List experiments (paginated), most recent first."""
    session = deps.session_factory()
    try:
        query = session.query(Experiment).order_by(Experiment.id.desc())
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        items = [
            {
                "id": e.id,
                "name": e.name,
                "status": e.status,
                "created_at": _iso_utc(e.created_at),
            }
            for e in rows
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}
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
        results = _result_rows(experiment)
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
            "created_at": _iso_utc(experiment.created_at),
            "finished_at": _iso_utc(experiment.finished_at),
            "pause_requested": _pause_requested(experiment_id),
            "error": cfg.get("error") or None,
            "progress": {
                "completed": completed_combos,
                "total": total_combos,
                # Staged runs: "generating", then "evaluating" (scoring the answers).
                "phase": cfg.get("phase"),
            },
            "prompts": cfg.get("prompts"),
            "results": results,
        }
    finally:
        session.close()


@router.get("/experiments/{experiment_id}/export.csv")
def export_experiment_csv(
    experiment_id: int,
    deps: ExperimentDeps = Depends(get_experiment_deps),
) -> Response:
    """Download every per-question result of an experiment as a CSV file."""
    session = deps.session_factory()
    try:
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        content = "\ufeff" + _results_csv(_result_rows(experiment))
        filename = f"{_safe_filename(experiment.name)}.csv"
    finally:
        session.close()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
