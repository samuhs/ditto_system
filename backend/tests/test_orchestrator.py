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

    def spy(rag, questions, metrics, eval_embedder, concurrency, exp_id):
        seen.append(concurrency)
        return real(rag, questions, metrics, eval_embedder, concurrency, exp_id)

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
