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


def test_add_missing_columns_upgrades_an_old_run_result_table():
    from sqlalchemy import create_engine, inspect, text

    from app.core.db.base import add_missing_columns

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE run_result (id INTEGER PRIMARY KEY, question VARCHAR)"))
    add_missing_columns(engine, {"run_result": {"reference_contexts": "JSON"}})
    add_missing_columns(engine, {"run_result": {"reference_contexts": "JSON"}})  # idempotent
    assert "reference_contexts" in {c["name"] for c in inspect(engine).get_columns("run_result")}
