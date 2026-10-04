"""Building the Grafo de conhecimento inside an experiment: cache, progress, pause, memory.

Driven through run_experiment with a fake LLM that counts extraction calls,
Qdrant :memory: and SQLite (no network, no Postgres).
"""
import pytest
from qdrant_client import QdrantClient

from app.core.db.models import Experiment
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.experiments import orchestrator
from app.experiments.orchestrator import ExperimentDeps, request_pause, run_experiment
from app.experiments.schemas import ExperimentConfig, QuestionItem
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig
from tests.test_orchestrator import _FakeEmbedder, _embedder_factory, session_factory  # noqa: F401

_REPLY = "entidade<|>Praça Central<|>lugar<|>Praça no centro.\n<|FIM|>"
_DOC = "Para one.\n\nPara two here.\n\nPara three, longer."


class _CountingLLM:
    """Answers extraction prompts with one entity and records each one; else answers."""

    def __init__(self, calls, on_extract=None):
        self.calls = calls
        self._on_extract = on_extract

    def generate(self, prompt):
        if prompt.startswith("Extraia do texto"):
            self.calls.append(prompt)
            if self._on_extract:
                self._on_extract(len(self.calls))
            return _REPLY
        return "Resposta gerada."


def _store(embeddings=("e5",), text=_DOC, store=None):
    store = store or QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text=text)],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=list(embeddings)),
        store, embedder_factory=_embedder_factory,
    )
    return store


def _chunks(store, embedding="e5"):
    return store.scroll(collection_name("viagem", "recursive", embedding))


def _deps(store, session_factory, calls, on_extract=None, events=None):  # noqa: F811
    from app.core.memory.manager import ModelManager

    def factory(name, **kwargs):
        if events is not None:
            events.append(f"load:{name}")
        return _FakeEmbedder()

    def llm(name, **kw):
        if events is not None:
            return _EventLLM(calls, events)
        return _CountingLLM(calls, on_extract)

    models = ModelManager(
        factory, max_local=1, is_local=lambda n: n in {"e5", "paraphrase"},
        on_evict=(lambda: events.append("evict")) if events is not None else (lambda: None),
    )
    return ExperimentDeps(store=store, session_factory=session_factory, llm_factory=llm,
                          models=models)


def _experiment(session_factory, name, prompts=None):  # noqa: F811
    session = session_factory()
    experiment = Experiment(name=name, status="pending",
                            config={"prompts": prompts} if prompts else {})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    return experiment_id


def _config(**kw):
    base = dict(base="viagem", chunkings=["recursive"], embeddings=["e5"], rags=["graph"],
                retrievers=["similarity"], metrics=["rouge_l"], llms=["qwen3:1.7b"],
                eval_embedding="e5")
    return ExperimentConfig(**{**base, **kw})


def _run(session_factory, deps, name, config=None, prompts=None, experiment_id=None):  # noqa: F811
    experiment_id = experiment_id or _experiment(session_factory, name, prompts)
    run_experiment(experiment_id, config or _config(), [QuestionItem(text="Onde fica a praça?")],
                   deps)
    session = session_factory()
    experiment = session.get(Experiment, experiment_id)
    status = experiment.status
    runs = [(r.embedding, r.status, r.graph_stats, [x.generated_answer for x in r.results])
            for r in experiment.runs]
    session.close()
    return status, runs


def test_a_second_experiment_on_the_same_index_and_llm_does_not_call_the_extractor(
    session_factory,  # noqa: F811
):
    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _run(session_factory, deps, "first")
    assert len(calls) == len(_chunks(store))

    status, [(_, _, stats, answers)] = _run(session_factory, deps, "second")
    assert status == "done" and answers == ["Resposta gerada."]
    assert stats["entities"] == 1
    assert len(calls) == len(_chunks(store))  # no new extraction


def test_the_same_chunking_with_another_embedding_reuses_the_extraction(
    session_factory,  # noqa: F811
):
    store, calls = _store(("e5", "paraphrase")), []
    deps = _deps(store, session_factory, calls)
    status, runs = _run(session_factory, deps, "two-embeddings",
                        _config(embeddings=["e5", "paraphrase"]))
    assert status == "done"
    # Both Índices got their own Grafo, from one extraction per chunk.
    assert sorted(r[0] for r in runs) == ["e5", "paraphrase"]
    assert all(r[2]["entities"] == 1 for r in runs)
    assert len(calls) == len(_chunks(store))


def test_changing_the_extraction_prompt_invalidates_the_cache(session_factory):  # noqa: F811
    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _run(session_factory, deps, "v1", prompts={"graph": {"extract": "Extraia do texto v1: {text}"}})
    _run(session_factory, deps, "v1-again",
         prompts={"graph": {"extract": "Extraia do texto v1: {text}"}})
    assert len(calls) == len(_chunks(store))

    _run(session_factory, deps, "v2", prompts={"graph": {"extract": "Extraia do texto v2: {text}"}})
    assert len(calls) == 2 * len(_chunks(store))
    assert all(c.startswith("Extraia do texto v2") for c in calls[len(_chunks(store)):])


def test_reingesting_the_index_rebuilds_the_grafo_on_the_new_chunks(session_factory):  # noqa: F811
    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _run(session_factory, deps, "before")

    store.delete_collection(collection_name("viagem", "recursive", "e5"))
    _store(text="Praça Central fica no centro.", store=store)
    [new_chunk] = [c["payload"]["text"] for c in _chunks(store)]
    status, [(_, _, stats, _)] = _run(session_factory, deps, "after")
    assert status == "done"
    assert stats["chunks"] == 1
    assert new_chunk in calls[-1]


def test_a_markdown_index_is_extracted_without_its_heading_path(session_factory):  # noqa: F811
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="guia.md", text=(
            "# Guia da cidade\n## Perguntas frequentes\n### A praça\nA Praça Central fica no centro."
        ))],
        IngestConfig(base="viagem", chunkings=["markdown"], embeddings=["e5"]),
        store, embedder_factory=_embedder_factory,
    )
    calls = []
    status, [(_, _, stats, _)] = _run(
        session_factory, _deps(store, session_factory, calls), "markdown",
        _config(chunkings=["markdown"]),
    )
    assert status == "done" and stats["entities"] == 1
    [prompt] = calls
    assert "Texto: A Praça Central fica no centro." in prompt
    assert "Guia da cidade" not in prompt and "Perguntas frequentes" not in prompt


def test_a_chunk_of_headings_only_is_not_sent_to_the_extractor(session_factory):  # noqa: F811
    # The paragraph fills a recursive chunk, so the title is cut off on its own.
    store, calls = _store(text="# Guia da cidade\n\n" + "A praça fica no centro. " * 41), []
    assert "# Guia da cidade" in [c["payload"]["text"] for c in _chunks(store)]

    status, [(_, _, stats, _)] = _run(session_factory, _deps(store, session_factory, calls), "h")
    assert status == "done" and stats["chunks"] == len(_chunks(store))
    assert len(calls) == len(_chunks(store)) - 1


def test_a_grafo_built_by_an_older_version_is_rebuilt_from_the_cache(
    session_factory, monkeypatch,  # noqa: F811
):
    from app.core.graph import build

    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _run(session_factory, deps, "v1")
    seen = []
    monkeypatch.setattr(build, "GRAPH_VERSION", build.GRAPH_VERSION + 1)
    monkeypatch.setattr(orchestrator, "build_graph", lambda *a, **kw: seen.append(1) or
                        build.build_graph(*a, **kw))

    status, [(_, _, stats, _)] = _run(session_factory, deps, "v2")
    assert status == "done" and stats["entities"] == 1
    # Rebuilt, but the extractions still hold: no new LLM call.
    assert seen == [1]
    assert len(calls) == len(_chunks(store))


def test_the_build_shows_as_building_graph_with_chunks_extracted(session_factory):  # noqa: F811
    seen = []

    def on_extract(n):
        session = session_factory()
        phase = session.get(Experiment, experiment_id).config.get("phase")
        session.close()
        seen.append((phase, orchestrator.graph_build_progress(experiment_id)))

    store, calls = _store(), []
    total = len(_chunks(store))
    experiment_id = _experiment(session_factory, "progress")
    status, _ = _run(session_factory, _deps(store, session_factory, calls, on_extract), "progress",
                     experiment_id=experiment_id)
    assert status == "done"
    # Seen while extracting chunk n: the n-1 before it are done.
    assert seen == [("building_graph", {"extracted": n, "total": total}) for n in range(total)]
    assert orchestrator.graph_build_progress(experiment_id) is None


def test_a_pause_during_the_build_resumes_without_reextracting(session_factory):  # noqa: F811
    store, calls = _store(), []
    total = len(_chunks(store))
    experiment_id = _experiment(session_factory, "paused")
    deps = _deps(store, session_factory, calls,
                 on_extract=lambda n: n == 1 and request_pause(experiment_id))
    status, [(_, run_status, _, answers)] = _run(session_factory, deps, "paused",
                                                 experiment_id=experiment_id)
    assert (status, run_status, answers) == ("paused", "paused", [])
    assert len(calls) == 1

    status, [(_, run_status, stats, _)] = _run(
        session_factory, _deps(store, session_factory, calls), "resumed"
    )
    assert (status, run_status, stats["chunks"]) == ("done", "done", total)
    assert len(calls) == total  # the first chunk was not asked again


class _EventLLM:
    def __init__(self, calls, events):
        self.calls, self._events = calls, events

    def generate(self, prompt):
        if prompt.startswith("Extraia do texto"):
            self.calls.append(prompt)
            self._events.append("extract")
            return _REPLY
        self._events.append("gen")
        return "Resposta gerada."


def test_low_profile_never_holds_the_extractor_and_the_embedder_together(
    session_factory, monkeypatch,  # noqa: F811
):
    from app.core.llm import ollama

    events, calls = [], []
    monkeypatch.setattr(ollama, "unload_local_llm", lambda name, *a, **k: events.append("unload"))
    store = _store()
    status, _ = _run(session_factory, _deps(store, session_factory, calls, events=events), "low")
    assert status == "done"
    first, last = events.index("extract"), len(events) - 1 - events[::-1].index("extract")
    write = events.index("load:e5", last)
    gen = events.index("gen")
    assert not any(e.startswith("load:") for e in events[first:last])  # extraction: LLM only
    assert "unload" in events[last:write]                               # LLM out before embedder
    assert "evict" in events[write:gen]                                 # embedder out before gen


def test_an_embedder_an_earlier_run_loaded_leaves_before_the_extraction(
    session_factory,  # noqa: F811
):
    events, calls = [], []
    store = _store()
    # HyDE embeds the passage the LLM writes: the real embedder loads during generation.
    status, _ = _run(session_factory, _deps(store, session_factory, calls, events=events),
                     "hyde-then-graph", _config(rags=["hyde", "graph"]))
    assert status == "done"
    before = events[: events.index("extract")]
    assert before.count("load:e5") == 2  # stage A and the HyDE fallback
    assert before.count("evict") == before.count("load:e5")  # none left next to the extractor
