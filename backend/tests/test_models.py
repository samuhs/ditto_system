"""Tests for SQLAlchemy models and relationships."""
from app.core.db.models import Experiment, ExperimentRun, RunResult


def test_experiment_run_result_relationship(db_session):
    """Verify that Experiment -> ExperimentRun -> RunResult relationships are persisted correctly."""
    exp = Experiment(name="brave-otter-42", status="pending", config={"k": 5})
    run = ExperimentRun(
        chunking="recursive",
        embedding="e5",
        rag_technique="naive",
        retriever="similarity",
        status="pending",
    )
    exp.runs.append(run)
    result = RunResult(
        question="Qual a capital?",
        reference_answer=None,
        generated_answer="Brasilia",
        retrieved_context=[{"text": "..."}],
        scores={"faithfulness": 0.9},
        latency_ms=120,
        tokens=42,
    )
    run.results.append(result)

    db_session.add(exp)
    db_session.commit()

    stored = db_session.query(Experiment).filter_by(name="brave-otter-42").one()
    assert stored.runs[0].results[0].generated_answer == "Brasilia"
    assert stored.runs[0].results[0].scores["faithfulness"] == 0.9
