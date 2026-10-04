"""End-to-end test for the experiment orchestrator (no network, no Postgres)."""
from unittest.mock import patch

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db.base import Base
from app.core.db.models import Experiment
from app.core.vectorstore.qdrant import QdrantStore
from app.experiments.orchestrator import (
    ExperimentDeps,
    request_pause,
    resume_experiment,
    run_experiment,
)
from app.experiments.schemas import ExperimentConfig, QuestionItem
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig


class _FakeEmbedder:
    """Deterministic 3-dim embedder; no network."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        return [float(len(text) % 5), 1.0, 0.0]

    @property
    def dimension(self) -> int:
        return 3


class _FakeLLM:
    """Returns a fixed answer; no network."""

    def generate(self, prompt: str) -> str:
        return "The center is around the main square."


def _embedder_factory(name, **kwargs):
    return _FakeEmbedder()


def _llm_factory(name, **kwargs):
    return _FakeLLM()


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_run_experiment_persists_results(session_factory):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two here.\n\nPara three.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )

    session = session_factory()
    experiment = Experiment(name="brave-otter-42", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    config = ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy", "faithfulness"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )

    run_experiment(experiment_id, config, [QuestionItem(text="Where is the center?")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done"
    assert len(stored.runs) == 1
    run = stored.runs[0]
    assert (run.chunking, run.embedding, run.rag_technique, run.retriever) == (
        "recursive", "gemini", "naive", "similarity",
    )
    assert len(run.results) == 1
    result = run.results[0]
    assert result.generated_answer == "The center is around the main square."
    assert "answer_relevancy" in result.scores
    assert result.latency_ms >= 0
    assert result.tokens > 0
    assert isinstance(result.retrieved_context, list) and len(result.retrieved_context) >= 1
    check.close()


def test_question_retry_on_transient_failure(session_factory):
    """When rag.answer fails, it retries up to _MAX_RETRIES times then records the error."""
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Some text here for retrieval.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="retry-test", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    call_count = 0

    class _FlakeyLLM:
        def generate(self, prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("503 UNAVAILABLE")

    config = ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=lambda *a, **kw: _FlakeyLLM(),
        embedder_factory=_embedder_factory,
    )

    with patch("app.experiments.orchestrator.time.sleep"):
        run_experiment(
            experiment_id,
            config,
            [QuestionItem(text="Where is the center?")],
            deps,
        )

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done", "experiment should complete even when a question fails"
    run = stored.runs[0]
    assert len(run.results) == 1
    result = run.results[0]
    assert result.generated_answer.startswith("[ERRO:")
    assert call_count == 3, f"expected 3 attempts, got {call_count}"
    check.close()


def test_pause_before_start(session_factory):
    """A pause requested before running stops the experiment with no combinations done."""
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Some text for retrieval.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="pause-early", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    config = ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )

    request_pause(experiment_id)
    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "paused"
    assert all(r.status != "done" for r in stored.runs)
    check.close()


def test_pause_mid_run_keeps_partial_results(session_factory):
    """Pausing after the first combination stops the rest but keeps done combinations."""
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One. Two. Three. Four sentences here.")],
        IngestConfig(base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="pause-mid", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    class _PausingLLM:
        """Requests pause the first time it answers, so combo 2 stops."""

        def generate(self, prompt: str) -> str:
            request_pause(experiment_id)
            return "answer"

    config = ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive", "token"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=lambda *a, **kw: _PausingLLM(),
        embedder_factory=_embedder_factory,
    )

    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "paused"
    done_runs = [r for r in stored.runs if r.status == "done"]
    assert len(done_runs) == 1, "first combination should have completed"
    assert len(done_runs[0].results) == 1
    # Registro de pausa: a manual Pausa records one "manual" entry with the phase
    # it stopped in and a memory snapshot; nothing was in flight (concurrency 1).
    [entry] = stored.pauses
    assert entry["reason"] == "manual"
    assert entry["phase"] == "generating"
    assert entry["in_flight"] == []
    assert entry["resumed_at"] is None
    assert set(entry["memory"]) == {"free_mb", "api_mb"}
    check.close()


def test_run_experiment_cartesian_product(session_factory):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One sentence. Two sentence. Three sentence.")],
        IngestConfig(base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="exp", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    config = ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive", "token"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )
    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert {r.chunking for r in stored.runs} == {"recursive", "token"}
    check.close()


def test_run_experiment_includes_llm_dimension(session_factory):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One. Two. Three sentences here.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="llm-dim", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    seen_llm_names = []

    def _recording_llm_factory(name, **kwargs):
        seen_llm_names.append(name)
        return _FakeLLM()

    config = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
        llms=["gemini", "ollama"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_recording_llm_factory,
        embedder_factory=_embedder_factory,
    )

    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert len(stored.runs) == 2  # 1*1*1*1*2 llms
    assert {r.llm for r in stored.runs} == {"gemini", "ollama"}
    check.close()
    assert set(seen_llm_names) == {"gemini", "ollama"}


def test_rag_not_in_prompt_specs_receives_no_prompts_kwarg(session_factory):
    """A RAG technique absent from PROMPT_SPECS must not be passed a prompts kwarg."""
    from app.core.rag.base import RAGResult

    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Some text for retrieval.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name="gate-test", status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()

    received_kwargs: dict = {}

    class _StubRag:
        def answer(self, query: str) -> RAGResult:
            return RAGResult(answer="a", contexts=[])

    def _recording_rag_factory(name, **kwargs):
        received_kwargs.update(kwargs)
        return _StubRag()

    config = ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["custom_promptless"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
        rag_factory=_recording_rag_factory,
    )

    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    assert "prompts" not in received_kwargs
    assert received_kwargs.get("retriever") is not None


def _seeded_store():
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One. Two. Three. Four sentences here.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    return store


def _new_experiment(session_factory, name):
    session = session_factory()
    experiment = Experiment(name=name, status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    return experiment_id


def _single_combo_config(concurrency):
    return ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive"],
        embeddings=["gemini"],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
        concurrency=concurrency,
    )


def test_concurrency_defaults_to_one():
    config = ExperimentConfig(
        llms=["gemini"],
        base="b", chunkings=["c"], embeddings=["e"], rags=["r"], retrievers=["s"], metrics=["m"]
    )
    assert config.concurrency == 1


def test_concurrent_questions_run_in_parallel_and_keep_order(session_factory):
    """With concurrency N, slow LLM calls overlap and results keep question order."""
    import threading
    import time as _time

    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    class _SlowLLM:
        def generate(self, prompt: str) -> str:
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            _time.sleep(0.2)
            with lock:
                state["active"] -= 1
            return "answer"

    store = _seeded_store()
    experiment_id = _new_experiment(session_factory, "concurrent")
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=lambda *a, **kw: _SlowLLM(),
        embedder_factory=_embedder_factory,
    )
    questions = [QuestionItem(text=f"q{i}") for i in range(8)]

    run_experiment(experiment_id, _single_combo_config(4), questions, deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done"
    results = sorted(stored.runs[0].results, key=lambda r: r.id)
    assert [r.question for r in results] == [f"q{i}" for i in range(8)]
    assert state["peak"] > 1, "questions should overlap when concurrency > 1"
    assert state["peak"] <= 4
    check.close()


def test_pause_with_concurrency_stops_new_questions(session_factory):
    """A pause stops questions that have not started; in-flight ones are kept."""
    store = _seeded_store()
    experiment_id = _new_experiment(session_factory, "concurrent-pause")

    class _PausingLLM:
        def generate(self, prompt: str) -> str:
            request_pause(experiment_id)
            return "answer"

    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=lambda *a, **kw: _PausingLLM(),
        embedder_factory=_embedder_factory,
    )
    questions = [QuestionItem(text=f"q{i}") for i in range(10)]

    run_experiment(experiment_id, _single_combo_config(2), questions, deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "paused"
    assert 1 <= len(stored.runs[0].results) <= 2
    check.close()


def test_indexes_run_only_the_listed_pairs(session_factory):
    """Explicit index pairs replace the chunking x embedding cartesian product."""
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One. Two. Three. Four sentences here.")],
        IngestConfig(base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    experiment_id = _new_experiment(session_factory, "indexes")
    config = ExperimentConfig(
        llms=["gemini"],
        base="viagem",
        chunkings=["recursive", "token"],
        embeddings=["gemini", "e5"],
        indexes=[{"chunking": "recursive", "embedding": "gemini"}],
        rags=["naive"],
        retrievers=["similarity"],
        metrics=["answer_relevancy"],
    )
    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_embedder_factory,
    )

    run_experiment(experiment_id, config, [QuestionItem(text="q")], deps)

    check = session_factory()
    runs = check.get(Experiment, experiment_id).runs
    assert [(r.chunking, r.embedding) for r in runs] == [("recursive", "gemini")]
    check.close()


def _setup_two_llm_experiment(session_factory, name="llm-major", **config_overrides):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two here.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=["gemini"]),
        store,
        embedder_factory=_embedder_factory,
    )
    session = session_factory()
    experiment = Experiment(name=name, status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    config = ExperimentConfig(
        base="viagem", chunkings=["recursive"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity", "mmr"],
        metrics=["answer_relevancy"], llms=["gemini", "gemini-2.5-flash-lite"],
        **config_overrides,
    )
    return store, experiment_id, config


def test_runs_are_llm_major_and_each_llm_is_built_once(session_factory):
    store, experiment_id, config = _setup_two_llm_experiment(session_factory)
    built = []

    def llm_factory(name, **kwargs):
        built.append(name)
        return _FakeLLM()

    deps = ExperimentDeps(store=store, session_factory=session_factory,
                          llm_factory=llm_factory, embedder_factory=_embedder_factory)
    run_experiment(experiment_id, config, [QuestionItem(text="Where?")], deps)

    check = session_factory()
    runs = sorted(check.get(Experiment, experiment_id).runs, key=lambda r: r.id)
    assert [r.llm for r in runs] == ["gemini", "gemini", "gemini-2.5-flash-lite", "gemini-2.5-flash-lite"]
    assert built == ["gemini", "gemini-2.5-flash-lite"]
    check.close()


def test_embedders_load_once_per_experiment(session_factory):
    store, experiment_id, config = _setup_two_llm_experiment(session_factory)
    config.eval_embedding = "gemini"
    loads = []

    def embedder_factory(name, **kwargs):
        loads.append(name)
        return _FakeEmbedder()

    deps = ExperimentDeps(store=store, session_factory=session_factory,
                          llm_factory=_llm_factory, embedder_factory=embedder_factory)
    run_experiment(experiment_id, config, [QuestionItem(text="Where?")], deps)
    assert loads == ["gemini"]  # eval and retrieval share one instance


def test_concurrency_is_capped_by_the_profile(session_factory, monkeypatch):
    from app.core.config.settings import get_settings
    from app.experiments import orchestrator

    monkeypatch.setenv("MEMORY_PROFILE", "low")
    get_settings.cache_clear()
    store, experiment_id, config = _setup_two_llm_experiment(session_factory, concurrency=8)
    seen = []
    real = orchestrator._run_questions

    def spy(rag, questions, metrics, eval_embedder, concurrency, exp_id, combo, tracker):
        seen.append(concurrency)
        return real(rag, questions, metrics, eval_embedder, concurrency, exp_id, combo, tracker)

    monkeypatch.setattr(orchestrator, "_run_questions", spy)
    deps = ExperimentDeps(store=store, session_factory=session_factory,
                          llm_factory=_llm_factory, embedder_factory=_embedder_factory)
    try:
        run_experiment(experiment_id, config, [QuestionItem(text="Where?")], deps)
    finally:
        get_settings.cache_clear()
    assert seen and set(seen) == {2}


def test_experiments_run_one_at_a_time(session_factory, monkeypatch):
    import threading
    import time

    from app.experiments import orchestrator

    active, peak, lock = [0], [0], threading.Lock()
    real = orchestrator._run_experiment

    def tracked(*args, **kwargs):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            time.sleep(0.05)
            return real(*args, **kwargs)
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(orchestrator, "_run_experiment", tracked)
    jobs = []
    for i in range(2):
        store, experiment_id, config = _setup_two_llm_experiment(session_factory, name=f"exp-{i}")
        deps = ExperimentDeps(store=store, session_factory=session_factory,
                              llm_factory=_llm_factory, embedder_factory=_embedder_factory)
        jobs.append(threading.Thread(target=run_experiment,
                                     args=(experiment_id, config, [QuestionItem(text="Q?")], deps)))
    for job in jobs:
        job.start()
    for job in jobs:
        job.join(10)
    assert peak[0] == 1


class _EventLLM:
    def __init__(self, events):
        self._events = events

    def generate(self, prompt):
        self._events.append("gen")
        return "Resposta gerada."


def _staged_deps(store, session_factory, events, max_local=1):
    from app.core.memory.manager import ModelManager

    def factory(name, **kwargs):
        events.append(f"load:{name}")
        return _FakeEmbedder()

    models = ModelManager(factory, max_local=max_local, is_local=lambda n: n in {"e5", "paraphrase"},
                          on_evict=lambda: events.append("evict"))
    return ExperimentDeps(store=store, session_factory=session_factory,
                          llm_factory=lambda name, **kw: _EventLLM(events), models=models)


def _indexed_store(embedding):
    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="Para one.\n\nPara two here.")],
        IngestConfig(base="viagem", chunkings=["recursive"], embeddings=[embedding]),
        store, embedder_factory=_embedder_factory,
    )
    return store


def _new_experiment(session_factory, name):
    session = session_factory()
    experiment = Experiment(name=name, status="pending", config={})
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    return experiment_id


def _staged_config(**kw):
    base = dict(base="viagem", chunkings=["recursive"], embeddings=["e5"], rags=["naive"],
                retrievers=["similarity"], metrics=["answer_relevancy"], llms=["qwen3:1.7b"],
                eval_embedding="e5")
    return ExperimentConfig(**{**base, **kw})


def _results(session_factory, experiment_id):
    check = session_factory()
    experiment = check.get(Experiment, experiment_id)
    rows = [r for run in experiment.runs for r in run.results]
    status = experiment.status
    config = dict(experiment.config)
    check.close()
    return status, rows, config


def test_staged_run_keeps_embedders_out_of_memory_while_generating(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "staged-1")
    run_experiment(experiment_id, _staged_config(),
                   [QuestionItem(text="Where?"), QuestionItem(text="When?")],
                   _staged_deps(store, session_factory, events))
    first_gen = events.index("gen")
    last_gen = len(events) - 1 - events[::-1].index("gen")
    assert "load:e5" in events[:first_gen]                               # A: question vectors
    assert "evict" in events[events.index("load:e5"):first_gen]          # freed before the LLM
    assert not any(e.startswith("load:") for e in events[first_gen:last_gen])  # B: nothing loads
    assert "load:e5" in events[last_gen:]                                # C: eval embedder
    status, rows, config = _results(session_factory, experiment_id)
    assert status == "done" and "phase" not in config
    assert len(rows) == 2 and all("answer_relevancy" in r.scores for r in rows)


def test_staged_hyde_loads_the_embedder_only_for_generated_text(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "staged-hyde")
    run_experiment(experiment_id, _staged_config(rags=["hyde"], metrics=["rouge_l"]),
                   [QuestionItem(text="Where?", reference="Aqui.")],
                   _staged_deps(store, session_factory, events))
    first_gen = events.index("gen")
    assert [e for e in events[first_gen:] if e.startswith("load:")] == ["load:e5"]  # HyDE miss only
    _, [row], _ = _results(session_factory, experiment_id)
    assert "rouge_l" in row.scores  # rouge_l needs no embedder: stage C loaded nothing


def test_staged_scores_gold_metrics_from_stored_evidence(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "staged-gold")
    run_experiment(experiment_id, _staged_config(metrics=["context_hit", "context_mrr"]),
                   [QuestionItem(text="Where?", evidence=["Para two here."])],
                   _staged_deps(store, session_factory, events))
    _, [row], _ = _results(session_factory, experiment_id)
    assert row.reference_contexts == ["Para two here."]
    assert row.scores["context_hit"] == 1.0 and row.scores["context_mrr"] > 0


def test_staged_skips_failed_questions_when_scoring(session_factory, monkeypatch):
    from app.experiments import orchestrator

    monkeypatch.setattr(orchestrator, "_RETRY_DELAY_S", 0)
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "staged-err")
    deps = _staged_deps(store, session_factory, events)

    class _Flaky:
        def generate(self, prompt):
            if "Boom" in prompt:
                raise RuntimeError("LLM down")
            return "ok"

    deps.llm_factory = lambda name, **kw: _Flaky()
    run_experiment(experiment_id, _staged_config(),
                   [QuestionItem(text="Boom?"), QuestionItem(text="Fine?")], deps)
    _, rows, _ = _results(session_factory, experiment_id)
    by_q = {r.question: r for r in rows}
    assert by_q["Boom?"].generated_answer.startswith("[ERRO: ") and by_q["Boom?"].scores == {}
    assert "answer_relevancy" in by_q["Fine?"].scores


def test_paused_staged_run_still_scores_what_it_generated(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "staged-pause")
    deps = _staged_deps(store, session_factory, events)

    class _PausingLLM:
        def generate(self, prompt):
            request_pause(experiment_id)
            return "ok"

    deps.llm_factory = lambda name, **kw: _PausingLLM()
    run_experiment(experiment_id, _staged_config(retrievers=["similarity", "mmr"]),
                   [QuestionItem(text="Where?")], deps)
    status, rows, _ = _results(session_factory, experiment_id)
    assert status == "paused" and len(rows) == 1
    assert "answer_relevancy" in rows[0].scores


def test_unstaged_run_holds_the_retrieval_embedder_across_runs(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "unstaged")
    run_experiment(
        experiment_id,
        _staged_config(staged=False, retrievers=["similarity", "mmr"], eval_embedding="paraphrase"),
        [QuestionItem(text="Where?")], _staged_deps(store, session_factory, events),
    )
    assert events.count("load:e5") == 1  # not reloaded for the second retriever


def test_closed_book_runs_once_per_llm_across_indexes_and_retrievers(session_factory):
    from app.experiments.schemas import combinations, combination_count

    config = _staged_config(rags=["naive", "closed_book"], retrievers=["similarity", "mmr"],
                            llms=["qwen3:1.7b", "gemini"], metrics=["rouge_l"])
    runs = list(combinations(config))
    closed = [r for r in runs if r[2] == "closed_book"]
    assert [r[0] for r in closed] == ["qwen3:1.7b", "gemini"]
    assert combination_count(config) == len(runs) == 2 * (2 + 1)


def test_run_stores_question_profiles_and_retrieval_signals(session_factory):
    from app.core.db.models import QuestionProfile, RunResult

    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "difficulty")
    run_experiment(experiment_id, _staged_config(rags=["naive", "closed_book"], metrics=["rouge_l"]),
                   [QuestionItem(text="Where is para two?", reference="Aqui.")],
                   _staged_deps(store, session_factory, events))
    check = session_factory()
    results = {r.run.rag_technique: r for r in check.query(RunResult).all()}
    assert set(results["naive"].retrieval_signals) == {"top_score", "score_gap", "score_spread"}
    assert results["closed_book"].retrieval_signals == {}
    assert results["closed_book"].retrieved_context == []
    [profile] = check.query(QuestionProfile).filter_by(experiment_id=experiment_id).all()
    assert profile.question == "Where is para two?"
    assert {"question_length", "mean_idf", "out_of_corpus"} <= set(profile.signals)
    check.close()


def test_oracle_runs_once_per_llm_on_questions_with_evidence(session_factory):
    from app.core.db.models import RunResult

    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "oracle")
    run_experiment(
        experiment_id,
        _staged_config(rags=["oracle"], retrievers=["similarity", "mmr"], metrics=["rouge_l"]),
        [QuestionItem(text="Com evidência?", reference="Aqui.", evidence=["Para two here."]),
         QuestionItem(text="Sem evidência?", reference="Aqui.")],
        _staged_deps(store, session_factory, events),
    )
    check = session_factory()
    [row] = check.query(RunResult).all()
    assert row.question == "Com evidência?"
    assert row.retrieved_context == [{"text": "Para two here.", "source": "oracle"}]
    assert row.retrieval_signals == {}
    check.close()


def test_profiles_get_evidence_signals_and_distance(session_factory):
    from app.core.db.models import QuestionProfile

    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "evidence-signals")
    run_experiment(experiment_id, _staged_config(metrics=["rouge_l"]),
                   [QuestionItem(text="Where?", reference="Aqui.", evidence=["Para two here."]),
                    QuestionItem(text="When?", reference="Agora.")],
                   _staged_deps(store, session_factory, events))
    check = session_factory()
    profiles = {p.question: p.signals for p in check.query(QuestionProfile).all()}
    check.close()
    assert profiles["Where?"]["evidence_count"] == 1.0
    assert 0.0 <= profiles["Where?"]["evidence_distance"] <= 2.0
    assert "evidence_count" not in profiles["When?"]
    assert "evidence_distance" not in profiles["When?"]
    assert "load:e5" in events[events.index("gen"):]  # distance uses the eval embedder after generation


def test_perplexity_is_scored_once_per_llm_not_per_combination(session_factory):
    from app.core.db.models import QuestionProfile
    from app.core.difficulty import perplexity

    perplexity._cache.clear()
    calls = []

    class _Scorer:
        def score(self, model, questions):
            calls.append((model, list(questions)))
            return {q: 10.0 + len(q) for q in questions}

    events = []
    store = _indexed_store("e5")
    deps = _staged_deps(store, session_factory, events)
    deps.perplexity_scorer_factory = lambda model: _Scorer() if "/" in model else None
    experiment_id = _new_experiment(session_factory, "perplexity")
    run_experiment(
        experiment_id,
        _staged_config(rags=["naive", "closed_book"], retrievers=["similarity", "mmr"],
                       llms=["org/small-4bit", "qwen3:1.7b", "gemini"], metrics=["rouge_l"]),
        [QuestionItem(text="Where?"), QuestionItem(text="When?"), QuestionItem(text="Where?")],
        deps,
    )
    assert calls == [("org/small-4bit", ["Where?", "When?"])]
    check = session_factory()
    profiles = {p.question: p.model_signals for p in check.query(QuestionProfile).all()}
    check.close()
    assert profiles["Where?"] == {"org/small-4bit": {"perplexity": 16.0}}


def test_skipped_perplexity_is_recorded_for_the_ui(session_factory):
    from app.core.difficulty import perplexity

    perplexity._cache.clear()

    class _NoMemory:
        def score(self, model, questions):
            raise perplexity.PerplexitySkipped(1107, 2178)

    store = _indexed_store("e5")
    deps = _staged_deps(store, session_factory, [])
    deps.perplexity_scorer_factory = lambda model: _NoMemory()
    experiment_id = _new_experiment(session_factory, "perplexity-skipped")
    run_experiment(experiment_id, _staged_config(llms=["org/small-4bit"], metrics=["rouge_l"]),
                   [QuestionItem(text="Where?")], deps)
    status, _, config = _results(session_factory, experiment_id)
    assert status == "done"
    assert config["perplexity_skipped"] == {"org/small-4bit": {"free_mb": 1107, "needed_mb": 2178}}


_ABSENT = "Um trecho que não está em parte alguma da base indexada."


def _all_hops_score(session_factory, evidence, hops, staged=True, rag="naive"):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, f"all-hops-{rag}-{staged}-{hops}")
    run_experiment(
        experiment_id,
        _staged_config(metrics=["context_all_hops", "context_hit"], rags=[rag], staged=staged),
        [QuestionItem(text="Where?", evidence=evidence, evidence_hops=hops)],
        _staged_deps(store, session_factory, events),
    )
    _, [row], _ = _results(session_factory, experiment_id)
    return row.scores


@pytest.mark.parametrize("staged", [True, False])
@pytest.mark.parametrize(
    "evidence, hops, expected",
    [
        (["Para one.", "Para two here."], [1, 2], 1.0),      # every hop retrieved
        (["Para one.", _ABSENT], [1, 2], 0.0),               # hop 2 missing
        (["Para one.", _ABSENT, "Para two here."], [1, 2, 2], 1.0),  # one alternative suffices
        ([_ABSENT, _ABSENT + " Outro."], [1, 1], 0.0),        # one hop, nothing found
    ],
)
def test_context_all_hops_needs_every_hop_retrieved(session_factory, staged, evidence, hops, expected):
    scores = _all_hops_score(session_factory, evidence, hops, staged=staged)
    assert scores["context_all_hops"] == expected


@pytest.mark.parametrize("evidence", [["Para two here."], [_ABSENT], [_ABSENT, "Para one."]])
def test_context_all_hops_equals_context_hit_on_a_single_hop(session_factory, evidence):
    scores = _all_hops_score(session_factory, evidence, None)
    assert scores["context_all_hops"] == scores["context_hit"]


def test_context_all_hops_is_skipped_when_nothing_is_retrieved(session_factory):
    scores = _all_hops_score(session_factory, ["Para one."], [1], rag="closed_book")
    assert "context_all_hops" not in scores


# ---- Registro de pausa (issue #16): the reusable "pause now, with reason and
# details" primitives #19 (Falhas consecutivas) and #20 (Travamento) will reuse.

def test_in_flight_tracker_tracks_and_clears_questions():
    from app.experiments.orchestrator import _InFlightTracker

    tracker = _InFlightTracker()
    combo = {"chunking": "recursive", "embedding": "e5", "rag": "naive",
             "retriever": "similarity", "llm": "qwen3:1.7b"}

    token_a = tracker.start(combo, "Onde fica?")
    token_b = tracker.start(combo, "Quando é?")
    assert {item["question"] for item in tracker.snapshot()} == {"Onde fica?", "Quando é?"}

    tracker.finish(token_a)
    [remaining] = tracker.snapshot()
    assert remaining == {**combo, "question": "Quando é?"}

    tracker.finish(token_b)
    assert tracker.snapshot() == []


def test_record_pause_appends_a_registro_entry(session_factory):
    from app.experiments.orchestrator import record_pause

    session = session_factory()
    experiment = Experiment(name="rp", status="running", config={"phase": "generating"})
    session.add(experiment)
    session.commit()

    record_pause(
        session, experiment,
        reason="stall", phase="generating",
        in_flight=[{"question": "Onde fica?"}],
        last_error={"message": "timeout", "traceback": "Traceback (most recent call last)..."},
    )

    assert len(experiment.pauses) == 1
    entry = experiment.pauses[0]
    assert entry["reason"] == "stall"
    assert entry["phase"] == "generating"
    assert entry["in_flight"] == [{"question": "Onde fica?"}]
    assert entry["last_error"]["message"] == "timeout"
    assert entry["resumed_at"] is None
    assert set(entry["memory"]) == {"free_mb", "api_mb"}

    # A second entry appends, it never replaces the Registro's history.
    record_pause(session, experiment, reason="manual", phase=None)
    assert [e["reason"] for e in experiment.pauses] == ["stall", "manual"]
    session.close()


def test_pause_now_path_skips_scoring_and_records_the_given_reason(session_factory, monkeypatch):
    """The internal 'pause now, without scoring' path #19/#20 will trigger for real.

    Unlike a manual Pausa, this one must not run the scoring (or difficulty-signal)
    stage at all: the whole point is freeing the machine right away.
    """
    from app.experiments import orchestrator

    scored = []
    monkeypatch.setattr(orchestrator, "_score_results", lambda *a, **kw: scored.append(True))

    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "stop-now")
    deps = _staged_deps(store, session_factory, events)

    class _StallingLLM:
        """Simulates #19/#20 requesting an immediate, reasoned pause mid-generation."""

        def generate(self, prompt: str) -> str:
            orchestrator.request_pause(
                experiment_id, reason="consecutive_failures", score_partial=False,
                detail={"message": "LLM indisponível", "traceback": "Traceback..."},
            )
            return "ok"

    deps.llm_factory = lambda name, **kw: _StallingLLM()
    run_experiment(
        experiment_id, _staged_config(),
        [QuestionItem(text="Where?"), QuestionItem(text="When?")], deps,
    )

    status, rows, _ = _results(session_factory, experiment_id)
    assert status == "paused"
    assert scored == [], "scoring must not run on an immediate, unscored pause"
    assert len(rows) == 1 and rows[0].scores == {}

    check = session_factory()
    [entry] = check.get(Experiment, experiment_id).pauses
    check.close()
    assert entry["reason"] == "consecutive_failures"
    assert entry["last_error"]["message"] == "LLM indisponível"
    assert entry["resumed_at"] is None


def test_failed_experiment_records_a_failed_pause_entry(session_factory):
    """An uncaught exception still keeps config['error'] (compatibility) and now
    also appends a `failed` entry to the Registro de pausa."""
    store = _seeded_store()
    experiment_id = _new_experiment(session_factory, "boom")

    def _broken_embedder_factory(name, **kwargs):
        raise RuntimeError("embedder indisponível")

    deps = ExperimentDeps(
        store=store,
        session_factory=session_factory,
        llm_factory=_llm_factory,
        embedder_factory=_broken_embedder_factory,
    )

    run_experiment(experiment_id, _single_combo_config(1), [QuestionItem(text="q")], deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "failed"
    assert stored.config["error"] == "embedder indisponível"
    [entry] = stored.pauses
    assert entry["reason"] == "failed"
    assert entry["last_error"]["message"] == "embedder indisponível"
    assert "Traceback" in entry["last_error"]["traceback"]
    check.close()


# ---- Retomada (issue #17): resume_experiment reads config/questions back from the
# database and reuses _run_experiment's loop (skip done, reuse paused/running, create
# what never ran).

def _experiment_for_resume(
    session_factory, name: str, config: ExperimentConfig, questions: list[QuestionItem],
    status: str = "paused",
) -> int:
    """An Experiment row with its config and questions recorded, as #16's API does."""
    session = session_factory()
    experiment = Experiment(
        name=name, status=status,
        config=config.model_dump(),
        questions=[q.model_dump() for q in questions],
    )
    session.add(experiment)
    session.commit()
    experiment_id = experiment.id
    session.close()
    return experiment_id


def test_resume_runs_only_missing_questions_in_the_same_run(session_factory):
    """A run paused mid-way keeps its valid result and only the missing question runs."""
    from app.core.db.models import ExperimentRun, RunResult

    store = _seeded_store()
    config = _single_combo_config(1)
    questions = [QuestionItem(text="q1"), QuestionItem(text="q2")]
    experiment_id = _experiment_for_resume(session_factory, "resume-basic", config, questions)

    session = session_factory()
    run = ExperimentRun(
        experiment_id=experiment_id, chunking="recursive", embedding="gemini",
        rag_technique="naive", retriever="similarity", llm="gemini", status="paused",
    )
    run.results = [
        RunResult(question="q1", generated_answer="Resposta antiga.",
                  scores={"answer_relevancy": 1.0}, latency_ms=5, tokens=3),
    ]
    session.add(run)
    session.commit()
    session.close()

    deps = ExperimentDeps(
        store=store, session_factory=session_factory,
        llm_factory=_llm_factory, embedder_factory=_embedder_factory,
    )
    resume_experiment(experiment_id, deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done"
    [run] = stored.runs
    assert run.status == "done"
    by_q = {r.question: r for r in run.results}
    assert set(by_q) == {"q1", "q2"}
    assert by_q["q1"].generated_answer == "Resposta antiga."  # never reprocessed
    assert by_q["q2"].generated_answer == "The center is around the main square."
    check.close()


def test_resume_reruns_error_rows_but_keeps_valid_answers(session_factory):
    """[ERRO] rows are deleted and redone; a valid answer is never redone."""
    from app.core.db.models import ExperimentRun, RunResult

    store = _seeded_store()
    config = _single_combo_config(1)
    questions = [QuestionItem(text="q1"), QuestionItem(text="q2")]
    experiment_id = _experiment_for_resume(
        session_factory, "resume-errors", config, questions, status="failed"
    )

    session = session_factory()
    run = ExperimentRun(
        experiment_id=experiment_id, chunking="recursive", embedding="gemini",
        rag_technique="naive", retriever="similarity", llm="gemini", status="running",
    )
    run.results = [
        RunResult(question="q1", generated_answer="Resposta boa.",
                  scores={"answer_relevancy": 1.0}, latency_ms=5, tokens=3),
        RunResult(question="q2", generated_answer="[ERRO: 503 UNAVAILABLE]",
                  scores={}, latency_ms=0, tokens=0),
    ]
    session.add(run)
    session.commit()
    session.close()

    deps = ExperimentDeps(
        store=store, session_factory=session_factory,
        llm_factory=_llm_factory, embedder_factory=_embedder_factory,
    )
    resume_experiment(experiment_id, deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done"
    [run] = stored.runs
    assert len(run.results) == 2  # one row per question, no duplicates
    by_q = {r.question: r for r in run.results}
    assert by_q["q1"].generated_answer == "Resposta boa."
    assert by_q["q2"].generated_answer == "The center is around the main square."
    check.close()


def test_resume_combination_matrix_done_paused_and_missing(session_factory):
    """done is skipped untouched; paused is reused; a combination with no run is created."""
    from app.core.db.models import ExperimentRun, RunResult

    store = QdrantStore(client=QdrantClient(":memory:"))
    ingest_documents(
        [Document(name="a.txt", text="One. Two. Three. Four sentences here.")],
        IngestConfig(base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"]),
        store, embedder_factory=_embedder_factory,
    )
    config = ExperimentConfig(
        llms=["gemini"], base="viagem", chunkings=["recursive", "token"], embeddings=["gemini"],
        rags=["naive"], retrievers=["similarity"], metrics=["answer_relevancy"],
    )
    questions = [QuestionItem(text="q1")]
    experiment_id = _experiment_for_resume(session_factory, "resume-matrix", config, questions)

    session = session_factory()
    done_run = ExperimentRun(
        experiment_id=experiment_id, chunking="recursive", embedding="gemini",
        rag_technique="naive", retriever="similarity", llm="gemini", status="done",
    )
    done_run.results = [
        RunResult(question="q1", generated_answer="Já pronta.",
                  scores={"answer_relevancy": 1.0}, latency_ms=5, tokens=3),
    ]
    session.add(done_run)
    session.commit()
    session.close()

    deps = ExperimentDeps(
        store=store, session_factory=session_factory,
        llm_factory=_llm_factory, embedder_factory=_embedder_factory,
    )
    resume_experiment(experiment_id, deps)

    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done"
    runs = {r.chunking: r for r in stored.runs}
    assert set(runs) == {"recursive", "token"}
    assert runs["recursive"].status == "done"
    assert [r.generated_answer for r in runs["recursive"].results] == ["Já pronta."]
    assert runs["token"].status == "done"
    assert [r.question for r in runs["token"].results] == ["q1"]
    check.close()


def test_resume_sets_resumed_at_on_the_latest_pause_entry(session_factory):
    store = _seeded_store()
    config = _single_combo_config(1)
    questions = [QuestionItem(text="q1")]
    experiment_id = _experiment_for_resume(session_factory, "resume-pauses", config, questions)

    session = session_factory()
    experiment = session.get(Experiment, experiment_id)
    experiment.pauses = [
        {"paused_at": "2026-01-01T00:00:00+00:00", "reason": "manual", "phase": "generating",
         "in_flight": [], "last_error": None, "memory": {"free_mb": 1, "api_mb": 1},
         "resumed_at": None},
    ]
    session.commit()
    session.close()

    deps = ExperimentDeps(
        store=store, session_factory=session_factory,
        llm_factory=_llm_factory, embedder_factory=_embedder_factory,
    )
    resume_experiment(experiment_id, deps)

    check = session_factory()
    [entry] = check.get(Experiment, experiment_id).pauses
    assert entry["resumed_at"] is not None
    check.close()


def test_resume_handles_several_pause_resume_cycles(session_factory):
    """Pausing twice and resuming twice still ends with one row per question."""
    store = _seeded_store()
    config = _single_combo_config(1)
    questions = [QuestionItem(text=f"q{i}") for i in range(4)]
    experiment_id = _experiment_for_resume(session_factory, "resume-cycles", config, questions)

    calls = {"n": 0}
    pause_on = {1, 2}

    class _TwicePausingLLM:
        def generate(self, prompt: str) -> str:
            calls["n"] += 1
            if calls["n"] in pause_on:
                request_pause(experiment_id)
            return "answer"

    deps = ExperimentDeps(
        store=store, session_factory=session_factory,
        llm_factory=lambda *a, **kw: _TwicePausingLLM(),
        embedder_factory=_embedder_factory,
    )

    run_experiment(experiment_id, config, questions, deps)
    check = session_factory()
    assert check.get(Experiment, experiment_id).status == "paused"
    check.close()

    resume_experiment(experiment_id, deps)
    check = session_factory()
    assert check.get(Experiment, experiment_id).status == "paused"
    check.close()

    resume_experiment(experiment_id, deps)
    check = session_factory()
    stored = check.get(Experiment, experiment_id)
    assert stored.status == "done"
    [run] = stored.runs
    assert sorted(r.question for r in run.results) == ["q0", "q1", "q2", "q3"]
    assert all(r.generated_answer == "answer" for r in run.results)
    check.close()

