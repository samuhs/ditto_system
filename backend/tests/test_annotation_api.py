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
    assert mine["note"] == {"correctness": 2, "grounding": 1, "cannot_evaluate": False, "reason": None,
                            "comment": None}
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
    assert {k: queue["items"][0]["note"][k] for k in ("correctness", "grounding")} == {"correctness": 2, "grounding": 2}
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


# ---- #48: stratified sampling across Experimentos, pilot Rodadas ----

def _campaign(session_factory, name, base, runs) -> tuple[int, list[int]]:
    """An Experimento whose runs are (rag, llm, {question_type: how many answers})."""
    session = session_factory()
    experiment = Experiment(name=name, status="done", config={"base": base})
    for rag, llm, per_type in runs:
        run = ExperimentRun(chunking="markdown", embedding="e5", rag_technique=rag,
                            retriever="similarity", llm=llm, status="done")
        for qtype, n in per_type.items():
            for i in range(n):
                run.results.append(RunResult(
                    question=f"{qtype} {i}?", reference_answer="Ref.", question_type=qtype,
                    generated_answer=f"Resposta {qtype} {i}.", scores={"answer_correctness": 0.6},
                ))
        experiment.runs.append(run)
    session.add(experiment)
    session.commit()
    ids = experiment.id, [r.id for r in experiment.runs]
    session.close()
    return ids


def _strata_body(items, size, **over):
    return {"name": "estratificada", "items": items, "sample_size": size, "seed": 1, **over}


def _sampled(client, sf, round_id) -> list[tuple]:
    """(rag, llm, question_type) of each Item of a Rodada, read from the database."""
    from app.core.db.models import AnnotationItem
    session = sf()
    rows = session.query(AnnotationItem).filter_by(round_id=round_id).all()
    out = [(i.combination["rag"], i.combination["llm"], i.question_type) for i in rows]
    session.close()
    return out


def test_a_round_can_mix_combinations_of_two_experimentos_of_the_same_base(env):
    client, sf = env
    e1, [r1] = _campaign(sf, "fase-2", "b2", [("naive", "L0", {"simples": 5})])
    e2, [r2] = _campaign(sf, "fase-3", "b2", [("agentic", "M1", {"simples": 5})])

    response = client.post("/annotation/rounds", json=_strata_body([f"{e1}:{r1}", f"{e2}:{r2}"], 10))

    assert response.status_code == 201, response.text
    assert response.json()["experiment_ids"] == [e1, e2]
    assert sorted({rag for rag, _, _ in _sampled(client, sf, response.json()["id"])}) == ["agentic", "naive"]


def test_combinations_of_different_bases_are_refused(env):
    client, sf = env
    e1, [r1] = _campaign(sf, "guia", "guia", [("naive", "L0", {"simples": 5})])
    e2, [r2] = _campaign(sf, "b2", "b2", [("naive", "L0", {"simples": 5})])

    response = client.post("/annotation/rounds", json=_strata_body([f"{e1}:{r1}", f"{e2}:{r2}"], 4))

    assert response.status_code == 422
    assert "Base" in response.json()["detail"]


def test_a_combination_that_does_not_exist_is_404(env):
    client, sf = env
    e1, [r1] = _campaign(sf, "fase-2", "b2", [("naive", "L0", {"simples": 5})])

    response = client.post("/annotation/rounds", json=_strata_body([f"{e1}:{r1}", f"{e1}:999"], 2))

    assert response.status_code == 404


def test_equal_allocation_gives_each_stratum_the_same_share(env):
    client, sf = env
    e, runs = _campaign(sf, "fase-3", "b2", [
        ("naive", "L0", {"simples": 10, "ponte": 10}),
        ("agentic", "L0", {"simples": 10, "ponte": 10}),
    ])
    items = [f"{e}:{r}" for r in runs]

    response = client.post("/annotation/rounds", json=_strata_body(
        items, 8, strata=["rag", "question_type"], allocation="equal"))

    counts = {}
    for rag, _, qtype in _sampled(client, sf, response.json()["id"]):
        counts[(rag, qtype)] = counts.get((rag, qtype), 0) + 1
    assert counts == {("naive", "simples"): 2, ("naive", "ponte"): 2,
                      ("agentic", "simples"): 2, ("agentic", "ponte"): 2}


def test_proportional_allocation_follows_the_stratum_sizes(env):
    client, sf = env
    e, [r] = _campaign(sf, "fase-2", "b2", [("naive", "L0", {"simples": 30, "ponte": 10})])

    response = client.post("/annotation/rounds", json=_strata_body(
        [f"{e}:{r}"], 8, strata=["question_type"], allocation="proportional"))

    types = [t for _, _, t in _sampled(client, sf, response.json()["id"])]
    assert (types.count("simples"), types.count("ponte")) == (6, 2)


def test_a_short_stratum_gives_its_shortfall_to_the_others(env):
    client, sf = env
    e, [r] = _campaign(sf, "fase-2", "b2", [("naive", "L0", {"simples": 20, "ponte": 1})])

    response = client.post("/annotation/rounds", json=_strata_body(
        [f"{e}:{r}"], 6, strata=["question_type"], allocation="equal"))

    types = [t for _, _, t in _sampled(client, sf, response.json()["id"])]
    assert (types.count("simples"), types.count("ponte")) == (5, 1)


def test_stratified_sampling_is_reproducible_with_the_seed(env):
    client, sf = env
    e, runs = _campaign(sf, "fase-3", "b2", [
        ("naive", "L0", {"simples": 15, "ponte": 15}), ("agentic", "M1", {"simples": 15, "ponte": 15}),
    ])
    body = _strata_body([f"{e}:{r}" for r in runs], 12, strata=["rag", "question_type"])

    def answers():
        rid = client.post("/annotation/rounds", json=body).json()["id"]
        q = client.get(f"/annotation/rounds/{rid}/queue", params={"annotator_id": annotator}).json()
        return sorted(i["generated_answer"] for i in q["items"])

    annotator = _annotator(client)
    assert answers() == answers()


def test_the_preview_counts_each_stratum_and_warns_about_short_ones(env):
    client, sf = env
    e, [r] = _campaign(sf, "fase-2", "b2", [("naive", "L0", {"simples": 20, "ponte": 1})])

    preview = client.post("/annotation/rounds/preview", json=_strata_body(
        [f"{e}:{r}"], 6, strata=["question_type"], allocation="equal")).json()

    by_key = {tuple(s["key"].values()): s for s in preview["strata"]}
    assert by_key[("ponte",)] == {"key": {"question_type": "ponte"}, "available": 1, "allocated": 1, "short": True}
    assert by_key[("simples",)]["available"] == 20
    assert by_key[("simples",)]["allocated"] == 5
    assert preview["available"] == 21
    assert preview["size"] == 6


def test_unknown_strata_dimensions_are_refused(env):
    client, sf = env
    e, [r] = _campaign(sf, "fase-2", "b2", [("naive", "L0", {"simples": 5})])

    response = client.post("/annotation/rounds", json=_strata_body([f"{e}:{r}"], 2, strata=["cor"]))

    assert response.status_code == 422


def test_a_pilot_round_is_marked_as_such(env):
    client, sf = env
    e, [r] = _campaign(sf, "fase-2", "b2", [("naive", "L0", {"simples": 5})])

    created = client.post("/annotation/rounds", json=_strata_body([f"{e}:{r}"], 2, pilot=True)).json()

    assert created["pilot"] is True
    assert client.get("/annotation/rounds").json()[0]["pilot"] is True
    assert created["strata"] == [] and created["allocation"] == "proportional"


def test_stratified_items_are_shuffled_not_grouped_by_stratum(env):
    client, sf = env
    e, runs = _campaign(sf, "fase-3", "b2", [("naive", "L0", {"simples": 20}), ("agentic", "L0", {"simples": 20})])

    rid = client.post("/annotation/rounds", json=_strata_body(
        [f"{e}:{r}" for r in runs], 20, strata=["rag"], allocation="equal")).json()["id"]

    from app.core.db.models import AnnotationItem
    session = sf()
    order = [i.combination["rag"] for i in session.query(AnnotationItem).filter_by(round_id=rid)
             .order_by(AnnotationItem.position)]
    session.close()
    assert order.count("naive") == order.count("agentic") == 10
    assert set(order[:10]) == {"naive", "agentic"}


def test_a_round_from_an_experimento_still_running_is_refused(env):
    client, sf = env
    e, [r] = _campaign(sf, "fase-3", "b2", [("naive", "L0", {"simples": 5})])
    session = sf()
    session.get(Experiment, e).status = "running"
    session.commit()
    session.close()

    response = client.post("/annotation/rounds", json=_strata_body([f"{e}:{r}"], 2))

    assert response.status_code == 422
    assert "concluído" in response.json()["detail"]


# ---- #49: joining Rodadas, per-Avaliador order, removing a participant ----

def _join(client, round_id, annotator_id):
    return client.post(f"/annotation/rounds/{round_id}/participants", json={"annotator_id": annotator_id})


def test_joining_a_round_lists_the_avaliador_in_the_progress_even_with_nothing_done(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=3)
    ana = _annotator(client, "Ana")

    assert _join(client, rnd["id"], ana).status_code == 200
    assert _join(client, rnd["id"], ana).status_code == 200  # joining twice is harmless

    progress = client.get(f"/annotation/rounds/{rnd['id']}").json()["progress"]
    assert progress == [{"annotator_id": ana, "name": "Ana", "done": 0, "total": 3}]


def test_an_inactive_avaliador_cannot_join(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=3)
    ana = _annotator(client, "Ana")
    client.patch(f"/annotators/{ana}", json={"active": False})

    assert _join(client, rnd["id"], ana).status_code == 409


def test_each_avaliador_sees_their_own_stable_order(env):
    client, sf = env
    rnd = _round(client, _experiment(sf, n_ok=20), size=20)
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")

    def order(annotator_id):
        q = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": annotator_id}).json()
        return [i["id"] for i in q["items"]]

    assert order(ana) == order(ana)
    assert order(ana) != order(bruno)
    assert sorted(order(ana)) == sorted(order(bruno))


def test_removing_a_participant_deletes_their_notes_in_that_round_only(env):
    client, sf = env
    experiment_id = _experiment(sf)
    rnd, other = _round(client, experiment_id, size=2), _round(client, experiment_id, size=2)
    ana = _annotator(client, "Ana")
    for r in (rnd, other):
        _join(client, r["id"], ana)
        item = client.get(f"/annotation/rounds/{r['id']}/queue", params={"annotator_id": ana}).json()["items"][0]
        client.put(f"/annotation/items/{item['id']}/notes/{ana}", json={"correctness": 1, "grounding": 1})

    response = client.delete(f"/annotation/rounds/{rnd['id']}/participants/{ana}")

    assert response.status_code == 200
    assert response.json() == {"round_id": rnd["id"], "annotator_id": ana, "notes_deleted": 1}
    assert client.get(f"/annotation/rounds/{rnd['id']}").json()["progress"] == []
    assert client.get(f"/annotation/rounds/{other['id']}").json()["progress"][0]["done"] == 1


def test_removing_someone_who_is_not_a_participant_is_404(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana = _annotator(client, "Ana")

    assert client.delete(f"/annotation/rounds/{rnd['id']}/participants/{ana}").status_code == 404


def test_a_removed_avaliador_cannot_save_until_they_pick_the_round_again(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana = _annotator(client, "Ana")
    _join(client, rnd["id"], ana)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()["items"][0]["id"]
    client.put(f"/annotation/items/{item_id}/notes/{ana}", json={"correctness": 1, "grounding": 1})
    client.delete(f"/annotation/rounds/{rnd['id']}/participants/{ana}")

    stale = client.put(f"/annotation/items/{item_id}/notes/{ana}", json={"correctness": 2, "grounding": 2})

    assert stale.status_code == 409
    assert client.get(f"/annotation/rounds/{rnd['id']}").json()["progress"] == []
    _join(client, rnd["id"], ana)
    assert client.put(f"/annotation/items/{item_id}/notes/{ana}",
                      json={"correctness": 2, "grounding": 2}).status_code == 200
    assert client.get(f"/annotation/rounds/{rnd['id']}").json()["progress"][0]["done"] == 1


def test_scoring_without_joining_first_joins_the_round(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana = _annotator(client, "Ana")
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()["items"][0]["id"]

    client.put(f"/annotation/items/{item_id}/notes/{ana}", json={"correctness": 1, "grounding": 1})

    assert client.delete(f"/annotation/rounds/{rnd['id']}/participants/{ana}").json()["notes_deleted"] == 1


# ---- #50: "não se aplica", "não consigo avaliar", comment ----

def _closed_book_round(client, sf):
    """A Rodada whose only answer has no retrieved context (closed_book)."""
    session = sf()
    experiment = Experiment(name="cb", status="done", config={"base": "guia"})
    run = ExperimentRun(chunking="markdown", embedding="e5", rag_technique="closed_book",
                        retriever="similarity", llm="L0", status="done")
    run.results.append(RunResult(question="Sem contexto?", reference_answer="Ref.", generated_answer="Não sei.",
                                 retrieved_context=[], scores={"answer_correctness": 0.4}))
    experiment.runs.append(run)
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    return _round(client, experiment_id, size=1)


def _first_item(client, round_id, annotator_id):
    return client.get(f"/annotation/rounds/{round_id}/queue", params={"annotator_id": annotator_id}).json()["items"][0]


def test_the_queue_says_whether_grounding_applies(env):
    client, sf = env
    ana = _annotator(client)

    with_context = _first_item(client, _round(client, _experiment(sf), size=1)["id"], ana)
    without = _first_item(client, _closed_book_round(client, sf)["id"], ana)

    assert with_context["grounding_applicable"] is True
    assert without["grounding_applicable"] is False


def test_without_retrieved_context_grounding_must_be_left_out(env):
    client, sf = env
    rnd = _closed_book_round(client, sf)
    ana = _annotator(client)
    item = _first_item(client, rnd["id"], ana)
    url = f"/annotation/items/{item['id']}/notes/{ana}"

    assert client.put(url, json={"correctness": 1, "grounding": 2}).status_code == 422
    assert client.put(url, json={"correctness": 1}).status_code == 200
    queue = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()
    assert queue["items"][0]["note"]["grounding"] is None
    assert queue["done"] == 1


def test_with_retrieved_context_grounding_is_required(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client)
    item = _first_item(client, rnd["id"], ana)

    assert client.put(f"/annotation/items/{item['id']}/notes/{ana}", json={"correctness": 1}).status_code == 422


def test_cannot_evaluate_needs_a_reason_and_no_scores(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client)
    url = f"/annotation/items/{_first_item(client, rnd['id'], ana)['id']}/notes/{ana}"

    assert client.put(url, json={"cannot_evaluate": True}).status_code == 422
    assert client.put(url, json={"cannot_evaluate": True, "reason": "  "}).status_code == 422
    assert client.put(url, json={"cannot_evaluate": True, "reason": "ambígua", "correctness": 1,
                                 "grounding": 1}).status_code == 422
    assert client.put(url, json={"cannot_evaluate": True, "reason": "Referência ambígua"}).status_code == 200

    queue = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()
    note = queue["items"][0]["note"]
    assert (note["cannot_evaluate"], note["reason"], note["correctness"]) == (True, "Referência ambígua", None)
    assert queue["done"] == 1  # counted as handled


def test_a_comment_is_kept_with_the_note(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client)
    url = f"/annotation/items/{_first_item(client, rnd['id'], ana)['id']}/notes/{ana}"

    client.put(url, json={"correctness": 2, "grounding": 2, "comment": "Resposta longa, mas certa."})

    assert _first_item(client, rnd["id"], ana)["note"]["comment"] == "Resposta longa, mas certa."


# ---- #51: closing a Rodada and measuring the Concordância ----

def _score_all(client, round_id, annotator_id, scores):
    """Join and score the Items in position order: scores[i] = (correctness, grounding) or None to skip."""
    _join(client, round_id, annotator_id)
    from app.core.db.models import AnnotationItem  # noqa: F401
    items = sorted(client.get(f"/annotation/rounds/{round_id}/queue",
                              params={"annotator_id": annotator_id}).json()["items"],
                   key=lambda i: i["position"])
    for item, score in zip(items, scores):
        if score is None:
            continue
        if score == "cannot":
            body = {"cannot_evaluate": True, "reason": "ambígua"}
        else:
            body = {"correctness": score[0], "grounding": score[1]}
        assert client.put(f"/annotation/items/{item['id']}/notes/{annotator_id}", json=body).status_code == 200
    return items


def test_closing_a_round_refuses_new_notes(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana = _annotator(client)
    items = _score_all(client, rnd["id"], ana, [(1, 1)])

    assert client.post(f"/annotation/rounds/{rnd['id']}/close").json()["status"] == "closed"
    late = client.put(f"/annotation/items/{items[1]['id']}/notes/{ana}", json={"correctness": 1, "grounding": 1})
    assert late.status_code == 409


def test_agreement_of_two_avaliadores_has_kappa_alpha_confusion_and_disagreements(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=4)
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")
    _score_all(client, rnd["id"], ana, [(0, 2), (1, 2), (2, 2), (2, 2)])
    _score_all(client, rnd["id"], bruno, [(0, 2), (2, 2), (2, 2), (1, 2)])

    result = client.get(f"/annotation/rounds/{rnd['id']}/agreement", params={"resamples": 200}).json()

    corr = result["dimensions"]["correctness"]
    assert corr["n"] == 4
    assert corr["kappa"]["value"] == pytest.approx(7 / 11)
    assert corr["alpha"]["value"] is not None
    assert corr["alpha"]["low"] <= corr["alpha"]["value"] <= corr["alpha"]["high"]
    assert corr["confusion"] == {"avaliadores": ["Ana", "Bruno"], "levels": [0, 1, 2],
                                 "matrix": [[1, 0, 0], [0, 0, 1], [0, 1, 1]]}
    assert result["dimensions"]["grounding"]["kappa"] is None  # no variation: undefined
    disagreements = result["disagreements"]
    assert len(disagreements) == 2
    assert {d["notes"]["Ana"]["correctness"] for d in disagreements} == {1, 2}
    assert result["avaliadores"] == ["Ana", "Bruno"]


def test_items_without_a_score_are_left_out_of_that_dimension(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=3)
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")
    _score_all(client, rnd["id"], ana, [(0, 1), (1, 1), "cannot"])
    _score_all(client, rnd["id"], bruno, [(0, 1), (2, 2), (2, 2)])

    dims = client.get(f"/annotation/rounds/{rnd['id']}/agreement", params={"resamples": 100}).json()["dimensions"]

    assert dims["correctness"]["n"] == 2
    assert dims["grounding"]["n"] == 2


def test_kappa_only_with_exactly_two_avaliadores(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=3)
    for name, scores in (("Ana", [(0, 0), (1, 1), (2, 2)]), ("Bruno", [(0, 0), (1, 1), (2, 1)]),
                         ("Caio", [(0, 0), (2, 1), (2, 2)])):
        _score_all(client, rnd["id"], _annotator(client, name), scores)

    corr = client.get(f"/annotation/rounds/{rnd['id']}/agreement",
                      params={"resamples": 100}).json()["dimensions"]["correctness"]

    assert corr["kappa"] is None
    assert corr["confusion"] is None
    assert corr["alpha"]["value"] is not None


def test_agreement_with_a_single_avaliador_says_why_it_is_missing(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    _score_all(client, rnd["id"], _annotator(client), [(1, 1), (2, 2)])

    result = client.get(f"/annotation/rounds/{rnd['id']}/agreement", params={"resamples": 100}).json()

    assert result["dimensions"]["correctness"]["alpha"]["value"] is None
    assert "dois avaliadores" in result["note"]


def test_a_closed_round_keeps_its_notes_even_when_removing_a_participant(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana = _annotator(client)
    _score_all(client, rnd["id"], ana, [(1, 1)])
    client.post(f"/annotation/rounds/{rnd['id']}/close")

    assert client.delete(f"/annotation/rounds/{rnd['id']}/participants/{ana}").status_code == 409
    assert client.get(f"/annotation/rounds/{rnd['id']}").json()["progress"][0]["done"] == 1


# ---- #52: Adjudicação and Nota final ----

def _disputed_round(client, sf):
    """A closed Rodada of 3 Items: Ana and Bruno agree on the first, disagree on Correção of the
    second and on both dimensions of the third. Returns (round, items in position order, ids)."""
    rnd = _round(client, _experiment(sf), size=3)
    ana, bruno, ori = _annotator(client, "Ana"), _annotator(client, "Bruno"), _annotator(client, "Orientador")
    items = _score_all(client, rnd["id"], ana, [(2, 2), (1, 2), (0, 0)])
    _score_all(client, rnd["id"], bruno, [(2, 2), (2, 2), (2, 1)])
    client.post(f"/annotation/rounds/{rnd['id']}/close")
    return rnd, items, (ana, bruno, ori)


def _set_adjudicator(client, round_id, annotator_id):
    return client.patch(f"/annotation/rounds/{round_id}", json={"adjudicator_id": annotator_id})


def test_the_researcher_designates_an_adjudicator(env):
    client, sf = env
    rnd, _, (_, _, ori) = _disputed_round(client, sf)

    response = _set_adjudicator(client, rnd["id"], ori)

    assert response.status_code == 200
    assert client.get(f"/annotation/rounds/{rnd['id']}").json()["adjudicator_id"] == ori


def test_someone_who_scored_the_round_cannot_adjudicate_it(env):
    client, sf = env
    rnd, _, (ana, _, _) = _disputed_round(client, sf)

    assert _set_adjudicator(client, rnd["id"], ana).status_code == 409


def test_the_adjudicator_sees_only_the_disagreements_with_the_others_notes(env):
    client, sf = env
    rnd, items, (_, _, ori) = _disputed_round(client, sf)
    _set_adjudicator(client, rnd["id"], ori)

    view = client.get(f"/annotation/rounds/{rnd['id']}/adjudication", params={"annotator_id": ori}).json()

    assert sorted(i["id"] for i in view["items"]) == sorted([items[1]["id"], items[2]["id"]])
    disputed = next(i for i in view["items"] if i["id"] == items[1]["id"])
    assert disputed["notes"]["Ana"]["correctness"] == 1 and disputed["notes"]["Bruno"]["correctness"] == 2
    assert disputed["disputed"] == ["correctness"]
    assert disputed["adjudication"] is None


def test_only_the_adjudicator_can_see_or_decide(env):
    client, sf = env
    rnd, items, (ana, _, ori) = _disputed_round(client, sf)
    _set_adjudicator(client, rnd["id"], ori)

    assert client.get(f"/annotation/rounds/{rnd['id']}/adjudication", params={"annotator_id": ana}).status_code == 403
    response = client.put(f"/annotation/items/{items[1]['id']}/adjudication",
                          json={"annotator_id": ana, "correctness": 2})
    assert response.status_code == 403


def test_adjudication_needs_a_closed_round(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ori = _annotator(client, "Orientador")

    assert _set_adjudicator(client, rnd["id"], ori).status_code == 200
    assert client.get(f"/annotation/rounds/{rnd['id']}/adjudication", params={"annotator_id": ori}).status_code == 409


def test_the_final_note_follows_agreement_then_adjudication_and_counts_what_is_pending(env):
    client, sf = env
    rnd, items, (_, _, ori) = _disputed_round(client, sf)
    _set_adjudicator(client, rnd["id"], ori)

    before = client.get(f"/annotation/rounds/{rnd['id']}/final").json()
    assert before["pending"] == 2

    decided = client.put(f"/annotation/items/{items[1]['id']}/adjudication",
                         json={"annotator_id": ori, "correctness": 1})
    assert decided.status_code == 200
    final = client.get(f"/annotation/rounds/{rnd['id']}/final").json()

    by_id = {i["id"]: i for i in final["items"]}
    assert by_id[items[0]["id"]]["final"] == {"correctness": 2, "grounding": 2}
    assert by_id[items[0]["id"]]["status"] == "concordância"
    assert by_id[items[1]["id"]]["final"] == {"correctness": 1, "grounding": 2}
    assert by_id[items[1]["id"]]["status"] == "adjudicada"
    assert by_id[items[2]["id"]]["final"] == {"correctness": None, "grounding": None}
    assert by_id[items[2]["id"]]["status"] == "pendente"
    assert final["pending"] == 1


def test_the_adjudication_must_cover_every_disputed_dimension(env):
    client, sf = env
    rnd, items, (_, _, ori) = _disputed_round(client, sf)
    _set_adjudicator(client, rnd["id"], ori)

    partial = client.put(f"/annotation/items/{items[2]['id']}/adjudication",
                         json={"annotator_id": ori, "correctness": 1})

    assert partial.status_code == 422


def test_an_item_without_disagreement_cannot_be_adjudicated(env):
    client, sf = env
    rnd, items, (_, _, ori) = _disputed_round(client, sf)
    _set_adjudicator(client, rnd["id"], ori)

    response = client.put(f"/annotation/items/{items[0]['id']}/adjudication",
                          json={"annotator_id": ori, "correctness": 2, "grounding": 2})

    assert response.status_code == 409


def test_an_adjudicator_who_scored_after_being_designated_cannot_adjudicate(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana, ori = _annotator(client, "Ana"), _annotator(client, "Orientador")
    _set_adjudicator(client, rnd["id"], ori)
    _score_all(client, rnd["id"], ana, [(0, 0), (1, 1)])
    _score_all(client, rnd["id"], ori, [(2, 2), (1, 1)])
    client.post(f"/annotation/rounds/{rnd['id']}/close")

    assert client.get(f"/annotation/rounds/{rnd['id']}/adjudication", params={"annotator_id": ori}).status_code == 409


def test_a_note_against_cannot_evaluate_is_not_concordance(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    _score_all(client, rnd["id"], _annotator(client, "Ana"), [(2, 2)])
    _score_all(client, rnd["id"], _annotator(client, "Bruno"), ["cannot"])

    final = client.get(f"/annotation/rounds/{rnd['id']}/final").json()

    assert final["items"][0]["status"] == "uma nota"


# ---- #53: human scores against the automatic metrics ----

def _validation_round(client, sf, pilot=False):
    """A closed Rodada of 6 Items scored the same by Ana and Bruno, with answer_correctness
    rising with the human Correção (so Spearman is high)."""
    session = sf()
    experiment = Experiment(name="val", status="done", config={"base": "b2"})
    for k, (rag, llm) in enumerate((("naive", "L0"), ("agentic", "M3"))):
        run = ExperimentRun(chunking="markdown", embedding="e5", rag_technique=rag, retriever="similarity",
                            llm=llm, status="done")
        for i in range(3):
            run.results.append(RunResult(
                question=f"Q{k}{i}?", reference_answer="Ref.", question_type=("simples", "ponte", "simples")[i],
                generated_answer=f"R{k}{i}.", retrieved_context=["trecho"],
                scores={"answer_correctness": 0.4 + 0.1 * i + 0.01 * k, "token_f1": 0.2 + 0.1 * i,
                        "chrf": 0.3, "rouge_l": 0.1 * i, "faithfulness": 0.5 + 0.1 * i},
            ))
        experiment.runs.append(run)
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    rnd = client.post("/annotation/rounds", json={"name": "val", "experiment_id": experiment_id, "sample_size": 6,
                                                  "seed": 1, "pilot": pilot}).json()
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")
    for a in (ana, bruno):
        _join(client, rnd["id"], a)
        for item in client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": a}).json()["items"]:
            i = int(item["question"][2])
            client.put(f"/annotation/items/{item['id']}/notes/{a}", json={"correctness": i, "grounding": i})
    client.post(f"/annotation/rounds/{rnd['id']}/close")
    return rnd


def test_spearman_between_the_human_correctness_and_each_metric(env):
    client, sf = env
    rnd = _validation_round(client, sf)

    result = client.get(f"/annotation/rounds/{rnd['id']}/validation", params={"resamples": 200}).json()

    corr = {c["metric"]: c for c in result["correlations"]["correctness"]}
    assert set(corr) == {"answer_correctness", "token_f1", "chrf", "rouge_l"}
    assert corr["answer_correctness"]["rho"] == pytest.approx(1.0, abs=0.13)  # ties within k
    assert corr["answer_correctness"]["n"] == 6
    assert corr["chrf"]["rho"] is None  # constant metric: undefined
    grounding = {c["metric"]: c for c in result["correlations"]["grounding"]}
    assert set(grounding) == {"faithfulness"}
    assert grounding["faithfulness"]["rho"] == pytest.approx(1.0)
    assert result["pending"] == 0


def test_mean_human_score_per_combination_and_question_type(env):
    client, sf = env
    rnd = _validation_round(client, sf)

    result = client.get(f"/annotation/rounds/{rnd['id']}/validation", params={"resamples": 200}).json()

    by_combo = {(c["rag"], c["llm"]): c for c in result["by_combination"]}
    naive = by_combo[("naive", "L0")]
    assert naive["n"] == 3
    assert naive["human"]["mean"] == pytest.approx(1.0)  # scores 0, 1, 2
    assert naive["automatic"]["mean"] == pytest.approx(0.5)  # 0.4, 0.5, 0.6
    by_type = {t["question_type"]: t for t in result["by_question_type"]}
    assert by_type["ponte"]["n"] == 2
    assert by_type["ponte"]["human"]["mean"] == pytest.approx(1.0)


def test_pending_items_are_left_out_and_counted(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    items = _score_all(client, rnd["id"], _annotator(client, "Ana"), [(0, 0), (1, 1)])
    _score_all(client, rnd["id"], _annotator(client, "Bruno"), [(2, 2), (1, 1)])
    client.post(f"/annotation/rounds/{rnd['id']}/close")

    result = client.get(f"/annotation/rounds/{rnd['id']}/validation", params={"resamples": 100}).json()

    assert result["pending"] == 1
    assert result["correlations"]["correctness"][0]["n"] == 1
    assert items  # silence unused


def test_a_pilot_round_is_kept_out_of_the_analysis(env):
    client, sf = env
    rnd = _validation_round(client, sf, pilot=True)

    response = client.get(f"/annotation/rounds/{rnd['id']}/validation")

    assert response.status_code == 409
    assert "piloto" in response.json()["detail"]


# ---- #54: retest Rodadas and intra-rater reliability ----

def _scored_closed_round(client, sf, scores):
    rnd = _round(client, _experiment(sf), size=len(scores))
    ana = _annotator(client, "Ana")
    _score_all(client, rnd["id"], ana, scores)
    client.post(f"/annotation/rounds/{rnd['id']}/close")
    return rnd, ana


def _retest(client, round_id, annotator_id):
    return client.post(f"/annotation/rounds/{round_id}/retest", json={"annotator_id": annotator_id})


def test_a_retest_copies_the_items_for_the_same_avaliador_in_a_new_order(env):
    client, sf = env
    rnd, ana = _scored_closed_round(client, sf, [(0, 0), (1, 1), (2, 2), (2, 1), (1, 0), (0, 2)])

    response = _retest(client, rnd["id"], ana)

    assert response.status_code == 201, response.text
    retest = response.json()
    assert retest["source_round_id"] == rnd["id"] and retest["retest_annotator_id"] == ana
    assert retest["size"] == 6 and retest["status"] == "open"
    original = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()["items"]
    _join(client, retest["id"], ana)
    second = client.get(f"/annotation/rounds/{retest['id']}/queue", params={"annotator_id": ana}).json()["items"]
    assert [i["question"] for i in second] != [i["question"] for i in original]
    assert sorted(i["question"] for i in second) == sorted(i["question"] for i in original)
    assert all(i["note"] is None for i in second)  # the first pass is not shown


def test_only_the_retested_avaliador_can_join_the_retest(env):
    client, sf = env
    rnd, ana = _scored_closed_round(client, sf, [(1, 1), (2, 2)])
    bruno = _annotator(client, "Bruno")
    retest = _retest(client, rnd["id"], ana).json()

    assert _join(client, retest["id"], bruno).status_code == 409


def test_a_retest_needs_a_closed_round_scored_by_that_avaliador(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")
    _score_all(client, rnd["id"], ana, [(1, 1), (2, 2)])

    assert _retest(client, rnd["id"], ana).status_code == 409  # still open
    client.post(f"/annotation/rounds/{rnd['id']}/close")
    assert _retest(client, rnd["id"], bruno).status_code == 409  # Bruno never scored it


def test_intra_rater_alpha_between_the_two_passes(env):
    client, sf = env
    scores = [(0, 0), (1, 1), (2, 2), (2, 1), (1, 0), (0, 2)]
    rnd, ana = _scored_closed_round(client, sf, scores)
    retest = _retest(client, rnd["id"], ana).json()
    _join(client, retest["id"], ana)
    # same scores the second time, by question: perfect intra-rater agreement
    first = {i["question"]: i["note"] for i in client.get(f"/annotation/rounds/{rnd['id']}/queue",
                                                           params={"annotator_id": ana}).json()["items"]}
    for item in client.get(f"/annotation/rounds/{retest['id']}/queue", params={"annotator_id": ana}).json()["items"]:
        note = first[item["question"]]
        client.put(f"/annotation/items/{item['id']}/notes/{ana}",
                   json={"correctness": note["correctness"], "grounding": note["grounding"]})

    result = client.get(f"/annotation/rounds/{rnd['id']}/retests", params={"resamples": 100}).json()

    assert len(result) == 1
    assert result[0]["avaliador"] == "Ana"
    assert result[0]["retest_round_id"] == retest["id"]
    assert result[0]["dimensions"]["correctness"]["n"] == 6
    assert result[0]["dimensions"]["correctness"]["alpha"]["value"] == pytest.approx(1.0)


def test_nobody_else_can_read_or_score_a_retest(env):
    client, sf = env
    rnd, ana = _scored_closed_round(client, sf, [(1, 1), (2, 2)])
    bruno = _annotator(client, "Bruno")
    retest = _retest(client, rnd["id"], ana).json()
    _join(client, retest["id"], ana)
    item_id = client.get(f"/annotation/rounds/{retest['id']}/queue", params={"annotator_id": ana}).json()["items"][0]["id"]

    assert client.get(f"/annotation/rounds/{retest['id']}/queue", params={"annotator_id": bruno}).status_code == 409
    assert client.put(f"/annotation/items/{item_id}/notes/{bruno}",
                      json={"correctness": 1, "grounding": 1}).status_code == 409


def test_retests_are_unique_per_avaliador_and_never_nested(env):
    client, sf = env
    rnd, ana = _scored_closed_round(client, sf, [(1, 1), (2, 2)])
    retest = _retest(client, rnd["id"], ana).json()

    assert _retest(client, rnd["id"], ana).status_code == 409
    client.post(f"/annotation/rounds/{retest['id']}/close")
    assert _retest(client, retest["id"], ana).status_code == 409
    assert client.get(f"/annotation/rounds/{retest['id']}/validation").status_code == 409


def test_a_retest_name_fits_the_column(env):
    client, sf = env
    long_round = client.post("/annotation/rounds", json={"name": "R" * 120, "experiment_id": _experiment(sf),
                                                          "sample_size": 1, "seed": 2}).json()
    ana = _annotator(client, "A" * 100)
    _score_all(client, long_round["id"], ana, [(1, 1)])
    client.post(f"/annotation/rounds/{long_round['id']}/close")

    retest = _retest(client, long_round["id"], ana).json()

    assert len(retest["name"]) <= 120


# ---- #55: CSV and LaTeX export ----

def test_the_csv_has_one_row_per_note_and_dimension_with_the_final_note_and_metrics(env):
    import csv
    import io
    client, sf = env
    rnd = _validation_round(client, sf)

    response = client.get(f"/annotation/rounds/{rnd['id']}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("﻿"))))
    assert len(rows) == 6 * 2 * 2  # Items x Avaliadores x dimensions
    first = rows[0]
    for column in ("rodada", "item", "pergunta", "tipo_pergunta", "rag", "llm", "avaliador", "dimensao",
                   "nota", "nao_consegue_avaliar", "nota_final", "situacao_final", "answer_correctness",
                   "faithfulness"):
        assert column in first
    assert {r["dimensao"] for r in rows} == {"correctness", "grounding"}
    assert all(r["situacao_final"] == "concordância" for r in rows)


def test_the_latex_has_the_agreement_and_correlation_tables_matching_the_page(env):
    client, sf = env
    rnd = _validation_round(client, sf)
    page = client.get(f"/annotation/rounds/{rnd['id']}/agreement", params={"resamples": 100}).json()

    tex = client.get(f"/annotation/rounds/{rnd['id']}/export.tex", params={"resamples": 100}).text

    assert "\\begin{tabular}" in tex and "\\toprule" in tex
    assert "Concordância" in tex and "Spearman" in tex
    alpha = page["dimensions"]["correctness"]["alpha"]["value"]
    assert f"{alpha:.3f}" in tex


def test_the_latex_can_use_the_decimal_comma(env):
    client, sf = env
    rnd = _validation_round(client, sf)

    tex = client.get(f"/annotation/rounds/{rnd['id']}/export.tex", params={"resamples": 100, "decimal": "comma"}).text

    assert "1,000" in tex and "1.000" not in tex


def test_a_pilot_round_exports_its_notes_but_no_analysis_tables(env):
    client, sf = env
    rnd = _validation_round(client, sf, pilot=True)

    assert client.get(f"/annotation/rounds/{rnd['id']}/export.csv").status_code == 200
    assert client.get(f"/annotation/rounds/{rnd['id']}/export.tex").status_code == 409


def test_the_excel_csv_uses_semicolons_and_quotes_formulas(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client, "Ana")
    item = _score_all(client, rnd["id"], ana, [None])[0]
    client.put(f"/annotation/items/{item['id']}/notes/{ana}",
               json={"correctness": 1, "grounding": 1, "comment": "=HYPERLINK(\"x\")"})

    excel = client.get(f"/annotation/rounds/{rnd['id']}/export.csv", params={"excel": True}).text
    plain = client.get(f"/annotation/rounds/{rnd['id']}/export.csv").text

    assert excel.splitlines()[0].count(";") > 5
    assert "'=HYPERLINK" in excel
    assert "'=HYPERLINK" not in plain and "=HYPERLINK" in plain


def test_the_latex_can_be_written_in_english_for_the_english_paper(env):
    client, sf = env
    rnd = _validation_round(client, sf)

    tex = client.get(f"/annotation/rounds/{rnd['id']}/export.tex", params={"resamples": 100, "lang": "en"}).text
    pt = client.get(f"/annotation/rounds/{rnd['id']}/export.tex", params={"resamples": 100}).text

    assert "Inter-annotator agreement" in tex and "Spearman correlation" in tex and "Correctness" in tex
    assert "Concordância" not in tex and "Correção" not in tex and "rodada" not in tex
    assert "1.000" in tex and "100 resamples" in tex  # point decimals, English separators
    assert "Concordância" in pt  # Portuguese stays the default
    names = [client.get(f"/annotation/rounds/{rnd['id']}/export.tex", params={"resamples": 100, **p}).headers[
        "content-disposition"] for p in ({}, {"decimal": "comma"}, {"lang": "en"})]
    assert len(set(names)) == 3 and "-en.tex" in names[2]


# ---- pairwise (side-by-side) comparison rounds ----

def _pair_experiment(session_factory, q1: list[str], q2: list[str], base="guia") -> tuple[int, int, int]:
    """One Experimento with two Combinações (naive, agentic); run 1 answers `q1`, run 2 `q2`."""
    session = session_factory()
    experiment = Experiment(name="pares", status="done", config={"base": base})
    for k, (rag, questions) in enumerate((("naive", q1), ("agentic", q2))):
        run = ExperimentRun(chunking="markdown", embedding="e5", rag_technique=rag,
                            retriever="similarity", llm="qwen3.5", status="done")
        for q in questions:
            run.results.append(RunResult(
                question=q, reference_answer=f"Ref {q}", generated_answer=f"Resposta {k} a {q}",
                retrieved_context=[f"Trecho {k} de {q}"], scores={"answer_correctness": 0.5},
            ))
        experiment.runs.append(run)
    session.add(experiment)
    session.commit()
    experiment_id, run_ids = experiment.id, [r.id for r in experiment.runs]
    session.close()
    return experiment_id, run_ids[0], run_ids[1]


def _pair_items_arg(experiment_id, run1, run2) -> list[str]:
    return [f"{experiment_id}:{run1}", f"{experiment_id}:{run2}"]


def _pair_round(client, items, **over) -> dict:
    body = {"name": "pares", "kind": "pairwise", "items": items, **over}
    response = client.post("/annotation/rounds", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _pair_items_by_position(sf, round_id) -> list[dict]:
    from app.core.db.models import AnnotationPairItem
    session = sf()
    items = session.query(AnnotationPairItem).filter_by(round_id=round_id) \
        .order_by(AnnotationPairItem.position).all()
    out = [{"id": i.id, "question": i.question, "a_is_1": i.a_is_1} for i in items]
    session.close()
    return out


def _pair_note(client, item_id, annotator_id, **over):
    body = {"preference": None, "reasons": [], "cannot_evaluate": False, "reason": None, "comment": None, **over}
    return client.put(f"/annotation/pair-items/{item_id}/notes/{annotator_id}", json=body)


def test_a_pairwise_round_pairs_only_the_common_questions(env):
    client, sf = env
    q1 = [f"Q{i}?" for i in range(5)]
    q2 = [f"Q{i}?" for i in range(2, 7)]
    experiment_id, r1, r2 = _pair_experiment(sf, q1, q2)

    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))

    assert rnd["kind"] == "pairwise"
    assert rnd["size"] == 3  # Q2, Q3, Q4 only
    items = _pair_items_by_position(sf, rnd["id"])
    assert sorted(i["question"] for i in items) == ["Q2?", "Q3?", "Q4?"]


def test_pairwise_sample_size_samples_that_many_common_questions(env):
    client, sf = env
    q = [f"Q{i}?" for i in range(10)]
    experiment_id, r1, r2 = _pair_experiment(sf, q, q)

    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2), sample_size=4, seed=1)

    assert rnd["size"] == 4


def test_asking_for_more_common_questions_than_exist_is_refused(env):
    client, sf = env
    q = [f"Q{i}?" for i in range(3)]
    experiment_id, r1, r2 = _pair_experiment(sf, q, q)

    response = client.post("/annotation/rounds", json={
        "name": "pares", "kind": "pairwise", "items": _pair_items_arg(experiment_id, r1, r2), "sample_size": 10,
    })

    assert response.status_code == 422
    assert "3" in response.json()["detail"]


def test_a_pairwise_round_needs_exactly_two_combinations(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])

    one_item = client.post("/annotation/rounds", json={
        "name": "x", "kind": "pairwise", "items": [f"{experiment_id}:{r1}"],
    })
    three_items = client.post("/annotation/rounds", json={
        "name": "x", "kind": "pairwise",
        "items": [f"{experiment_id}:{r1}", f"{experiment_id}:{r2}", f"{experiment_id}:{r1}"],
    })

    assert one_item.status_code == 422
    assert three_items.status_code == 422


def test_the_ab_order_is_reproducible_with_the_seed(env):
    client, sf = env
    q = [f"Q{i}?" for i in range(6)]
    experiment_id, r1, r2 = _pair_experiment(sf, q, q)
    items = _pair_items_arg(experiment_id, r1, r2)
    ana = _annotator(client, "Ana")

    def answer_by_question(seed):
        rnd = _pair_round(client, items, seed=seed)
        qs = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()["items"]
        return {i["question"]: i["answer_a"] for i in qs}

    first, second = answer_by_question(5), answer_by_question(5)
    assert first == second
    assert answer_by_question(6) != first


def test_the_queue_is_blind_for_pairwise_rounds(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana = _annotator(client)

    item = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()["items"][0]

    hidden = {"rag", "llm", "experiment_id", "combination", "source_result_id_1", "source_result_id_2",
              "answer_1", "answer_2", "context_1", "context_2"}
    assert hidden.isdisjoint(item)
    assert "naive" not in str(item) and "agentic" not in str(item) and "qwen" not in str(item)
    assert {"answer_a", "answer_b", "context_a", "context_b"} <= set(item)


def test_pairwise_note_requires_a_preference_or_cannot_evaluate(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana = _annotator(client)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]

    assert _pair_note(client, item_id, ana).status_code == 422  # no preference
    assert _pair_note(client, item_id, ana, preference="A").status_code == 422  # no reasons
    assert _pair_note(client, item_id, ana, preference="A", reasons=["mais_correta"]).status_code == 200
    assert _pair_note(client, item_id, ana, preference="tie", reasons=["mais_correta"]).status_code == 422
    assert _pair_note(client, item_id, ana, preference="tie").status_code == 200
    assert _pair_note(client, item_id, ana, cannot_evaluate=True).status_code == 422  # no reason text
    assert _pair_note(client, item_id, ana, cannot_evaluate=True, reason="ambígua").status_code == 200
    assert _pair_note(client, item_id, ana, cannot_evaluate=True, reason="ambígua",
                      preference="A").status_code == 422


def test_an_invalid_pairwise_reason_is_refused(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana = _annotator(client)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]

    assert _pair_note(client, item_id, ana, preference="A", reasons=["chute"]).status_code == 422


def test_a_pairwise_note_is_saved_and_shown_in_the_queue(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana = _annotator(client)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]

    saved = _pair_note(client, item_id, ana, preference="B", reasons=["mais_completa", "mais_concisa"],
                       comment="Melhor organizada.")

    assert saved.status_code == 200
    queue = client.get(f"/annotation/rounds/{rnd['id']}/queue", params={"annotator_id": ana}).json()
    assert queue["items"][0]["note"] == {"preference": "B", "reasons": ["mais_completa", "mais_concisa"],
                                        "cannot_evaluate": False, "reason": None, "comment": "Melhor organizada."}
    assert queue["done"] == 1


def test_pairwise_export_unblinds_which_combination_was_a_and_translates_the_preference(env):
    import csv
    import io
    client, sf = env
    q = ["Q0?", "Q1?"]
    experiment_id, r1, r2 = _pair_experiment(sf, q, q)
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2), seed=3)
    ana = _annotator(client, "Ana")
    items = _pair_items_by_position(sf, rnd["id"])
    _pair_note(client, items[0]["id"], ana, preference="A", reasons=["mais_correta"])
    _pair_note(client, items[1]["id"], ana, preference="B", reasons=["mais_concisa"])
    client.post(f"/annotation/rounds/{rnd['id']}/close")

    response = client.get(f"/annotation/rounds/{rnd['id']}/export.csv")

    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("﻿"))))
    assert len(rows) == 2
    for row in rows:
        assert row["run1_rag"] == "naive" and row["run2_rag"] == "agentic"
        assert row["a_e_do_run"] in ("1", "2")
        assert row["preferencia"] in ("naive·qwen3.5 melhor", "agentic·qwen3.5 melhor")
    row0 = next(r for r in rows if int(r["item"]) == items[0]["id"])
    expected_label = "naive·qwen3.5" if row0["a_e_do_run"] == "1" else "agentic·qwen3.5"
    assert row0["preferencia"] == f"{expected_label} melhor"
    assert row0["preferencia_final"] == row0["preferencia"]
    assert row0["situacao_final"] == "uma nota"


def test_pairwise_agreement_has_kappa_variants_and_alpha(env):
    client, sf = env
    q = [f"Q{i}?" for i in range(4)]
    experiment_id, r1, r2 = _pair_experiment(sf, q, q)
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2), seed=9)
    ana, bruno = _annotator(client, "Ana"), _annotator(client, "Bruno")
    items = _pair_items_by_position(sf, rnd["id"])
    # The same (0, 1, 2, 2) / (0, 2, 2, 1) sequence hand-worked for kappa in test_annotation_agreement.py,
    # with 0="A", 1="tie", 2="B": kappa unweighted 0.2, kappa linear 3/7, kappa quadratic 7/11.
    for item, pref in zip(items, ["A", "tie", "B", "B"]):
        _pair_note(client, item["id"], ana, preference=pref, reasons=([] if pref == "tie" else ["mais_correta"]))
    for item, pref in zip(items, ["A", "B", "B", "tie"]):
        _pair_note(client, item["id"], bruno, preference=pref, reasons=([] if pref == "tie" else ["mais_correta"]))

    result = client.get(f"/annotation/rounds/{rnd['id']}/agreement", params={"resamples": 200}).json()

    dim = result["dimension"]
    assert dim["n"] == 4
    assert dim["kappa_unweighted"]["value"] == pytest.approx(0.2)
    assert dim["kappa_linear"]["value"] == pytest.approx(3 / 7)
    assert dim["alpha"]["value"] is not None
    assert dim["confusion"]["avaliadores"] == ["Ana", "Bruno"]
    assert dim["confusion"]["levels"] == ["A", "tie", "B"]
    assert dim["confusion"]["matrix"] == [[1, 0, 0], [0, 0, 1], [0, 1, 1]]
    assert len(result["disagreements"]) == 2


def test_pairwise_summary_gives_wins_ties_sign_test_and_wilson_ci(env):
    client, sf = env
    q = [f"Q{i}?" for i in range(4)]
    experiment_id, r1, r2 = _pair_experiment(sf, q, q)
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2), seed=4)
    ana = _annotator(client, "Ana")
    items = _pair_items_by_position(sf, rnd["id"])
    # Want: run 1 wins twice, run 2 once, one tie, whichever item's own A/B coin flip came up.
    for item, want in zip(items, ["1", "1", "2", "tie"]):
        if want == "tie":
            _pair_note(client, item["id"], ana, preference="tie")
        else:
            preference = "A" if (want == "1") == item["a_is_1"] else "B"
            _pair_note(client, item["id"], ana, preference=preference, reasons=["mais_correta"])
    client.post(f"/annotation/rounds/{rnd['id']}/close")

    result = client.get(f"/annotation/rounds/{rnd['id']}/pairwise-summary").json()

    ana_summary = result["avaliadores"]["Ana"]
    assert ana_summary["wins"] == {"1": 2, "2": 1}
    assert ana_summary["ties"] == 1
    assert ana_summary["n_decided"] == 3
    assert ana_summary["sign_test_p"] == pytest.approx(1.0)  # n=10,k=2 would be 0.109; here n=3,k=1: 1.0
    assert ana_summary["proportion"]["1"]["value"] == pytest.approx(2 / 3)
    assert ana_summary["proportion"]["1"]["low"] == pytest.approx(0.2077, abs=0.001)
    assert ana_summary["proportion"]["1"]["high"] == pytest.approx(0.9385, abs=0.001)
    assert ana_summary["reasons"]["1"] == {"mais_correta": 2}
    assert result["final"]["wins"] == {"1": 2, "2": 1}  # a single Avaliador: the final is their own
    assert result["pair_run_1"]["rag"] == "naive"
    assert result["pair_run_2"]["rag"] == "agentic"


def test_pairwise_adjudication_decides_the_final_preference(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana, bruno, ori = _annotator(client, "Ana"), _annotator(client, "Bruno"), _annotator(client, "Orientador")
    item = _pair_items_by_position(sf, rnd["id"])[0]
    _pair_note(client, item["id"], ana, preference="A", reasons=["mais_correta"])
    _pair_note(client, item["id"], bruno, preference="B", reasons=["mais_concisa"])
    client.post(f"/annotation/rounds/{rnd['id']}/close")
    client.patch(f"/annotation/rounds/{rnd['id']}", json={"adjudicator_id": ori})

    view = client.get(f"/annotation/rounds/{rnd['id']}/pair-adjudication", params={"annotator_id": ori}).json()
    assert len(view["items"]) == 1
    assert view["items"][0]["notes"]["Ana"]["preference"] == "A"
    assert view["items"][0]["notes"]["Bruno"]["preference"] == "B"

    decided = client.put(f"/annotation/pair-items/{item['id']}/adjudication",
                         json={"annotator_id": ori, "preference": "B"})
    assert decided.status_code == 200

    final = client.get(f"/annotation/rounds/{rnd['id']}/pairwise-summary").json()["final"]
    expected_side = "2" if item["a_is_1"] else "1"  # "B" won: translate to which run that is
    other_side = "1" if expected_side == "2" else "2"
    assert final["wins"][expected_side] == 1
    assert final["wins"][other_side] == 0


def test_an_item_without_disagreement_cannot_be_pair_adjudicated(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana, ori = _annotator(client, "Ana"), _annotator(client, "Orientador")
    item = _pair_items_by_position(sf, rnd["id"])[0]
    _pair_note(client, item["id"], ana, preference="A", reasons=["mais_correta"])
    client.post(f"/annotation/rounds/{rnd['id']}/close")
    client.patch(f"/annotation/rounds/{rnd['id']}", json={"adjudicator_id": ori})

    response = client.put(f"/annotation/pair-items/{item['id']}/adjudication",
                          json={"annotator_id": ori, "preference": "B"})

    assert response.status_code == 409


def test_single_rounds_default_to_kind_single_and_are_unaffected(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)

    assert rnd["kind"] == "single"
    assert client.get("/annotation/rounds").json()[0]["kind"] == "single"
    assert client.get(f"/annotation/rounds/{rnd['id']}").json()["kind"] == "single"


def test_validation_retest_and_latex_are_refused_for_pairwise_rounds(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana = _annotator(client)
    item = _pair_items_by_position(sf, rnd["id"])[0]
    _pair_note(client, item["id"], ana, preference="A", reasons=["mais_correta"])
    client.post(f"/annotation/rounds/{rnd['id']}/close")

    assert client.get(f"/annotation/rounds/{rnd['id']}/validation").status_code == 409
    assert client.get(f"/annotation/rounds/{rnd['id']}/export.tex").status_code == 409
    assert client.post(f"/annotation/rounds/{rnd['id']}/retest", json={"annotator_id": ana}).status_code == 409


def test_deleting_a_round_without_notes_succeeds(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=2)

    response = client.delete(f"/annotation/rounds/{rnd['id']}")

    assert response.status_code == 200
    assert client.get(f"/annotation/rounds/{rnd['id']}").status_code == 404


def test_deleting_a_round_with_notes_is_refused(env):
    client, sf = env
    rnd = _round(client, _experiment(sf), size=1)
    ana = _annotator(client)
    item_id = client.get(f"/annotation/rounds/{rnd['id']}/queue",
                         params={"annotator_id": ana}).json()["items"][0]["id"]
    client.put(f"/annotation/items/{item_id}/notes/{ana}", json={"correctness": 1, "grounding": 1})

    response = client.delete(f"/annotation/rounds/{rnd['id']}")

    assert response.status_code == 409
    assert client.get(f"/annotation/rounds/{rnd['id']}").status_code == 200


def test_deleting_a_pairwise_round_with_notes_is_refused(env):
    client, sf = env
    experiment_id, r1, r2 = _pair_experiment(sf, ["Q0?"], ["Q0?"])
    rnd = _pair_round(client, _pair_items_arg(experiment_id, r1, r2))
    ana = _annotator(client)
    item = _pair_items_by_position(sf, rnd["id"])[0]
    _pair_note(client, item["id"], ana, preference="A", reasons=["mais_correta"])

    response = client.delete(f"/annotation/rounds/{rnd['id']}")

    assert response.status_code == 409


def test_an_unknown_round_cannot_be_deleted(env):
    client, _ = env

    assert client.delete("/annotation/rounds/999").status_code == 404
