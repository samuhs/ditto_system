"""Endpoints to create and inspect experiments."""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.core.db.base import SessionLocal
from app.core.db.models import Experiment
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.csv_loader import parse_questions_csv
from app.experiments.naming import generate_experiment_name
from app.experiments.orchestrator import ExperimentDeps, run_experiment
from app.experiments.schemas import ExperimentConfig

router = APIRouter()


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
    parsed = ExperimentConfig.model_validate_json(config)
    if not parsed.name:
        parsed.name = generate_experiment_name()
    csv_text = (await questions.read()).decode("utf-8")
    items = parse_questions_csv(csv_text)

    session = deps.session_factory()
    try:
        experiment = Experiment(name=parsed.name, status="pending", config=parsed.model_dump())
        session.add(experiment)
        session.commit()
        session.refresh(experiment)
        experiment_id = experiment.id
        name = experiment.name
    finally:
        session.close()

    background_tasks.add_task(run_experiment, experiment_id, parsed, items, deps)
    return {"id": experiment_id, "name": name, "status": "pending"}


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
                        "question": result.question,
                        "answer": result.generated_answer,
                        "scores": result.scores,
                        "latency_ms": result.latency_ms,
                        "tokens": result.tokens,
                    }
                )
        return {
            "id": experiment.id,
            "name": experiment.name,
            "status": experiment.status,
            "results": results,
        }
    finally:
        session.close()
