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
            qtype = {"p": "ponte", "c": "comparacao"}.get(question[0], "simples")
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


def test_friedman_runs_over_the_questions_every_item_answered(env):
    """The worked example of the stats tests, as three Combinações: chi2 = 7/6, df 2."""
    client, sf = env
    exp, runs = _experiment(sf, "friedman", [
        ("a", "naive", _ac(1.0, 1.0, 0.5, 0.3)),
        ("b", "naive", _ac(0.0, 1.0, 0.2)),  # q4 missing: not a complete block
        ("c", "naive", _ac(0.0, 0.0, 0.9, 0.3)),
    ])
    items = ",".join(f"{exp}:{r}" for r in runs)
    friedman = client.get(f"/comparisons?items={items}").json()["friedman"]
    assert friedman["chi2"] == pytest.approx(7 / 6)
    assert friedman["df"] == 2 and friedman["n"] == 3
    assert friedman["p"] == pytest.approx(0.5580351457700471)


def test_friedman_needs_two_paired_items(env):
    client, sf = env
    exp, [a] = _experiment(sf, "sozinho", [("a", "naive", _ac(0.5))])
    friedman = client.get(f"/comparisons?items={exp}:{a}").json()["friedman"]
    assert "duas" in friedman["reason"] and "chi2" not in friedman


def test_friedman_needs_a_question_every_item_answered(env):
    client, sf = env
    exp, runs = _experiment(sf, "sem-bloco", [
        ("a", "naive", {"q1": {"answer_correctness": 0.5}, "q2": {"answer_correctness": 0.5}}),
        ("b", "naive", {"q1": {"answer_correctness": 0.6}}),
        ("c", "naive", {"q2": {"answer_correctness": 0.7}}),
    ])
    items = ",".join(f"{exp}:{r}" for r in runs)
    friedman = client.get(f"/comparisons?items={items}").json()["friedman"]
    assert "todas" in friedman["reason"]


def test_the_difference_by_tipo_de_pergunta(env):
    """Better on single-passage questions, worse on ponte; comparacao never paired."""
    client, sf = env
    ac = lambda v: {"answer_correctness": v}  # noqa: E731
    exp, [a, b] = _experiment(sf, "por-tipo", [
        ("a", "naive", {"q1": ac(0.5), "q2": ac(0.5), "p1": ac(0.5), "p2": ac(0.5), "c1": ac(0.5)}),
        ("b", "agentic", {"q1": ac(0.7), "q2": ac(0.7), "p1": ac(0.4), "p2": ac(0.4)}),
    ])
    by_type = client.get(f"/comparisons?items={exp}:{a},{exp}:{b}").json()["by_type"]
    assert by_type["types"] == ["simples", "ponte", "comparacao"]
    [row] = by_type["rows"]
    assert row["id"] == f"{exp}:{b}"
    assert row["cells"]["simples"]["mean"] == pytest.approx(0.2)
    assert row["cells"]["simples"]["n"] == 2 and row["cells"]["simples"]["significant"]
    assert row["cells"]["ponte"]["mean"] == pytest.approx(-0.1)
    assert row["cells"]["comparacao"] is None


def test_items_of_another_base_are_shown_unpaired(env):
    client, sf = env
    guia, [g] = _experiment(sf, "guia", [("a", "naive", _ac(0.5, 0.5))])
    faq, [f] = _experiment(sf, "faq", [("a", "naive", _ac(0.2, 0.4, 0.6, 0.8))], base="faq")

    body = client.get(f"/comparisons?items={guia}:{g},{faq}:{f}").json()
    assert [i["id"] for i in body["items"]] == [f"{guia}:{g}"]
    assert body["excluded"] == []
    [other] = body["other_bases"]
    assert other["id"] == f"{faq}:{f}" and other["base"] == "faq" and other["n"] == 4
    assert other["mean"]["mean"] == pytest.approx(0.5)
    assert other["mean"]["low"] < 0.5 < other["mean"]["high"]
    assert "diff" not in other


def test_the_linha_de_base_decides_which_base_is_paired(env):
    client, sf = env
    guia, [g] = _experiment(sf, "guia", [("a", "naive", _ac(0.5, 0.5))])
    faq, [f] = _experiment(sf, "faq", [("a", "naive", _ac(0.2, 0.4))], base="faq")
    body = client.get(f"/comparisons?items={guia}:{g},{faq}:{f}&baseline={faq}:{f}").json()
    assert body["base"] == "faq"
    assert [i["id"] for i in body["other_bases"]] == [f"{guia}:{g}"]


def _export_fixture(sf):
    guia, [a, b] = _experiment(sf, "fase_3", [
        ("qwen2.5", "naive", _ac(0.5, 0.5, 0.5)),
        ("qwen3.5", "naive", _ac(0.7, 0.7, 0.7)),
    ])
    faq, [f] = _experiment(sf, "faq", [("qwen2.5", "naive", _ac(0.2, 0.4))], base="faq")
    return f"items={guia}:{a},{guia}:{b},{faq}:{f}", (guia, a, b, faq, f)


def test_csv_export_has_one_row_per_item_with_the_page_columns(env):
    import csv
    import io

    client, sf = env
    query, (guia, a, b, faq, f) = _export_fixture(sf)
    response = client.get(f"/comparisons/export.csv?{query}")
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8").lstrip("﻿"))))
    assert [r["item"] for r in rows] == [f"{guia}:{a}", f"{guia}:{b}", f"{faq}:{f}"]
    paired = rows[1]
    assert paired["llm"] == "qwen3.5" and paired["experimento"] == "fase_3"
    assert paired["perguntas"] == "3" and paired["linha_de_base"] == "não"
    assert float(paired["diferenca"]) == pytest.approx(0.2)
    assert paired["significativa"] == "sim"
    assert float(paired["answer_correctness"]) == pytest.approx(0.7)
    assert float(paired["diferenca_simples"]) == pytest.approx(0.2)
    assert rows[0]["linha_de_base"] == "sim" and rows[0]["diferenca"] == ""
    other = rows[2]
    assert other["pareamento"] == "outra Base" and other["diferenca"] == ""
    assert float(other["ic_inferior"]) <= 0.3 <= float(other["ic_superior"])


def test_latex_export_is_a_booktabs_table_in_the_papers_format(env):
    client, sf = env
    query, _ = _export_fixture(sf)
    tex = client.get(f"/comparisons/export.tex?{query}").content.decode("utf-8")
    assert "\\begin{tabular}" in tex and "\\toprule" in tex and "\\bottomrule" in tex
    assert tex.count("\\begin{tabular}") == tex.count("\\end{tabular}")
    assert "+0.200*~[0.200, 0.200]" in tex  # mean, * when significant, CI
    assert "fase\\_3" in tex and "answer\\_correctness" in tex  # escaped
    assert "Friedman" in tex and "comparações múltiplas" in tex
    assert "Outras Bases" in tex
