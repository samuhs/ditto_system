"""Tests for the experiments endpoints (background runs synchronously under TestClient)."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.experiments import get_experiment_deps
from app.core.db.base import Base
from app.core.db.models import Experiment
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.orchestrator import ExperimentDeps
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig
from app.main import create_app


class _FakeEmbedder:
    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [float(len(text) % 5), 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _FakeLLM:
    def generate(self, prompt: str) -> str:
        return "An answer."


def _embedder_factory(name, **kwargs):
    return _FakeEmbedder()


def _llm_factory(name, **kwargs):
    return _FakeLLM()


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two.\n\nPara three.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )
    app = create_app()
    app.dependency_overrides[get_experiment_deps] = lambda: deps
    return TestClient(app)


def _config_payload():
    return json.dumps(
        {
            "base": "viagem",
            "chunkings": ["recursive"],
            "embeddings": ["gemini"],
            "rags": ["naive"],
            "retrievers": ["similarity"],
            "metrics": ["answer_relevancy"], "llms": ["gemini"],
        }
    )


def test_create_experiment_runs_and_persists(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    response = client.post("/experiments", data={"config": _config_payload()}, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"pending", "done"}
    assert body["name"]
    assert body["warnings"] == []

    detail = client.get(f"/experiments/{body['id']}").json()
    assert detail["status"] == "done"
    assert len(detail["results"]) == 1
    assert detail["results"][0]["answer"] == "An answer."
    assert "answer_relevancy" in detail["results"][0]["scores"]


def test_list_experiments_paginated(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    client.post("/experiments", data={"config": _config_payload()}, files=files)
    body = client.get("/experiments").json()
    assert set(body.keys()) == {"items", "total", "page", "page_size"}
    assert body["total"] >= 1
    assert body["page"] == 1 and body["page_size"] == 20
    item = body["items"][0]
    assert {"id", "name", "status", "created_at"} <= set(item.keys())
    assert item["created_at"]  # ISO string present
    assert item["created_at"].endswith("+00:00")


def test_get_experiment_includes_timestamps(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["created_at"]  # present
    assert detail["created_at"].endswith("+00:00")
    assert detail["finished_at"]  # experiment ran to completion → finished_at set
    assert detail["finished_at"].endswith("+00:00")


def test_get_missing_experiment_404(client):
    assert client.get("/experiments/99999").status_code == 404


def test_create_experiment_invalid_config_422(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nWhere?\n"), "text/csv")}
    response = client.post("/experiments", data={"config": "{not valid json"}, files=files)
    assert response.status_code == 422


def test_create_experiment_csv_missing_column_422(client):
    files = {"questions": ("q.csv", io.BytesIO(b"wrong_header\nvalue\n"), "text/csv")}
    response = client.post("/experiments", data={"config": _config_payload()}, files=files)
    assert response.status_code == 422


def test_create_experiment_rejects_base_colliding_with_graph_marker(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    config = json.loads(_config_payload())
    config["base"] = "viagem__kg_x"
    response = client.post("/experiments", data={"config": json.dumps(config)}, files=files)
    assert response.status_code == 422


def test_experiment_records_llm_dimension(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    config = json.dumps({
        "base": "viagem", "chunkings": ["recursive"], "embeddings": ["gemini"],
        "rags": ["naive"], "retrievers": ["similarity"], "metrics": ["answer_relevancy"],
        "llms": ["gemini", "ollama"],
    })
    resp = client.post("/experiments", data={"config": config}, files=files)
    assert resp.status_code == 200
    detail = client.get(f"/experiments/{resp.json()['id']}").json()
    llms_in_rows = {row["llm"] for row in detail["results"]}
    assert llms_in_rows == {"gemini", "ollama"}


def test_get_experiment_reports_pause_requested(client):
    from app.experiments.orchestrator import _pause_requests, request_pause

    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    request_pause(exp_id)
    try:
        assert client.get(f"/experiments/{exp_id}").json()["pause_requested"] is True
    finally:
        _pause_requests.pop(exp_id, None)


def test_experiment_snapshots_prompts(client):
    config = {
        "base": "viagem",
        "chunkings": ["recursive"],
        "embeddings": ["gemini"],
        "rags": ["naive"],
        "retrievers": ["similarity"],
        "metrics": ["answer_relevancy"], "llms": ["gemini"],
    }
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nOnde fica o centro?\n"), "text/csv")}
    data = {"config": json.dumps(config)}
    resp = client.post("/experiments", data=data, files=files)
    assert resp.status_code == 200
    exp_id = resp.json()["id"]

    detail = client.get(f"/experiments/{exp_id}").json()
    assert "prompts" in detail
    assert "naive" in detail["prompts"]
    assert "answer" in detail["prompts"]["naive"]
    assert "{context}" in detail["prompts"]["naive"]["answer"]


def _build_grafo(client, llm, extractor="gemini"):
    """Build the base's Grafo beforehand, as a Grafo build job would: experiments only query."""
    from contextlib import nullcontext

    from app.core.graph.build import build_graph

    deps = client.app.dependency_overrides[get_experiment_deps]()
    build_graph(deps.store, "viagem", "recursive", "gemini", extractor, llm,
                lambda: nullcontext(_FakeEmbedder()))


def test_graph_snapshots_only_the_naive_answer_prompt(client):
    from app.core.prompts import load_prompt

    _build_grafo(client, _FakeLLM())
    exp_id = _post_with_metrics(
        client, ["rouge_l"], "pergunta\nOnde?\n", rags=("graph",)
    ).json()["id"]

    prompts = client.get(f"/experiments/{exp_id}").json()["prompts"]
    assert prompts == {"graph": {"answer": load_prompt("naive", "answer")}}


def test_graph_mix_snapshots_the_graphs_prompts_it_shares(client):
    from app.core.prompts import load_prompt

    _build_grafo(client, _FakeLLM())
    exp_id = _post_with_metrics(
        client, ["rouge_l"], "pergunta\nOnde?\n", rags=("graph_mix",)
    ).json()["id"]

    prompts = client.get(f"/experiments/{exp_id}").json()["prompts"]
    assert prompts == {"graph_mix": {"answer": load_prompt("naive", "answer")}}


def _seed_experiment(client, name="Exp Árvore/1"):
    """Insert an experiment with two results, one of them missing a metric."""
    from app.core.db.models import Experiment, ExperimentRun, RunResult

    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    try:
        experiment = Experiment(name=name, status="done", config={})
        run = ExperimentRun(
            chunking="recursive", embedding="gemini", rag_technique="naive",
            retriever="similarity", llm="gemini", status="done",
        )
        run.results = [
            RunResult(
                question="Onde fica?", reference_answer="Ali", generated_answer="Lá, perto",
                scores={"faithfulness": 0.5, "answer_relevancy": 1.0}, latency_ms=120, tokens=42,
            ),
            RunResult(
                question="Quando?", reference_answer=None, generated_answer="Amanhã",
                scores={"answer_relevancy": 0.25}, latency_ms=80, tokens=10,
            ),
        ]
        experiment.runs = [run]
        session.add(experiment)
        session.commit()
        return experiment.id
    finally:
        session.close()


def test_export_experiment_csv(client):
    import csv

    exp_id = _seed_experiment(client)
    response = client.get(f"/experiments/{exp_id}/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="Exp_Arvore_1.csv"' in disposition

    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # BOM so Excel detects UTF-8
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0] == [
        "chunking", "embedding", "rag", "retriever", "llm",
        "pergunta", "resposta_referencia", "resposta",
        "tipo", "evidencia_salto", "entidades_ponte",
        "answer_relevancy", "faithfulness", "media", "latency_ms", "tokens",
    ]
    assert len(rows) == 3
    assert rows[1] == [
        "recursive", "gemini", "naive", "similarity", "gemini",
        "Onde fica?", "Ali", "Lá, perto", "simples", "", "",
        "1.0", "0.5", "0.75", "120", "42",
    ]
    # missing metric → empty cell; media averages only present scores
    assert rows[2][6] == ""
    assert rows[2][11:] == ["0.25", "", "0.25", "80", "10"]


def test_export_missing_experiment_404(client):
    assert client.get("/experiments/99999/export.csv").status_code == 404


def _indexes_payload(indexes):
    return json.dumps(
        {
            "base": "viagem",
            "chunkings": sorted({i["chunking"] for i in indexes}),
            "embeddings": sorted({i["embedding"] for i in indexes}),
            "indexes": indexes,
            "rags": ["naive"],
            "retrievers": ["similarity"],
            "metrics": ["answer_relevancy"], "llms": ["gemini"],
        }
    )


def test_create_experiment_with_existing_indexes(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    payload = _indexes_payload([{"chunking": "recursive", "embedding": "gemini"}])
    response = client.post("/experiments", data={"config": payload}, files=files)
    assert response.status_code == 200


def test_create_experiment_rejects_missing_index(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    payload = _indexes_payload([{"chunking": "fixed", "embedding": "e5"}])
    response = client.post("/experiments", data={"config": payload}, files=files)
    assert response.status_code == 422
    assert "fixed" in response.json()["detail"]


def test_detail_reports_the_evaluation_phase(client):
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = Experiment(
        name="avaliando", status="running",
        config={"chunkings": ["recursive"], "embeddings": ["gemini"], "rags": ["naive"],
                "retrievers": ["similarity"], "llms": ["gemini"], "phase": "evaluating"},
    )
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    progress = client.get(f"/experiments/{experiment_id}").json()["progress"]
    assert progress["phase"] == "evaluating"


def test_create_experiment_uses_the_saved_eval_embedding(client, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    from app.core.config.runtime import set_eval_embedding

    set_eval_embedding("e5")
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    assert client.get(f"/experiments/{exp_id}").json()["eval_embedding"] == "e5"


def test_create_experiment_keeps_an_explicit_eval_embedding(client, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    payload = json.loads(_config_payload()) | {"eval_embedding": "gemini"}
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": json.dumps(payload)}, files=files).json()["id"]
    assert client.get(f"/experiments/{exp_id}").json()["eval_embedding"] == "gemini"


def test_export_adds_difficulty_signal_columns(client):
    import csv

    from app.core.db.models import Experiment, QuestionProfile, RunResult

    exp_id = _seed_experiment(client, name="sinais")
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = session.get(Experiment, exp_id)
    experiment.question_profiles = [QuestionProfile(question="Onde fica?", signals={"negation": 0.0})]
    result = session.query(RunResult).filter_by(question="Onde fica?").one()
    result.retrieval_signals = {"top_score": 0.9}
    session.commit()
    session.close()

    text = client.get(f"/experiments/{exp_id}/export.csv").content.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0][-2:] == ["pergunta_negation", "busca_top_score"]
    assert rows[1][-2:] == ["0.0", "0.9"]
    assert rows[2][-2:] == ["", ""]


def test_get_experiment_includes_an_empty_pauses_list_by_default(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]
    assert client.get(f"/experiments/{exp_id}").json()["pauses"] == []


def test_get_experiment_surfaces_the_recorded_registro_de_pausa(client):
    from app.core.db.models import Experiment

    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    entry = {
        "paused_at": "2026-01-01T00:00:00+00:00", "reason": "stall", "phase": "generating",
        "in_flight": [{"question": "Onde?"}], "last_error": None,
        "memory": {"free_mb": 1000, "api_mb": 500}, "resumed_at": None,
    }
    experiment = Experiment(name="com-pausa", status="paused", config={}, pauses=[entry])
    session.add(experiment)
    session.commit()
    exp_id = experiment.id
    session.close()

    assert client.get(f"/experiments/{exp_id}").json()["pauses"] == [entry]


def test_questions_are_recorded_with_the_experiment_and_reconstructable(client):
    from app.core.db.models import Experiment
    from app.experiments.schemas import QuestionItem

    files = {
        "questions": (
            "q.csv",
            io.BytesIO(
                "pergunta,evidencia_referencia,tipo,evidencia_salto,entidades_ponte\n"
                "Quando é o evento?,Para one|Para two,ponte,1|2,Parque\n".encode()
            ),
            "text/csv",
        )
    }
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]

    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    stored = session.get(Experiment, exp_id)
    reconstructed = [QuestionItem(**d) for d in stored.questions]
    session.close()

    assert len(reconstructed) == 1
    question = reconstructed[0]
    assert question.text == "Quando é o evento?"
    assert question.evidence == ["Para one", "Para two"]
    assert question.question_type == "ponte"
    assert question.evidence_hops == [1, 2]
    assert question.bridge_entities == ["Parque"]


def test_difficulty_endpoint(client):
    exp_id = _seed_experiment(client, name="dificuldade")
    body = client.get(f"/experiments/{exp_id}/difficulty").json()
    assert body["llms"] == ["gemini"]
    assert {q["question"] for q in body["questions"]} == {"Onde fica?", "Quando?"}
    # Stored before the Tipo de pergunta existed: every question reads as simples.
    assert {q["question_type"] for q in body["questions"]} == {"simples"}
    assert list(body["irt"]["by_type"]) == ["simples"]
    assert client.get("/experiments/99999/difficulty").status_code == 404


def test_oracle_without_any_evidence_is_rejected(client):
    import json

    payload = json.loads(_config_payload())
    payload["rags"] = ["naive", "oracle"]
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    response = client.post("/experiments", data={"config": json.dumps(payload)}, files=files)
    assert response.status_code == 422
    assert "evidencia_referencia" in response.json()["detail"]

    files = {"questions": ("q.csv", io.BytesIO(
        b"pergunta,resposta_referencia,evidencia_referencia\nWhere?,,Aqui.\n"), "text/csv")}
    response = client.post("/experiments", data={"config": json.dumps(payload)}, files=files)
    assert response.status_code == 200


def _post_questions(client, csv_text: str):
    """Create an experiment from a questions CSV given as text."""
    files = {"questions": ("q.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    return client.post("/experiments", data={"config": _config_payload()}, files=files)


def test_annotated_question_is_kept_with_each_result(client):
    response = _post_questions(
        client,
        "pergunta,evidencia_referencia,tipo,evidencia_salto,entidades_ponte\n"
        "Quando é o evento do parque?,Para one|Para two|Para three,ponte,1|2|2,Parque|Evento\n",
    )
    assert response.status_code == 200

    result = client.get(f"/experiments/{response.json()['id']}").json()["results"][0]
    assert result["question_type"] == "ponte"
    assert result["evidence_hops"] == [1, 2, 2]
    assert result["bridge_entities"] == ["Parque", "Evento"]


def test_unannotated_question_is_a_single_hop_simple_question(client):
    response = _post_questions(client, "pergunta,evidencia_referencia\nOnde?,Para one|Para two\n")

    result = client.get(f"/experiments/{response.json()['id']}").json()["results"][0]
    assert result["question_type"] == "simples"
    assert result["evidence_hops"] == [1, 1]
    assert result["bridge_entities"] == []


@pytest.mark.parametrize(
    "csv_text, message",
    [
        ("pergunta,tipo\nOnde?,global\n", "tipo"),
        ("pergunta,evidencia_referencia,evidencia_salto\nOnde?,a|b,1\n", "evidencia_salto"),
        ("pergunta,evidencia_referencia,evidencia_salto\nOnde?,a|b,1|x\n", "evidencia_salto"),
        ("pergunta,evidencia_salto\nOnde?,1|2\n", "evidencia_salto"),
    ],
)
def test_invalid_annotation_is_rejected_on_upload(client, csv_text, message):
    response = _post_questions(client, csv_text)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_export_carries_the_question_annotations(client):
    import csv

    exp_id = _post_questions(
        client,
        "pergunta,evidencia_referencia,tipo,evidencia_salto,entidades_ponte\n"
        "Qual é mais alto?,Para one|Para two,comparacao,1|2,Morro|Ilha\n",
    ).json()["id"]

    text = client.get(f"/experiments/{exp_id}/export.csv").content.decode("utf-8")
    header, row = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    annotations = dict(zip(header, row))
    assert annotations["tipo"] == "comparacao"
    assert annotations["evidencia_salto"] == "1|2"
    assert annotations["entidades_ponte"] == "Morro|Ilha"


def _post_with_metrics(client, metrics: list[str], csv_text: str, rags=("naive",)):
    payload = {**json.loads(_config_payload()), "metrics": metrics, "rags": list(rags)}
    files = {"questions": ("q.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    return client.post("/experiments", data={"config": json.dumps(payload)}, files=files)


_THREE_HOPS_CSV = (
    "pergunta,evidencia_referencia,tipo,evidencia_salto\n"
    "Onde e quando?,Para one|Trecho ausente de toda a base indexada|Para three,ponte,1|2|3\n"
)


def test_result_shows_which_hops_were_retrieved(client):
    exp_id = _post_with_metrics(client, ["context_all_hops"], _THREE_HOPS_CSV).json()["id"]

    result = client.get(f"/experiments/{exp_id}").json()["results"][0]
    assert result["scores"]["context_all_hops"] == 0.0
    assert result["hops_found"] == [
        {"hop": 1, "found": True}, {"hop": 2, "found": False}, {"hop": 3, "found": True},
    ]


def test_hops_are_not_matched_unless_context_all_hops_was_chosen(client):
    exp_id = _post_with_metrics(client, ["context_hit"], _THREE_HOPS_CSV).json()["id"]

    result = client.get(f"/experiments/{exp_id}").json()["results"][0]
    assert result["hops_found"] == []


def test_hops_are_not_matched_for_a_technique_that_retrieves_nothing(client):
    exp_id = _post_with_metrics(
        client, ["context_all_hops"], _THREE_HOPS_CSV, rags=("closed_book",)
    ).json()["id"]

    result = client.get(f"/experiments/{exp_id}").json()["results"][0]
    assert "context_all_hops" not in result["scores"]
    assert result["hops_found"] == []


def test_difficulty_reports_each_question_type(client):
    exp_id = _post_questions(
        client,
        "pergunta,evidencia_referencia,tipo,evidencia_salto,entidades_ponte\n"
        "Quando é o evento do parque?,Para one|Para two,ponte,1|2,Parque\n"
        "Onde fica?,Para three,,,\n",
    ).json()["id"]

    body = client.get(f"/experiments/{exp_id}/difficulty").json()
    types = {q["question"]: q["question_type"] for q in body["questions"]}
    assert types == {"Quando é o evento do parque?": "ponte", "Onde fica?": "simples"}


def test_graph_rows_carry_the_stats_of_their_grafo(client):
    import csv

    # The fake LLM never writes the extraction format: every line fails, the row still runs.
    _build_grafo(client, _FakeLLM())
    exp_id = _post_with_metrics(
        client, ["rouge_l"], "pergunta,resposta_referencia\nOnde?,Ali\n", rags=("naive", "graph")
    ).json()["id"]

    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["status"] == "done"
    stats = {row["rag"]: row["graph_stats"] for row in detail["results"]}
    assert stats["naive"] is None
    graph = stats["graph"]
    assert graph["entities"] == graph["relations"] == 0
    assert graph["chunks"] >= 1 and graph["failed_lines"] == graph["lines"] == graph["chunks"]

    text = client.get(f"/experiments/{exp_id}/export.csv").content.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    by_rag = {row["rag"]: row for row in rows}
    assert by_rag["graph"]["grafo_entities"] == "0"
    assert by_rag["graph"]["grafo_failed_lines"] == str(graph["failed_lines"])
    assert by_rag["naive"]["grafo_entities"] == ""


class _ExtractingLLM:
    """Writes one entity and one relation for every chunk; answers anything else."""

    def generate(self, prompt: str) -> str:
        if prompt.startswith("Extraia do texto"):
            return (
                "entidade<|>Parque Ecológico<|>lugar<|>Um parque.\n"
                "relacao<|>Parque Ecológico<|>Festa do Peão<|>evento<|>A festa é no parque.\n"
                "<|FIM|>"
            )
        return "An answer."


def test_graph_rows_explain_what_the_grafo_found_and_used(client):
    import csv

    _build_grafo(client, _ExtractingLLM())
    exp_id = _post_with_metrics(
        client, ["rouge_l"],
        "pergunta,resposta_referencia,tipo,entidades_ponte\n"
        "Quando é a festa?,Em maio,ponte,parque ecologico|Festa do Peão|Parque\n",
        rags=("naive", "graph"),
    ).json()["id"]

    rows = {row["rag"]: row for row in client.get(f"/experiments/{exp_id}").json()["results"]}
    graph = rows["graph"]
    # "Festa do Peão" only appears as a relation's target: consolidation promotes it.
    assert sorted(e["name"] for e in graph["graph_explanation"]["entities"]) == [
        "Festa do Peão", "Parque Ecológico",
    ]
    assert graph["graph_explanation"]["facts"] == [
        "Parque Ecológico → Festa do Peão: A festa é no parque."
    ]
    # Annotated Entidades-ponte match the Grafo's names ignoring case and accents.
    assert graph["bridges_found"] == [
        {"entity": "parque ecologico", "found": True},
        {"entity": "Festa do Peão", "found": True},
        # Part of a name is not the entity.
        {"entity": "Parque", "found": False},
    ]
    assert rows["naive"]["graph_explanation"] is None
    assert rows["naive"]["bridges_found"] == []

    text = client.get(f"/experiments/{exp_id}/export.csv").content.decode("utf-8")
    by_rag = {row["rag"]: row for row in csv.DictReader(io.StringIO(text.lstrip("﻿")))}
    assert sorted(by_rag["graph"]["grafo_entidades_encontradas"].split("|")) == [
        "Festa do Peão", "Parque Ecológico",
    ]
    assert by_rag["graph"]["grafo_fatos_usados"] == "Parque Ecológico → Festa do Peão: A festa é no parque."
    assert by_rag["graph"]["grafo_pontes_encontradas"] == "parque ecologico|Festa do Peão"
    assert by_rag["graph"]["grafo_entities"] == "2"
    assert by_rag["naive"]["grafo_entidades_encontradas"] == ""


# ---- Retomada (issue #17): POST /experiments/{id}/resume and GET's `resumable`.

def _paused_experiment_with_questions(client, name="retomar-me", status="paused"):
    """An Experiment row with config + questions recorded, as #16's API stores them."""
    config = {
        "base": "viagem", "chunkings": ["recursive"], "embeddings": ["gemini"],
        "rags": ["naive"], "retrievers": ["similarity"], "metrics": ["answer_relevancy"],
        "llms": ["gemini"],
    }
    questions = [{"text": "Onde fica o centro?"}]
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = Experiment(name=name, status=status, config=config, questions=questions)
    session.add(experiment)
    session.commit()
    exp_id = experiment.id
    session.close()
    return exp_id


def test_resume_missing_experiment_404(client):
    assert client.post("/experiments/99999/resume").status_code == 404


def test_resume_rejects_status_not_paused_or_failed(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 409
    assert "done" in response.json()["detail"]


def test_resume_rejects_experiment_without_stored_questions(client):
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = Experiment(name="antigo", status="paused", config={}, questions=None)
    session.add(experiment)
    session.commit()
    exp_id = experiment.id
    session.close()

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 409
    assert "perguntas" in response.json()["detail"]


def test_resume_runs_to_completion(client):
    exp_id = _paused_experiment_with_questions(client)

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 200
    assert response.json() == {"id": exp_id, "status": "pending"}
    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["status"] == "done"
    assert len(detail["results"]) == 1
    assert detail["results"][0]["answer"] == "An answer."


def test_resume_allows_a_failed_experiment(client):
    exp_id = _paused_experiment_with_questions(client, name="falhou", status="failed")

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 200
    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["status"] == "done"


def test_get_experiment_reports_resumable_when_paused_with_questions(client):
    exp_id = _paused_experiment_with_questions(client)
    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["resumable"] is True
    assert detail["resumable_reason"] is None


def test_get_experiment_reports_not_resumable_without_stored_questions(client):
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = Experiment(name="antigo2", status="paused", config={}, questions=None)
    session.add(experiment)
    session.commit()
    exp_id = experiment.id
    session.close()

    detail = client.get(f"/experiments/{exp_id}").json()
    assert detail["resumable"] is False
    assert "perguntas" in detail["resumable_reason"]


def test_get_experiment_reports_not_resumable_when_done(client):
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta,resposta_referencia\nWhere?,\n"), "text/csv")}
    exp_id = client.post("/experiments", data={"config": _config_payload()}, files=files).json()["id"]

    detail = client.get(f"/experiments/{exp_id}").json()

    assert detail["resumable"] is False
    assert detail["resumable_reason"]


# ---- Bloqueio por Índice/Grafo alterado e concorrência na Retomada (issue #21).

def _create_and_pause(client, config=None, csv_text=b"pergunta,resposta_referencia\nOnde?,Ali\n"):
    """Create a real Experimento (recording its Índice/Grafo fingerprint, #21) then force
    it back to `paused`, as if a Pausa had happened right after it finished generating.
    """
    payload = {**json.loads(_config_payload()), **(config or {})}
    files = {"questions": ("q.csv", io.BytesIO(csv_text), "text/csv")}
    exp_id = client.post("/experiments", data={"config": json.dumps(payload)}, files=files).json()["id"]
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = session.get(Experiment, exp_id)
    experiment.status = "paused"
    session.commit()
    session.close()
    return exp_id


def test_resume_allows_when_nothing_changed(client):
    exp_id = _create_and_pause(client)

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 200
    assert client.get(f"/experiments/{exp_id}").json()["status"] == "done"


def test_resume_blocked_when_index_was_reingested(client):
    exp_id = _create_and_pause(client)
    deps = client.app.dependency_overrides[get_experiment_deps]()
    ingest_documents(
        [Document(name="b.txt", text="Mais um trecho novo.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        deps.store,
        embedder_factory=_embedder_factory,
    )

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "recursive" in detail and "gemini" in detail and "reingerido" in detail
    # The GET also reports it as not resumable, with the same reason.
    get_detail = client.get(f"/experiments/{exp_id}").json()
    assert get_detail["resumable"] is False
    assert "reingerido" in get_detail["resumable_reason"]


def test_resume_blocked_when_the_base_was_deleted_and_reingested_identically(client):
    """Deleting the Base and reingesting the exact same documents must be detected
    too (code review of #21): point ids are sequential counters that reset to the
    same values on a fresh collection, so point count alone (the only signal the
    fingerprint used to compare) comes back identical and would wrongly allow the
    Retomada to mix results from two different ingestions of the same Índice.
    """
    exp_id = _create_and_pause(client)
    deps = client.app.dependency_overrides[get_experiment_deps]()
    deps.store.delete_base("viagem")
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two.\n\nPara three.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        deps.store,
        embedder_factory=_embedder_factory,
    )

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 409
    assert "reingerido" in response.json()["detail"]


def test_resume_blocked_when_the_graph_changed(client):
    _build_grafo(client, _FakeLLM())
    exp_id = _create_and_pause(
        client, config={"rags": ["graph"]}, csv_text=b"pergunta\nOnde?\n",
    )
    # Rebuilding the Grafo (a different LLM extrator's output) replaces its collections and
    # built_at, even though the Índice itself (and its chunks_fingerprint) did not change.
    _build_grafo(client, _ExtractingLLM())

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 409
    assert "Grafo de conhecimento" in response.json()["detail"]


def test_resume_not_blocked_without_a_stored_fingerprint(client):
    """An Experimento created before #21 has no `fingerprint` key and is never blocked."""
    exp_id = _paused_experiment_with_questions(client, name="sem-fingerprint")
    deps = client.app.dependency_overrides[get_experiment_deps]()
    ingest_documents(
        [Document(name="b.txt", text="Mais um trecho novo.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        deps.store,
        embedder_factory=_embedder_factory,
    )

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 200


def test_resume_accepts_a_lower_concurrency(client):
    exp_id = _create_and_pause(client, config={"concurrency": 2})

    response = client.post(f"/experiments/{exp_id}/resume", json={"concurrency": 1})

    assert response.status_code == 200
    assert client.get(f"/experiments/{exp_id}").json()["concurrency"] == 1


def test_resume_rejects_concurrency_above_the_current_one(client):
    exp_id = _create_and_pause(client, config={"concurrency": 2})

    response = client.post(f"/experiments/{exp_id}/resume", json={"concurrency": 3})

    assert response.status_code == 422


def test_resume_rejects_concurrency_below_one(client):
    exp_id = _create_and_pause(client, config={"concurrency": 2})

    response = client.post(f"/experiments/{exp_id}/resume", json={"concurrency": 0})

    assert response.status_code == 422


def test_resume_without_a_body_keeps_the_configured_concurrency(client):
    exp_id = _create_and_pause(client, config={"concurrency": 2})

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 200
    assert client.get(f"/experiments/{exp_id}").json()["concurrency"] == 2


def test_resume_is_atomic_when_another_request_wins_the_race(client, monkeypatch):
    """The status flip is one atomic `UPDATE ... WHERE status IN (...)` (code review of
    #15-#21): if another request's Retomada already flipped the row in the gap between
    this request's read-only validation and its own write, the `UPDATE` matches zero
    rows and this request gets 409 instead of blindly overwriting it and scheduling a
    second Retomada of the same Experimento.
    """
    from app.api import experiments as experiments_api

    exp_id = _paused_experiment_with_questions(client)
    deps = client.app.dependency_overrides[get_experiment_deps]()
    real_resumable_reason = experiments_api._resumable_reason

    def _resumable_reason_that_loses_the_race(experiment, store):
        reason = real_resumable_reason(experiment, store)
        # Simulates a second request's Retomada winning the race right here, in the
        # gap between this request's check above and its own write below.
        session = deps.session_factory()
        other = session.get(Experiment, exp_id)
        other.status = "pending"
        session.commit()
        session.close()
        return reason

    monkeypatch.setattr(experiments_api, "_resumable_reason", _resumable_reason_that_loses_the_race)
    scheduled = []
    monkeypatch.setattr(experiments_api, "resume_experiment", lambda *a, **kw: scheduled.append(a))

    response = client.post(f"/experiments/{exp_id}/resume")

    assert response.status_code == 409
    assert scheduled == [], "the loser of the race must never schedule its own Retomada"


def test_resume_twice_in_a_row_rejects_the_second_call(client):
    """Once a Retomada is scheduled, the Experimento is no longer `paused`/`failed`:
    a second POST /resume right after the first gets 409, and only one Retomada runs."""
    exp_id = _paused_experiment_with_questions(client)

    first = client.post(f"/experiments/{exp_id}/resume")
    second = client.post(f"/experiments/{exp_id}/resume")

    assert first.status_code == 200
    assert second.status_code == 409
