"""API side of building the Grafo de conhecimento: progress and the preflight count."""
import io
import json

from app.api.experiments import get_experiment_deps
from app.core.db.models import Experiment
from app.experiments import orchestrator
from tests.test_experiments_api import client  # noqa: F401


def test_detail_reports_the_building_graph_phase_with_chunks_extracted(client):  # noqa: F811
    deps = client.app.dependency_overrides[get_experiment_deps]()
    session = deps.session_factory()
    experiment = Experiment(
        name="construindo", status="running",
        config={"chunkings": ["recursive"], "embeddings": ["gemini"], "rags": ["graph"],
                "retrievers": ["similarity"], "llms": ["gemini"], "phase": "building_graph"},
    )
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    orchestrator._graph_progress[experiment_id] = {"extracted": 2, "total": 5}
    try:
        progress = client.get(f"/experiments/{experiment_id}").json()["progress"]
    finally:
        orchestrator._graph_progress.pop(experiment_id, None)
    assert progress["phase"] == "building_graph"
    assert progress["graph"] == {"extracted": 2, "total": 5}


def _preflight(client, rags, llms):  # noqa: F811
    return client.post("/experiments/preflight", json={
        "base": "viagem", "indexes": [{"chunking": "recursive", "embedding": "gemini"}],
        "rags": rags, "llms": llms,
    })


def test_preflight_counts_the_grafos_still_to_build(client):  # noqa: F811
    response = _preflight(client, ["naive", "graph"], ["gemini", "qwen3:1.7b"])
    assert response.status_code == 200
    assert response.json()["graphs_to_build"] == [
        {"chunking": "recursive", "embedding": "gemini", "llm": "gemini"},
        {"chunking": "recursive", "embedding": "gemini", "llm": "qwen3:1.7b"},
    ]
    assert _preflight(client, ["naive"], ["gemini"]).json()["graphs_to_build"] == []

    config = {"base": "viagem", "chunkings": ["recursive"], "embeddings": ["gemini"],
              "rags": ["graph"], "retrievers": ["similarity"], "metrics": ["rouge_l"],
              "llms": ["gemini"]}
    files = {"questions": ("q.csv", io.BytesIO(b"pergunta\nOnde?\n"), "text/csv")}
    client.post("/experiments", data={"config": json.dumps(config)}, files=files)

    # The gemini Grafo now exists: only the other LLM extrator's is left.
    assert _preflight(client, ["graph"], ["gemini", "qwen3:1.7b"]).json()["graphs_to_build"] == [
        {"chunking": "recursive", "embedding": "gemini", "llm": "qwen3:1.7b"},
    ]
