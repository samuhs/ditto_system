"""Tests for GET /comparisons: Combinações of one or more Experimentos against a Linha de base."""
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.experiments import get_experiment_deps
from app.core.db.base import Base
from app.core.db.models import Experiment, ExperimentRun, RunResult
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.orchestrator import ExperimentDeps
from app.main import create_app


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    deps = ExperimentDeps(
        store=QdrantStore(client=QdrantClient(":memory:")),
        session_factory=session_factory,
        llm_factory=lambda name, **kw: None,
        embedder_factory=lambda name, **kw: None,
    )
    app = create_app()
    app.dependency_overrides[get_experiment_deps] = lambda: deps
    return TestClient(app), session_factory


def _experiment(session_factory, name, runs, base="guia", status="done",
                metrics=("answer_correctness", "token_f1")) -> tuple[int, list[int]]:
    """An Experimento with one run per entry of `runs`: (llm, rag, {question: scores | answer}).

    A value that is a str is stored as the generated answer with no scores (an [ERRO]).
    """
    session = session_factory()
    experiment = Experiment(name=name, status=status, config={"base": base, "metrics": list(metrics)})
    for llm, rag, answers in runs:
        run = ExperimentRun(chunking="markdown", embedding="e5", rag_technique=rag,
                            retriever="similarity", llm=llm, status="done")
        for question, value in answers.items():
            qtype = "ponte" if question.startswith("p") else "simples"
            if isinstance(value, str):
                run.results.append(RunResult(question=question, generated_answer=value, scores={},
                                             question_type=qtype))
            else:
                run.results.append(RunResult(question=question, generated_answer="Resposta.",
                                             scores=value, question_type=qtype))
        experiment.runs.append(run)
    session.add(experiment)
    session.commit()
    ids = experiment.id, [r.id for r in experiment.runs]
    session.close()
    return ids


def _ac(*values):
    return {f"q{i}": {"answer_correctness": v, "token_f1": v / 2} for i, v in enumerate(values, start=1)}


def test_items_from_two_experimentos_are_paired_against_the_linha_de_base(env):
    client, sf = env
    base_exp, [base_run] = _experiment(sf, "fase-1", [("qwen2.5", "naive", _ac(0.5, 0.5, 0.5))])
    other_exp, [other_run] = _experiment(sf, "fase-3", [("qwen3.5", "naive", _ac(0.7, 0.7, 0.7))],
                                         status="running")
    items = f"{base_exp}:{base_run},{other_exp}:{other_run}"

    body = client.get(f"/comparisons?items={items}").json()

    assert body["baseline"] == f"{base_exp}:{base_run}"  # the first item by default
    assert body["metric"] == "answer_correctness"
    assert body["base"] == "guia"
    baseline, other = body["items"]
    assert baseline["diff"] is None and baseline["n"] == 3 and not baseline["partial"]
    assert baseline["means"]["answer_correctness"] == pytest.approx(0.5)
    assert other["llm"] == "qwen3.5" and other["rag"] == "naive"
    assert other["experiment_id"] == other_exp and other["experiment_name"] == "fase-3"
    assert other["partial"]  # its Experimento is still running
    assert other["n"] == 3
    assert other["means"]["token_f1"] == pytest.approx(0.35)
    assert other["diff"]["mean"] == pytest.approx(0.2)
    assert (other["diff"]["low"], other["diff"]["high"]) == (pytest.approx(0.2), pytest.approx(0.2))
    assert other["diff"]["significant"]


def test_pairs_only_questions_with_a_valid_score_on_both_sides(env):
    """q2 failed on the item ([ERRO], no score) and q4 never ran on the Linha de base."""
    client, sf = env
    exp, [base_run, item_run] = _experiment(sf, "pares", [
        ("a", "naive", _ac(0.5, 0.5, 0.5)),
        ("b", "naive", {**_ac(0.9, 0.0, 0.9, 0.9), "q2": "[ERRO: timeout]"}),
    ])
    body = client.get(f"/comparisons?items={exp}:{base_run},{exp}:{item_run}").json()
    item = body["items"][1]
    assert item["n"] == 2  # q1 and q3
    assert item["diff"]["mean"] == pytest.approx(0.4)


def test_the_baseline_and_the_metric_can_be_chosen(env):
    client, sf = env
    exp, [a, b] = _experiment(sf, "escolha", [("a", "naive", _ac(0.4, 0.4)), ("b", "naive", _ac(0.8, 0.8))])
    body = client.get(f"/comparisons?items={exp}:{a},{exp}:{b}&baseline={exp}:{b}&metric=token_f1").json()
    assert body["baseline"] == f"{exp}:{b}" and body["metric"] == "token_f1"
    item_a = next(i for i in body["items"] if i["id"] == f"{exp}:{a}")
    assert item_a["diff"]["mean"] == pytest.approx(-0.2)


def test_without_answer_correctness_the_metric_defaults_to_the_baselines_first(env):
    client, sf = env
    scores = {"q1": {"context_all_hops": 1.0}}
    exp, [a] = _experiment(sf, "recuperacao", [("a", "naive", scores)], metrics=("context_all_hops",))
    assert client.get(f"/comparisons?items={exp}:{a}").json()["metric"] == "context_all_hops"


def test_a_metric_an_item_lacks_shows_as_missing(env):
    """closed_book has no context metrics: its mean is null, not zero."""
    client, sf = env
    exp, [a, b] = _experiment(sf, "faltando", [
        ("a", "naive", {"q1": {"answer_correctness": 0.5, "context_hit": 1.0}}),
        ("a", "closed_book", {"q1": {"answer_correctness": 0.3}}),
    ])
    body = client.get(f"/comparisons?items={exp}:{a},{exp}:{b}").json()
    assert body["items"][1]["means"]["context_hit"] is None
    assert set(body["metrics"]) == {"answer_correctness", "context_hit"}


def test_items_that_cannot_be_paired_are_listed_with_the_reason(env):
    client, sf = env
    exp, [a, b] = _experiment(sf, "excluidos", [
        ("a", "naive", {"q1": {"answer_correctness": 0.5}}),
        ("b", "naive", {"q9": {"answer_correctness": 0.5}}),
    ])
    body = client.get(f"/comparisons?items={exp}:{a},{exp}:{b},{exp}:999").json()
    assert [i["id"] for i in body["items"]] == [f"{exp}:{a}"]
    reasons = {e["id"]: e["reason"] for e in body["excluded"]}
    assert "nenhuma pergunta em comum" in reasons[f"{exp}:{b}"]
    assert "não existe" in reasons[f"{exp}:999"]


def test_an_unknown_experimento_is_404(env):
    client, _ = env
    response = client.get("/comparisons?items=999:1")
    assert response.status_code == 404
    assert "999" in response.json()["detail"]


def test_a_malformed_item_is_422(env):
    client, _ = env
    assert client.get("/comparisons?items=abc").status_code == 422


def test_the_baseline_must_be_one_of_the_items(env):
    client, sf = env
    exp, [a] = _experiment(sf, "fora", [("a", "naive", _ac(0.5))])
    assert client.get(f"/comparisons?items={exp}:{a}&baseline={exp}:77").status_code == 422
