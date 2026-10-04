"""Building the Grafo de conhecimento as a background job: cache, progress, pause, memory.

Driven through GraphBuilds (create + run) with a fake LLM extrator that counts
extraction calls, Qdrant :memory: and SQLite (no network, no Postgres).
"""
from qdrant_client import QdrantClient

from app.core.graph.build import current_graph
from app.core.graph.jobs import GraphBuildDeps, GraphBuilds
from app.core.memory.manager import ModelManager
from app.core.vectorstore.qdrant import QdrantStore, collection_name
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig
from tests.test_orchestrator import _FakeEmbedder, _embedder_factory, session_factory  # noqa: F401

_REPLY = "entidade<|>Praça Central<|>lugar<|>Praça no centro.\n<|FIM|>"
_DOC = "\n\n".join(f"Parágrafo {i}: " + "texto " * 150 for i in range(3))  # 3 chunks
_EXTRACTOR = "qwen3:1.7b"


class _CountingLLM:
    """Answers extraction prompts with one entity and records each one."""

    def __init__(self, calls, on_extract=None, events=None):
        self.calls = calls
        self._on_extract = on_extract
        self._events = events

    def generate(self, prompt):
        assert prompt.startswith("Extraia do texto")
        self.calls.append(prompt)
        if self._events is not None:
            self._events.append("extract")
        if self._on_extract:
            self._on_extract(len(self.calls))
        return _REPLY


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
    def factory(name, **kwargs):
        if events is not None:
            events.append(f"load:{name}")
        return _FakeEmbedder()

    models = ModelManager(
        factory, max_local=1, is_local=lambda n: n in {"e5", "paraphrase"},
        on_evict=(lambda: events.append("evict")) if events is not None else (lambda: None),
    )
    return GraphBuildDeps(
        store=store, session_factory=session_factory, models=models,
        llm_factory=lambda name, **kw: _CountingLLM(calls, on_extract, events), max_concurrency=1,
    )


def _build(deps, indexes=(("recursive", "e5"),), prompt=None, builds=None):
    builds = builds or GraphBuilds()
    job = builds.create("viagem", _EXTRACTOR, list(indexes), prompt=prompt)
    builds.run(job.id, deps)
    return builds, builds.get(job.id)


def test_a_job_builds_each_indexs_grafo_once_per_chunk(session_factory):  # noqa: F811
    store, calls = _store(), []
    _, job = _build(_deps(store, session_factory, calls))
    assert job.status == "done"
    [item] = job.indexes
    assert (item.status, item.extracted, item.total) == ("done", 3, 3)
    assert item.stats["entities"] == 1
    assert len(calls) == len(_chunks(store))
    graph = current_graph(store, "viagem", "recursive", "e5", _EXTRACTOR)
    assert graph is not None and graph.extractor == _EXTRACTOR


def test_a_second_job_on_a_current_grafo_does_not_call_the_extractor(session_factory):  # noqa: F811
    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _build(deps)
    _, job = _build(deps)
    assert job.status == "done" and job.indexes[0].stats["entities"] == 1
    assert len(calls) == len(_chunks(store))  # no new extraction


def test_the_same_chunking_with_another_embedding_reuses_the_extraction(
    session_factory,  # noqa: F811
):
    store, calls = _store(("e5", "paraphrase")), []
    _, job = _build(_deps(store, session_factory, calls),
                    indexes=[("recursive", "e5"), ("recursive", "paraphrase")])
    assert job.status == "done"
    # Both Índices got their own Grafo, from one extraction per chunk.
    assert [i.stats["entities"] for i in job.indexes] == [1, 1]
    assert len(calls) == len(_chunks(store))


def test_changing_the_extraction_prompt_invalidates_the_cache(session_factory):  # noqa: F811
    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _build(deps, prompt="Extraia do texto v1: {text}")
    _build(deps, prompt="Extraia do texto v1: {text}")
    assert len(calls) == len(_chunks(store))

    _build(deps, prompt="Extraia do texto v2: {text}")
    assert len(calls) == 2 * len(_chunks(store))
    assert all(c.startswith("Extraia do texto v2") for c in calls[len(_chunks(store)):])


def test_reingesting_the_index_rebuilds_the_grafo_on_the_new_chunks(session_factory):  # noqa: F811
    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _build(deps)

    store.delete_collection(collection_name("viagem", "recursive", "e5"))
    _store(text="Praça Central fica no centro.", store=store)
    [new_chunk] = [c["payload"]["text"] for c in _chunks(store)]
    _, job = _build(deps)
    assert job.status == "done" and job.indexes[0].stats["chunks"] == 1
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
    _, job = _build(_deps(store, session_factory, calls), indexes=[("markdown", "e5")])
    assert job.status == "done" and job.indexes[0].stats["entities"] == 1
    [prompt] = calls
    assert "Texto: A Praça Central fica no centro." in prompt
    assert "Guia da cidade" not in prompt and "Perguntas frequentes" not in prompt


def test_a_chunk_of_headings_only_is_not_sent_to_the_extractor(session_factory):  # noqa: F811
    # The paragraph fills a recursive chunk, so the title is cut off on its own.
    store, calls = _store(text="# Guia da cidade\n\n" + "A praça fica no centro. " * 41), []
    assert "# Guia da cidade" in [c["payload"]["text"] for c in _chunks(store)]

    _, job = _build(_deps(store, session_factory, calls))
    assert job.status == "done" and job.indexes[0].stats["chunks"] == len(_chunks(store))
    assert len(calls) == len(_chunks(store)) - 1


def test_a_grafo_built_by_an_older_version_is_rebuilt_from_the_cache(
    session_factory, monkeypatch,  # noqa: F811
):
    from app.core.graph import build, jobs

    store, calls = _store(), []
    deps = _deps(store, session_factory, calls)
    _build(deps)
    seen = []
    monkeypatch.setattr(build, "GRAPH_VERSION", build.GRAPH_VERSION + 1)
    monkeypatch.setattr(jobs, "build_graph", lambda *a, **kw: seen.append(1) or
                        build.build_graph(*a, **kw))

    _, job = _build(deps)
    assert job.status == "done" and job.indexes[0].stats["entities"] == 1
    # Rebuilt, but the extractions still hold: no new LLM call.
    assert seen == [1]
    assert len(calls) == len(_chunks(store))


def test_the_job_reports_chunks_extracted_while_it_builds(session_factory):  # noqa: F811
    seen = []
    builds = GraphBuilds()

    def on_extract(n):
        job = builds.get(job_id)
        seen.append((job.status, job.indexes[0].status, job.indexes[0].extracted,
                     job.indexes[0].total))

    store, calls = _store(), []
    total = len(_chunks(store))
    job_id = builds.create("viagem", _EXTRACTOR, [("recursive", "e5")]).id
    assert builds.get(job_id).status == "pending"
    builds.run(job_id, _deps(store, session_factory, calls, on_extract))
    # Seen while extracting chunk n: the n-1 before it are done.
    assert seen == [("running", "building", n, total) for n in range(total)]
    assert builds.get(job_id).status == "done"


def test_a_pause_during_the_build_resumes_without_reextracting(session_factory):  # noqa: F811
    builds = GraphBuilds()
    store, calls = _store(), []
    total = len(_chunks(store))
    job_id = builds.create("viagem", _EXTRACTOR, [("recursive", "e5")]).id
    deps = _deps(store, session_factory, calls,
                 on_extract=lambda n: n == 1 and builds.request_pause(job_id))
    builds.run(job_id, deps)
    job = builds.get(job_id)
    assert (job.status, job.indexes[0].status) == ("paused", "pending")
    assert len(calls) == 1
    assert current_graph(store, "viagem", "recursive", "e5", _EXTRACTOR) is None

    builds.resume(job_id)
    assert builds.get(job_id).status == "pending"
    builds.run(job_id, _deps(store, session_factory, calls))
    job = builds.get(job_id)
    assert (job.status, job.indexes[0].stats["chunks"]) == ("done", total)
    assert len(calls) == total  # the first chunk was not asked again


def test_a_pause_before_the_job_starts_leaves_it_paused(session_factory):  # noqa: F811
    builds = GraphBuilds()
    store, calls = _store(), []
    job_id = builds.create("viagem", _EXTRACTOR, [("recursive", "e5")]).id
    builds.request_pause(job_id)
    builds.run(job_id, _deps(store, session_factory, calls))
    assert builds.get(job_id).status == "paused" and calls == []


def test_an_index_that_cannot_be_built_fails_alone(session_factory):  # noqa: F811
    store, calls = _store(), []
    _, job = _build(_deps(store, session_factory, calls),
                    indexes=[("fixed", "e5"), ("recursive", "e5")])
    assert job.status == "failed"
    failed, done = job.indexes
    assert failed.status == "failed" and failed.error
    assert done.status == "done"


def test_low_profile_never_holds_the_extractor_and_the_embedder_together(
    session_factory, monkeypatch,  # noqa: F811
):
    from app.core.llm import ollama

    events, calls = [], []
    monkeypatch.setattr(ollama, "unload_local_llm", lambda name, *a, **k: events.append("unload"))
    store = _store()
    _, job = _build(_deps(store, session_factory, calls, events=events))
    assert job.status == "done"
    first, last = events.index("extract"), len(events) - 1 - events[::-1].index("extract")
    write = events.index("load:e5", last)
    assert not any(e.startswith("load:") for e in events[first:last])  # extraction: LLM only
    assert "unload" in events[last:write]                               # LLM out before embedder
    assert "evict" in events[write:]                                    # embedder out at the end
