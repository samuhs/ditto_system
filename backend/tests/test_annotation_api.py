"""Tests for the Anotação humana: Avaliadores, Rodadas de anotação and their notes."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_session_factory
from app.core.db.base import Base
from app.core.db.models import Experiment, ExperimentRun, RunResult
from app.main import create_app


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    return TestClient(app), session_factory


def _experiment(session_factory, n_ok=6, n_error=2) -> int:
    """An Experimento with two Combinações; each answers `n_ok` questions and fails `n_error`."""
    session = session_factory()
    experiment = Experiment(name="fase-3", status="done", config={"base": "guia"})
    for k, rag in enumerate(("naive", "agentic")):
        run = ExperimentRun(chunking="markdown", embedding="e5", rag_technique=rag,
                            retriever="similarity", llm="qwen3.5", status="done")
        for i in range(n_ok):
            run.results.append(RunResult(
                question=f"Pergunta {i}?", reference_answer=f"Referência {i}.",
                reference_contexts=[f"Evidência {i}."], question_type="simples",
                generated_answer=f"Resposta {k}-{i}.",
                retrieved_context=[f"Trecho recuperado {i}."],
                scores={"answer_correctness": 0.5 + i / 100, "faithfulness": 0.7},
            ))
        for i in range(n_error):
            run.results.append(RunResult(question=f"Falha {i}?", generated_answer="[ERRO: timeout]",
                                         scores={}))
        experiment.runs.append(run)
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    return experiment_id


def _annotator(client, name="Ana") -> int:
    response = client.post("/annotators", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _round(client, experiment_id, size=4, seed=7) -> dict:
    response = client.post("/annotation/rounds", json={
        "name": "piloto", "experiment_id": experiment_id, "sample_size": size, "seed": seed,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_a_new_avaliador_registers_and_appears_in_the_active_list(env):
    client, _ = env
    annotator_id = _annotator(client, "Ana")

    listed = client.get("/annotators").json()

    assert [(a["id"], a["name"], a["active"]) for a in listed] == [(annotator_id, "Ana", True)]


def test_a_duplicate_name_is_refused(env):
    client, _ = env
    _annotator(client, "Ana")

    response = client.post("/annotators", json={"name": "  Ana "})

    assert response.status_code == 409


def test_a_blank_name_is_refused(env):
    client, _ = env

    assert client.post("/annotators", json={"name": "   "}).status_code == 422


def test_deactivating_hides_the_avaliador_from_the_active_list_but_keeps_the_notes(env):
    client, sf = env
    annotator_id = _annotator(client)
    rnd = _round(client, _experiment(sf))
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": annotator_id}).json()["items"][0]["id"]
    client.put(f"/annotation/items/{item_id}/notes/{annotator_id}",
               json={"correctness": 2, "grounding": 1})

    response = client.patch(f"/annotators/{annotator_id}", json={"active": False})

    assert response.status_code == 200
    assert client.get("/annotators", params={"active": True}).json() == []
    assert [a["active"] for a in client.get("/annotators", params={"active": False}).json()] == [False]
    progress = client.get(f"/annotation/rounds/{rnd['id']}").json()["progress"]
    assert progress == [{"annotator_id": annotator_id, "name": "Ana", "done": 1, "total": 4}]


def test_a_round_samples_the_requested_number_of_answers_without_errors(env):
    client, sf = env

    rnd = _round(client, _experiment(sf), size=5)

    assert rnd["size"] == 5
    assert rnd["seed"] == 7
    assert rnd["status"] == "open"
    queue = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                       params={"annotator_id": _annotator(client)}).json()["items"]
    assert len(queue) == 5
    assert all(not item["generated_answer"].startswith("[ERRO") for item in queue)


def test_the_same_seed_samples_the_same_answers(env):
    client, sf = env
    experiment_id = _experiment(sf, n_ok=20)
    annotator_id = _annotator(client)

    def answers(seed):
        rnd = _round(client, experiment_id, size=6, seed=seed)
        queue = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                           params={"annotator_id": annotator_id}).json()["items"]
        return sorted(item["generated_answer"] for item in queue)

    assert answers(3) == answers(3)
    assert answers(3) != answers(4)


def test_asking_for_more_answers_than_exist_is_refused(env):
    client, sf = env

    response = client.post("/annotation/rounds", json={
        "name": "grande", "experiment_id": _experiment(sf, n_ok=2), "sample_size": 10,
    })

    assert response.status_code == 422
    assert "4" in response.json()["detail"]  # how many valid answers there are


def test_a_round_from_a_missing_experiment_is_404(env):
    client, _ = env

    response = client.post("/annotation/rounds", json={
        "name": "x", "experiment_id": 999, "sample_size": 1,
    })

    assert response.status_code == 404


def test_items_are_copies_that_survive_deleting_the_experiment(env):
    client, sf = env
    experiment_id = _experiment(sf)
    rnd = _round(client, experiment_id, size=3)
    session = sf()
    session.delete(session.get(Experiment, experiment_id))
    session.commit()
    session.close()

    queue = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                       params={"annotator_id": _annotator(client)}).json()["items"]

    assert len(queue) == 3
    first = queue[0]
    assert first["question"].startswith("Pergunta")
    assert first["reference_answer"].startswith("Referência")
    assert first["evidence"][0].startswith("Evidência")
    assert first["retrieved_context"][0].startswith("Trecho recuperado")


def test_the_queue_hides_technique_llm_experiment_and_scores(env):
    client, sf = env
    rnd = _round(client, _experiment(sf))

    item = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                      params={"annotator_id": _annotator(client)}).json()["items"][0]

    hidden = {"rag", "rag_technique", "llm", "experiment_id", "experiment_name", "chunking",
              "embedding", "retriever", "scores", "auto_scores", "combination", "source_result_id"}
    assert hidden.isdisjoint(item)
    assert "naive" not in str(item) and "agentic" not in str(item) and "qwen" not in str(item)


def test_a_note_is_saved_and_shown_only_to_its_avaliador(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]

    saved = client.put(f"/annotation/items/{item_id}/notes/{ana}",
                       json={"correctness": 2, "grounding": 1})

    assert saved.status_code == 200
    ana_queue = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()
    bruno_queue = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": bruno}).json()
    mine = next(i for i in ana_queue["items"] if i["id"] == item_id)
    theirs = next(i for i in bruno_queue["items"] if i["id"] == item_id)
    assert mine["note"] == {"correctness": 2, "grounding": 1}
    assert theirs["note"] is None
    assert (ana_queue["done"], ana_queue["total"]) == (1, 2)
    assert (bruno_queue["done"], bruno_queue["total"]) == (0, 2)


def test_saving_again_replaces_the_note(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]

    client.put(f"/annotation/items/{item_id}/notes/{ana}", json={"correctness": 0, "grounding": 0})
    client.put(f"/annotation/items/{item_id}/notes/{ana}", json={"correctness": 2, "grounding": 2})

    queue = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()
    assert queue["items"][0]["note"] == {"correctness": 2, "grounding": 2}
    assert queue["done"] == 1


@pytest.mark.parametrize("note", [
    {"correctness": 3, "grounding": 1}, {"correctness": -1, "grounding": 1},
    {"correctness": 1, "grounding": 5}, {"grounding": 1},
])
def test_notes_outside_the_rubrica_are_refused(env, note):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]

    assert client.put(f"/annotation/items/{item_id}/notes/{ana}", json=note).status_code == 422


def test_notes_for_unknown_items_or_avaliadores_are_404(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]
    note = {"correctness": 1, "grounding": 1}

    assert client.put(f"/annotation/items/999/notes/{ana}", json=note).status_code == 404
    assert client.put(f"/annotation/items/{item_id}/notes/999", json=note).status_code == 404


def test_the_rubrica_is_served_with_its_version_and_levels(env):
    client, _ = env

    rubric = client.get("/annotation/rubric").json()

    assert rubric["version"] == 1
    dims = {d["key"]: d for d in rubric["dimensions"]}
    assert set(dims) == {"correctness", "grounding"}
    assert [lvl["value"] for lvl in dims["correctness"]["levels"]] == [0, 1, 2]


def test_rounds_are_listed_newest_first_with_size_and_status(env):
    client, sf = env
    experiment_id = _experiment(sf)
    first = _round(client, experiment_id, size=2)
    second = _round(client, experiment_id, size=3)

    listed = client.get("/annotation/rounds").json()

    assert [(r["id"], r["size"], r["status"]) for r in listed] == [
        (second["id"], 3, "open"), (first["id"], 2, "open"),
    ]


def test_the_round_detail_shows_progress_per_avaliador_who_noted_something(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=3)
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")
    items = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()["items"]
    for item in items[:2]:
        client.put(f"/annotation/items/{item['id']}/notes/{ana}", json={"correctness": 1, "grounding": 1})
    client.put(f"/annotation/items/{items[0]['id']}/notes/{bruno}", json={"correctness": 2, "grounding": 2})

    detail = client.get(f"/annotation/rounds/{rnd['id']}").json()

    assert detail["experiment_ids"] == [rnd["experiment_ids"][0]]
    assert sorted((p["name"], p["done"], p["total"]) for p in detail["progress"]) == [
        ("Ana", 2, 3), ("Bruno", 1, 3),
    ]


def test_an_unknown_round_is_404(env):
    client, _ = env

    assert client.get("/annotation/rounds/42").status_code == 404
    assert client.get("/annotation/rounds/42/queue", params={"annotator_id": 1}).status_code == 404


def test_a_name_longer_than_the_column_is_refused(env):
    client, _ = env

    assert client.post("/annotators", json={"name": "A" * 121}).status_code == 422


def test_a_deactivated_name_is_refused_with_a_hint_to_reactivate(env):
    client, _ = env
    annotator_id = _annotator(client, "Ana")
    client.patch(f"/annotators/{annotator_id}", json={"active": False})

    response = client.post("/annotators", json={"name": "ana"})

    assert response.status_code == 409
    assert "reativ" in response.json()["detail"]


@pytest.mark.parametrize("body", [
    {"name": "   ", "experiment_id": 1, "sample_size": 1},
    {"name": "x", "experiment_id": 1, "sample_size": 1, "seed": 2**31},
    {"name": "x", "experiment_id": 1, "sample_size": 1, "seed": -1},
    {"name": "x" * 121, "experiment_id": 1, "sample_size": 1},
])
def test_invalid_rounds_are_refused(env, body):
    client, sf = env
    body = {**body, "experiment_id": _experiment(sf)}

    assert client.post("/annotation/rounds", json=body).status_code == 422
