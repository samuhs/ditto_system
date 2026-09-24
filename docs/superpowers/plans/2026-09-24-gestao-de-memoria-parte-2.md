# Gestão de memória, parte 2: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One model in memory at a time during experiments (staged execution, spec 3.4), the Phase 4 code polish, and the three minors deferred from part 1.

**Architecture:** An experiment runs in three stages. **A** embeds every question once per retrieval embedding and caches the vectors, then unloads the embedder. **B** generates the answers LLM by LLM. Retrievers get a `CachedQueryEmbedder` that answers from the cache, and it loads the real embedder only on a miss (text the LLM generated: HyDE, multi-query, CRAG/agentic rewrites). **C** asks the local LLM server to unload, loads the eval embedder once and scores every stored result. The `ModelManager` loads models outside its lock, takes a per-call wait timeout, and can evict idle models. `staged=false` keeps the one-pass path, which now holds each retrieval embedder across consecutive combinations.

**Tech Stack:** FastAPI, SQLAlchemy, sentence-transformers (optional), httpx, qdrant-client, React + vitest.

**Spec:** `docs/superpowers/specs/2026-09-24-gestao-de-memoria-design.md` (Phase 3.4, Phase 4, decisions in section 5).

## Global Constraints

- Identifiers, docstrings and errors in English; UI text in PT-BR.
- Tests never touch the network, Postgres or a real LLM server.
- Staged execution is the default in both profiles (`staged: bool = True` on `ExperimentConfig`); `staged=false` is the escape hatch.
- The embedder never shares the GPU with a local LLM: stage B embeds on the device `resolve_embedding_device(profile, config.llms)` picks (CPU with a local LLM).
- Scores must stay identical to part 1 for the same inputs: metrics keep using `embed_query` (Gemini distinguishes query from document embeddings).
- Qdrant `on_disk` (spec Phase 4) is out: part 1 measured ~300 MB and raised the limit instead.

## Review Focus

1. A question fails in stage B (`[ERRO: ...]` row) → stage C skips it and leaves `scores == {}`; the rest still get scored.
2. An experiment is paused in stage B → stage C still scores what was generated, and the status ends `paused`.
3. Metrics that need no embedder (only `rouge_l`) → stage C never loads an eval embedder.
4. A model load that raises inside the manager (outside the lock now) → the placeholder is removed, waiters wake up and re-raise or retry, and no slot leaks.
5. Two threads ask for the same model while it is loading → it loads once; the second waits for the first.

---

### Task 1: ModelManager — load outside the lock, per-call wait, evict_idle

**Files:** Modify `backend/app/core/memory/manager.py`, `backend/app/core/chat/graph.py`; Test `backend/tests/test_model_manager.py` (append)

**Interfaces — Produces:** `ModelManager.acquire(name, device="auto", wait_timeout_s: float | None = None)`; `ModelManager.evict_idle() -> int` (evicts every idle local model, returns how many); chat passes `wait_timeout_s=CHAT_WAIT_S` (5.0).

- [ ] **Step 1: failing tests** (append)

```python
def _blocking_factory(release, started, loads):
    def factory(name, **kwargs):
        loads.append(name)
        started.set()
        release.wait(5)
        return _Emb(name, kwargs.get("device"))
    return factory


def test_status_is_readable_while_a_model_loads():
    release, started, loads = threading.Event(), threading.Event(), []
    manager = ModelManager(_blocking_factory(release, started, loads), max_local=1,
                           is_local=lambda n: True, on_evict=lambda: None)
    t = threading.Thread(target=lambda: manager.acquire("e5", "cpu").__enter__())
    t.start()
    started.wait(5)
    began = time.monotonic()
    assert manager.loaded() == []          # the loading model is not listed yet
    assert time.monotonic() - began < 0.5  # and the call did not block
    release.set()
    t.join(5)


def test_same_model_requested_while_loading_loads_once():
    release, started, loads = threading.Event(), threading.Event(), []
    manager = ModelManager(_blocking_factory(release, started, loads), max_local=1,
                           is_local=lambda n: True, on_evict=lambda: None)
    got = []

    def use():
        with manager.acquire("e5", "cpu") as emb:
            got.append(emb)

    threads = [threading.Thread(target=use) for _ in range(2)]
    for t in threads:
        t.start()
    started.wait(5)
    release.set()
    for t in threads:
        t.join(5)
    assert loads == ["e5"] and got[0] is got[1]


def test_waiters_are_released_when_a_load_fails():
    calls = []

    def factory(name, **kwargs):
        calls.append(name)
        if len(calls) == 1:
            raise OSError("boom")
        return _Emb(name, kwargs.get("device"))

    manager = ModelManager(factory, max_local=1, is_local=lambda n: True, on_evict=lambda: None)
    with pytest.raises(OSError):
        with manager.acquire("e5", "cpu"):
            pass
    with manager.acquire("paraphrase", "cpu") as emb:  # the slot did not leak
        assert emb.name == "paraphrase"


def test_per_call_wait_timeout_overrides_the_default():
    manager, _, _ = _manager(max_local=1, timeout=30)
    release, holder = _hold(manager, "e5")
    began = time.monotonic()
    try:
        with manager.acquire("paraphrase", "cpu", wait_timeout_s=0.1):
            pass
    finally:
        release.set()
        holder.join(5)
    assert time.monotonic() - began < 2


def test_evict_idle_unloads_idle_local_models_only():
    manager, _, _ = _manager(max_local=3)
    with manager.acquire("e5", "cpu"):
        pass
    with manager.acquire("gemini"):
        pass
    release, holder = _hold(manager, "paraphrase")
    try:
        assert manager.evict_idle() == 1
        assert {m.name for m in manager.loaded()} == {"gemini", "paraphrase"}
    finally:
        release.set()
        holder.join(5)
```

- [ ] **Step 2:** run `pytest tests/test_model_manager.py -q`; expect the 5 new tests to FAIL.
- [ ] **Step 3: implement.** `_Entry` gains `ready: bool = False` and `embedder: Embedder | None`. `_checkout(key, local, wait_timeout_s)`:

```python
    def _checkout(self, key, local, wait_timeout_s):
        with self._cond:
            while True:
                entry = self._entries.get(key)
                if entry is None:
                    break
                if entry.ready:
                    entry.refs += 1
                    self._entries.move_to_end(key)
                    return entry
                self._cond.wait()  # someone else is loading it
            if local:
                self._evict_other_devices(key)
                self._make_room(wait_timeout_s)
            entry = self._entries[key] = _Entry(embedder=None, local=local, refs=1)
        try:
            embedder = self._load(key, local)  # outside the lock
        except BaseException:
            with self._cond:
                del self._entries[key]
                self._cond.notify_all()
            raise
        with self._cond:
            entry.embedder, entry.ready = embedder, True
            self._entries.move_to_end(key)
            self._cond.notify_all()
        return entry
```

`loaded()` lists only `ready` entries. `_make_room(wait_timeout_s)` uses the given timeout (`self._wait_timeout_s` when None). Idle means `ready and refs == 0`. `evict_idle()`:

```python
    def evict_idle(self) -> int:
        """Unload every idle local model (before handing the machine to the LLM)."""
        with self._cond:
            idle = [k for k, e in self._entries.items() if e.local and e.ready and e.refs == 0]
            for key in idle:
                self._evict(key)
            self._cond.notify_all()
            return len(idle)
```

In `chat/graph.py`, add `CHAT_WAIT_S = 5.0` (a chat turn should not stall for 30 s behind an experiment) and pass `wait_timeout_s=CHAT_WAIT_S` to `acquire`.

- [ ] **Step 4:** run `pytest -q` and expect all to pass. **Step 5:** commit `feat(memory): load models outside the manager lock; per-call wait; evict_idle`.

---

### Task 2: Batched query embedding and numpy-free vectors

**Files:** Modify `backend/app/core/embedding/base.py`, `backend/app/core/embedding/huggingface.py`; Test `backend/tests/test_embedding.py` (append)

**Interfaces — Produces:** `Embedder.embed_queries(texts: list[str]) -> list[list[float]]` (default loops over `embed_query`; `HuggingFaceEmbedder` batches).

- [ ] **Step 1: failing tests**

```python
def test_embed_queries_defaults_to_embed_query():
    from app.core.embedding.base import Embedder

    class _E(Embedder):
        def embed_documents(self, texts): raise AssertionError
        def embed_query(self, text): return [float(len(text))]
        @property
        def dimension(self): return 1

    assert _E().embed_queries(["a", "bb"]) == [[1.0], [2.0]]


def test_huggingface_batches_and_returns_plain_floats():
    import numpy as np
    from app.core.embedding.huggingface import HuggingFaceEmbedder

    calls = []

    class _Model:
        def encode(self, texts, **kwargs):
            calls.append((texts, kwargs.get("batch_size")))
            if isinstance(texts, str):
                return np.array([0.5, 1.0], dtype=np.float32)
            return np.ones((len(texts), 2), dtype=np.float32)

    emb = HuggingFaceEmbedder("x", model=_Model())
    out = emb.embed_queries(["a", "b", "c"])
    assert out == [[1.0, 1.0]] * 3 and type(out[0][0]) is float
    assert calls[-1] == (["a", "b", "c"], 32)
    assert emb.embed_query("q") == [0.5, 1.0]
```

- [ ] **Step 2:** run and expect FAIL. **Step 3: implement:**

```python
# base.py, in Embedder
    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed several queries (as queries, not documents). Providers may batch it."""
        return [self.embed_query(text) for text in texts]
```

```python
# huggingface.py
_BATCH_SIZE = 32

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents."""
        return self._model.encode(texts, batch_size=_BATCH_SIZE, convert_to_numpy=True).tolist()

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Local models embed queries and documents the same way: one batched call."""
        return self.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return self._model.encode(text, convert_to_numpy=True).tolist()
```

- [ ] **Step 4:** run `pytest -q` and expect green. **Step 5:** commit `perf(embedding): batch local query embeddings and return plain float lists`.

---

### Task 3: Unload a model from the local LLM server

**Files:** Modify `backend/app/core/llm/ollama.py`; Test `backend/tests/test_memory_device.py` (append)

**Interfaces — Produces:** `unload_local_llm(model: str, base_url: str | None = None, timeout: float = 5.0) -> bool`. It returns True when Ollama confirmed the unload, and False otherwise (MLX has no unload API; unreachable; error). It never raises.

- [ ] **Step 1: failing tests**

```python
def test_unload_asks_ollama_to_drop_the_model(monkeypatch):
    sent = []

    def post(url, json, timeout):
        sent.append((url, json))
        return _Resp(200, {})

    monkeypatch.setattr(httpx, "post", post)
    from app.core.llm.ollama import unload_local_llm

    assert unload_local_llm("qwen3:1.7b", "http://x/v1") is True
    assert sent == [("http://x/api/generate", {"model": "qwen3:1.7b", "keep_alive": 0})]


def test_unload_on_a_server_without_the_api_is_a_no_op(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: _Resp(404))
    from app.core.llm.ollama import unload_local_llm

    assert unload_local_llm("mlx-community/X", "http://x/v1") is False


def test_unload_never_raises(monkeypatch):
    def post(url, json, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", post)
    from app.core.llm.ollama import unload_local_llm

    assert unload_local_llm("q", "http://x/v1") is False
```

- [ ] **Step 2:** expect FAIL. **Step 3: implement:**

```python
def unload_local_llm(model: str, base_url: str | None = None, timeout: float = 5.0) -> bool:
    """Ask the local LLM server to free `model` now. True if it confirmed; never raises.

    Ollama unloads on a generate call with keep_alive=0. MLX and llama.cpp have
    no such API (the MLX server keeps one model and swaps it on demand).
    """
    import httpx

    root = (base_url or get_settings().ollama_base_url).rstrip("/").removesuffix("/v1")
    try:
        resp = httpx.post(f"{root}/api/generate", json={"model": model, "keep_alive": 0}, timeout=timeout)
        return resp.status_code < 400
    except httpx.HTTPError:
        return False
```

Also add to `conftest.py`'s `_no_llm_probe` fixture: `monkeypatch.setattr(ollama, "unload_local_llm", lambda *a, **k: False)`. The unload tests import the function inside the test body, after the fixture patched the module, so they must use `ollama.__dict__`. Instead, keep a module-level alias: `_real_unload = ollama.unload_local_llm` captured at test-module import, and call `_real_unload` in the three tests.

- [ ] **Step 4:** run `pytest -q` and expect green. **Step 5:** commit `feat(llm): ask the local LLM server to unload a model`.

---

### Task 4: Query-vector cache and lease switcher

**Files:** Create `backend/app/core/memory/leases.py`; Test `backend/tests/test_memory_leases.py`

**Interfaces — Produces:**
- `CachedQueryEmbedder(vectors: dict[str, list[float]], fallback: Callable[[], Embedder], dimension: int)`. It is an `Embedder`: `embed_query` answers from `vectors` and calls `fallback()` (lazily, once) on a miss. `embed_documents` and `embed_queries` go to the fallback. `loaded_fallback: bool` tells whether it had to load.
- `LeaseSwitcher(models: ModelManager)`. `get(name, device) -> Embedder` keeps one lease open, and switching to another (name, device) releases the previous one. `close()` releases. It is a context manager.

- [ ] **Step 1: failing tests**

```python
"""Query-vector cache for staged experiments, and a lease that follows consecutive runs."""
from app.core.memory.leases import CachedQueryEmbedder, LeaseSwitcher
from app.core.memory.manager import ModelManager


class _Emb:
    def __init__(self, name="e"):
        self.name = name

    def embed_query(self, text):
        return [9.0]

    def embed_documents(self, texts):
        return [[9.0] for _ in texts]

    def embed_queries(self, texts):
        return self.embed_documents(texts)

    @property
    def dimension(self):
        return 1


def test_cached_queries_never_load_the_model():
    loads = []
    emb = CachedQueryEmbedder({"q": [1.0]}, lambda: loads.append(1) or _Emb(), dimension=1)
    assert emb.embed_query("q") == [1.0]
    assert loads == [] and emb.loaded_fallback is False


def test_a_miss_loads_the_model_once():
    loads = []
    emb = CachedQueryEmbedder({}, lambda: loads.append(1) or _Emb(), dimension=1)
    assert emb.embed_query("gerado pelo LLM") == [9.0]
    emb.embed_query("outro")
    assert loads == [1] and emb.loaded_fallback is True


def test_switcher_keeps_the_lease_across_same_model_runs():
    loads = []
    manager = ModelManager(lambda n, **k: loads.append(n) or _Emb(n), max_local=1,
                           is_local=lambda n: True, on_evict=lambda: None)
    with LeaseSwitcher(manager) as leases:
        a = leases.get("e5", "cpu")
        b = leases.get("e5", "cpu")
        assert a is b and manager.loaded()[0].in_use == 1
        leases.get("paraphrase", "cpu")
        assert [(m.name, m.in_use) for m in manager.loaded()] == [("paraphrase", 1)]
    assert manager.loaded()[0].in_use == 0
    assert loads == ["e5", "paraphrase"]
```

- [ ] **Step 2:** expect FAIL (module missing). **Step 3: implement:**

```python
"""Helpers that decide when an embedder must actually be in memory."""
from collections.abc import Callable
from contextlib import ExitStack

from app.core.embedding.base import Embedder
from app.core.memory.manager import ModelManager


class CachedQueryEmbedder(Embedder):
    """Answers known queries from precomputed vectors; loads the real model only on a miss.

    Staged experiments embed every question before any LLM runs. Text the LLM
    writes later (a HyDE passage, multi-query variations, CRAG/agentic
    rewrites) is a miss, and only then does the model come into memory.
    """

    def __init__(self, vectors: dict[str, list[float]], fallback: Callable[[], Embedder], dimension: int) -> None:
        self._vectors = vectors
        self._fallback_factory = fallback
        self._fallback: Embedder | None = None
        self._dimension = dimension

    @property
    def loaded_fallback(self) -> bool:
        """Whether a miss forced the real model into memory."""
        return self._fallback is not None

    def _model(self) -> Embedder:
        if self._fallback is None:
            self._fallback = self._fallback_factory()
        return self._fallback

    def embed_query(self, text: str) -> list[float]:
        """The cached vector, or the real model's for text never seen before."""
        vector = self._vectors.get(text)
        return vector if vector is not None else self._model().embed_query(text)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model().embed_documents(texts)

    @property
    def dimension(self) -> int:
        return self._dimension


class LeaseSwitcher:
    """Holds one embedder lease and swaps it only when the requested model changes."""

    def __init__(self, models: ModelManager) -> None:
        self._models = models
        self._key: tuple[str, str] | None = None
        self._stack: ExitStack | None = None
        self._embedder: Embedder | None = None

    def get(self, name: str, device: str) -> Embedder:
        """The embedder for (name, device), keeping the current lease if it matches."""
        if self._key != (name, device):
            self.close()
            self._stack = ExitStack()
            self._embedder = self._stack.enter_context(self._models.acquire(name, device))
            self._key = (name, device)
        return self._embedder

    def close(self) -> None:
        """Release the current lease, if any."""
        if self._stack is not None:
            self._stack.close()
        self._stack, self._key, self._embedder = None, None, None

    def __enter__(self) -> "LeaseSwitcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
```

- [ ] **Step 4:** run `pytest -q` and expect green. **Step 5:** commit `feat(memory): query-vector cache and lease switcher`.

---

### Task 5: Evaluation embeds each distinct text once

**Files:** Modify `backend/app/core/evaluation/runner.py`; Test `backend/tests/test_evaluation_runner.py` (append)

**Interfaces — Produces:** `evaluate_sample` wraps the embedder in a per-sample memo (same scores, fewer calls); `metrics_need_embedder(metric_names: list[str]) -> bool`.

- [ ] **Step 1: failing tests**

```python
def test_each_distinct_text_is_embedded_once_per_sample():
    from app.core.evaluation.base import EvalSample
    from app.core.evaluation.runner import evaluate_sample

    calls = []

    class _E:
        def embed_query(self, text):
            calls.append(text)
            return [1.0, float(len(text))]

    sample = EvalSample(question="q?", answer="a", contexts=["c1", "c2"], reference_answer="r")
    names = ["answer_relevancy", "faithfulness", "context_precision", "context_recall", "answer_correctness"]
    evaluate_sample(sample, names, embedder=_E())
    assert sorted(calls) == sorted(set(calls))


def test_metrics_need_embedder():
    from app.core.evaluation.runner import metrics_need_embedder

    assert metrics_need_embedder(["rouge_l", "faithfulness"]) is True
    assert metrics_need_embedder(["rouge_l"]) is False
```

- [ ] **Step 2:** expect FAIL. **Step 3: implement** in `runner.py`:

```python
class _MemoEmbedder:
    """Embeds each distinct text once; metrics of one sample share the vectors."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._vectors: dict[str, list[float]] = {}

    def embed_query(self, text: str) -> list[float]:
        if text not in self._vectors:
            self._vectors[text] = self._embedder.embed_query(text)
        return self._vectors[text]


def _needs_embedder(metric_class) -> bool:
    return "embedder" in inspect.signature(metric_class.__init__).parameters


def metrics_need_embedder(metric_names: list[str]) -> bool:
    """Whether any of the metrics compares embeddings (so an eval embedder must load)."""
    return any(_needs_embedder(evaluation_registry.get(name)) for name in metric_names)
```

In `evaluate_sample`, wrap once before the loop (`memo = _MemoEmbedder(embedder) if embedder is not None else None`), pass `memo`, and use `_needs_embedder` for the check.

- [ ] **Step 4:** run `pytest -q` and expect green (scores unchanged; existing evaluation tests still pass). **Step 5:** commit `perf(evaluation): embed each distinct text once per sample`.

---

### Task 6: Staged experiments

**Files:** Modify `backend/app/experiments/schemas.py`, `backend/app/experiments/orchestrator.py`; Test `backend/tests/test_orchestrator.py` (append)

**Interfaces:**
- Consumes: `ModelManager.evict_idle`, `acquire(..., wait_timeout_s)`, `Embedder.embed_queries`, `unload_local_llm`, `is_local_llm`, `CachedQueryEmbedder`, `LeaseSwitcher`, `metrics_need_embedder`.
- Produces: `ExperimentConfig.staged: bool = True`; `experiment.config["phase"]` ∈ {`"generating"`, `"evaluating"`} while running; `orchestrator.ERROR_PREFIX = "[ERRO: "`.

- [ ] **Step 1: failing tests** (append to `tests/test_orchestrator.py`)

```python
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


def _config(**kw):
    base = dict(base="viagem", chunkings=["recursive"], embeddings=["e5"], rags=["naive"],
                retrievers=["similarity"], metrics=["answer_relevancy"], llms=["qwen3:1.7b"],
                eval_embedding="e5")
    return ExperimentConfig(**{**base, **kw})


def test_staged_run_keeps_embedders_out_of_memory_while_generating(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "staged-1")
    run_experiment(experiment_id, _config(), [QuestionItem(text="Where?"), QuestionItem(text="When?")],
                   _staged_deps(store, session_factory, events))
    first_gen, last_gen = events.index("gen"), len(events) - 1 - events[::-1].index("gen")
    assert "load:e5" in events[:first_gen]              # stage A: question vectors
    assert "evict" in events[events.index("load:e5"):first_gen]  # unloaded before the LLM
    assert not any(e.startswith("load:") for e in events[first_gen:last_gen])  # B: none loaded
    assert "load:e5" in events[last_gen:]               # stage C: eval embedder
    check = session_factory()
    results = [r for run in check.get(Experiment, experiment_id).runs for r in run.results]
    assert len(results) == 2 and all("answer_relevancy" in r.scores for r in results)
    assert check.get(Experiment, experiment_id).status == "done"
    check.close()


def test_staged_hyde_loads_the_embedder_only_for_generated_text(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "staged-hyde")
    run_experiment(experiment_id, _config(rags=["hyde"], metrics=["rouge_l"]),
                   [QuestionItem(text="Where?", reference="Aqui.")],
                   _staged_deps(store, session_factory, events))
    first_gen = events.index("gen")
    loads_during_b = [e for e in events[first_gen:] if e.startswith("load:")]
    assert loads_during_b == ["load:e5"]   # the HyDE passage is a cache miss
    # rouge_l needs no embedder: stage C loads nothing more
    check = session_factory()
    [result] = [r for run in check.get(Experiment, experiment_id).runs for r in run.results]
    assert "rouge_l" in result.scores
    check.close()


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
    run_experiment(experiment_id, _config(), [QuestionItem(text="Boom?"), QuestionItem(text="Fine?")], deps)
    check = session_factory()
    by_q = {r.question: r for run in check.get(Experiment, experiment_id).runs for r in run.results}
    assert by_q["Boom?"].generated_answer.startswith("[ERRO: ") and by_q["Boom?"].scores == {}
    assert "answer_relevancy" in by_q["Fine?"].scores
    check.close()


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
    run_experiment(experiment_id, _config(retrievers=["similarity", "mmr"]),
                   [QuestionItem(text="Where?")], deps)
    check = session_factory()
    experiment = check.get(Experiment, experiment_id)
    results = [r for run in experiment.runs for r in run.results]
    assert experiment.status == "paused" and len(results) == 1
    assert "answer_relevancy" in results[0].scores
    check.close()


def test_unstaged_run_holds_the_retrieval_embedder_across_runs(session_factory):
    events = []
    store = _indexed_store("e5")
    experiment_id = _new_experiment(session_factory, "unstaged")
    run_experiment(experiment_id,
                   _config(staged=False, retrievers=["similarity", "mmr"], eval_embedding="paraphrase"),
                   [QuestionItem(text="Where?")], _staged_deps(store, session_factory, events))
    assert events.count("load:e5") == 1      # not reloaded for the second retriever
```

- [ ] **Step 2:** expect FAIL (`staged` unknown, ordering wrong).

- [ ] **Step 3: implement.** In `schemas.py` add:

```python
    # One model in memory at a time: embed questions, generate, then score
    # (spec 3.4). False runs everything in one pass (escape hatch).
    staged: bool = True
```

In `orchestrator.py`:

1. Split `_process_question` into `_generate(rag, question)` (returns answer, contexts, latency, tokens) and scoring. `_process_question_with_retry(rag, question, metrics, eval_embedder)` keeps its signature and return shape. When `eval_embedder is None and not metrics`, it skips scoring (`scores = {}`). Stage B calls it with `metrics=[]`.
2. `ERROR_PREFIX = "[ERRO: "`, used where the error row is written.
3. `_set_phase(session, experiment, phase)` writes `experiment.config = {**experiment.config, "phase": phase}` and commits.
4. `_question_vectors(deps, config, questions, device) -> dict[str, dict[str, list[float]]]` (stage A). For each distinct retrieval embedding: `with deps.models.acquire(embedding, device) as emb: vectors[embedding] = dict(zip(texts, emb.embed_queries(texts)))`. Then `deps.models.evict_idle()`.
5. `_score_results(session, experiment_id, config, deps)` (stage C):

```python
def _score_results(session, experiment_id, config, deps) -> None:
    """Stage C: free the LLM, load the eval embedder once, score every stored answer."""
    for llm_name in config.llms:
        if is_local_llm(llm_name):
            ollama.unload_local_llm(_llm_server_model(llm_name))
    rows = (
        session.query(RunResult).join(ExperimentRun)
        .filter(ExperimentRun.experiment_id == experiment_id).all()
    )
    pending = [r for r in rows if not r.scores and not r.generated_answer.startswith(ERROR_PREFIX)]
    if not pending:
        return
    device = resolve_embedding_device(active_profile())
    eval_context = (
        deps.models.acquire(config.eval_embedding, device)
        if metrics_need_embedder(config.metrics) else nullcontext(None)
    )
    with eval_context as eval_embedder:
        for row in pending:
            sample = EvalSample(
                question=row.question, answer=row.generated_answer,
                contexts=[c.get("text", "") for c in row.retrieved_context],
                reference_answer=row.reference_answer,
            )
            row.scores = _score_with_retry(sample, config.metrics, eval_embedder)
        session.commit()
```

`_score_with_retry` retries `evaluate_sample` up to `_MAX_RETRIES` with `_RETRY_DELAY_S`; after that it logs and returns `{}`. `_llm_server_model(name)` maps a legacy named id through `get_ollama_models()` to its model, and otherwise returns the name.

6. `_run_experiment` becomes:

```python
        profile = active_profile()
        device = resolve_embedding_device(profile, config.llms)
        concurrency = ...  # unchanged
        staged = config.staged
        vectors = _question_vectors(deps, config, questions, device) if staged else {}
        if staged:
            _set_phase(session, experiment, "generating")
        eval_context = (
            deps.models.acquire(config.eval_embedding, device)
            if not staged and metrics_need_embedder(config.metrics) else nullcontext(None)
        )
        paused = False
        loaded_llm_name, llm = None, None
        with eval_context as eval_embedder, LeaseSwitcher(deps.models) as leases:
            for llm_name, (chunking, embedding), rag_name, retriever_name in _combinations(config):
                ...  # pause checkpoint, run row, llm swap: unchanged
                if staged:
                    embedder = CachedQueryEmbedder(
                        vectors[embedding],
                        fallback=lambda e=embedding: leases.get(e, device),
                        dimension=len(next(iter(vectors[embedding].values()), [])),
                    )
                else:
                    embedder = leases.get(embedding, device)
                ...  # build retriever/rag with `embedder`, run questions with
                     # metrics=[] if staged else config.metrics, persist rows, unchanged
        if staged:
            _set_phase(session, experiment, "evaluating")
            _score_results(session, experiment_id, config, deps)
        experiment.status = "paused" if paused else "done"
        experiment.config = {k: v for k, v in experiment.config.items() if k != "phase"}
```

The `LeaseSwitcher` exits (releasing any lazily-loaded retrieval embedder) before stage C loads the eval embedder. Import `from app.core.llm import ollama` and call `ollama.unload_local_llm`, so the conftest patch applies.

- [ ] **Step 4:** run `pytest -q` and expect green; the part-1 orchestrator tests must still pass. Their fakes are remote ("gemini"), and `test_embedders_load_once_per_experiment` still loads "gemini" once: stage A and stage C share the remote entry, since remote models are never evicted.
- [ ] **Step 5:** commit `feat(experiments): staged execution keeps one model in memory at a time`.

---

### Task 7: Show the evaluation stage

**Files:** Modify `backend/app/api/experiments.py`, `frontend/src/api/types.ts`, `frontend/src/pages/ExperimentDetailPage.tsx`, `frontend/src/context/TasksContext.tsx`; Test `backend/tests/test_experiments_api.py`, `frontend/src/pages/ExperimentDetailPage.test.tsx` (append)

**Interfaces — Produces:** `progress.phase: "generating" | "evaluating" | null` in `GET /experiments/{id}`; TS `ExperimentProgress.phase?: string | null`.

- [ ] **Step 1: failing tests.** Backend: create an `Experiment` with `status="running", config={"phase": "evaluating", ...}` directly in the DB through the test deps' session factory, then `GET /experiments/{id}` and assert `progress.phase == "evaluating"`. Frontend: mock `getExperiment` with `status: "running", progress: { completed: 1, total: 1, phase: "evaluating" }` and assert the page shows `Avaliando as respostas`.
- [ ] **Step 2:** expect FAIL. **Step 3: implement.** API: `"progress": {"completed": ..., "total": ..., "phase": cfg.get("phase")}`. Detail page: when `detail.progress?.phase === "evaluating"`, render `<span>Avaliando as respostas</span>` instead of the "N de M combinações" span. TasksContext: when `p?.phase === "evaluating"`, the message is `"avaliando as respostas"`.
- [ ] **Step 4:** `make test` + `make front-test` green. **Step 5:** commit `feat(experiments): show when an experiment is scoring its answers`.

---

### Task 8: Streaming ingestion

**Files:** Modify `backend/app/ingestion/pipeline.py`, `backend/app/core/vectorstore/qdrant.py`; Test `backend/tests/test_ingestion_pipeline.py` (append)

**Interfaces — Produces:** `QdrantStore.add(name, vectors, payloads, start_id: int | None = None)`; `QdrantStore.count(name) -> int`; `ingest_documents(..., batch_size: int = 256)`.

- [ ] **Step 1: failing test**

```python
def test_ingestion_embeds_and_stores_in_batches():
    from qdrant_client import QdrantClient

    from app.core.vectorstore.qdrant import QdrantStore

    batches = []

    class _E:
        def embed_documents(self, texts):
            batches.append(len(texts))
            return [[1.0, 0.0, float(i)] for i, _ in enumerate(texts)]

        def embed_query(self, text):
            return [1.0, 0.0, 0.0]

        @property
        def dimension(self):
            return 3

    store = QdrantStore(client=QdrantClient(":memory:"))
    text = "\n\n".join(f"Parágrafo número {i} com algum texto." for i in range(5))
    config = IngestConfig(base="b", chunkings=["recursive"], embeddings=["gemini"])
    result = ingest_documents([Document(name="a.txt", text=text)], config, store,
                              embedder_factory=lambda n, **k: _E(), batch_size=2)
    assert max(batches) <= 2
    name = result.collections[0]
    points = store.scroll(name)
    assert len(points) == result.total_chunks
    assert len({p["id"] for p in points}) == result.total_chunks  # no id collisions
```

(If the recursive splitter merges the 5 paragraphs into one chunk, use `chunkings=["fixed"]` with a longer text. Check `result.total_chunks >= 3` first and adjust the text until it is.)

- [ ] **Step 2:** expect FAIL (`batch_size` unknown). **Step 3: implement.** `QdrantStore.count(name)` returns `self._client.count(name).count`. `add(..., start_id=None)` uses `start_id if start_id is not None else self.count(name)`. The pipeline computes `next_id = store.count(name)` once per collection and, per document, loops `for i in range(0, len(chunks), batch_size)`: embed the slice, build its payloads (the `chunk_index` stays document-global: `i + offset`), `store.add(name, vectors, payloads, start_id=next_id)`, `next_id += len(slice)`.
- [ ] **Step 4:** `pytest -q` green. **Step 5:** commit `perf(ingestion): embed and store chunks in batches`.

---

### Task 9: Parent-document retriever reads only the window

**Files:** Modify `backend/app/core/vectorstore/qdrant.py`, `backend/app/core/retrieval/parent_document.py`; Test `backend/tests/test_retrievers_advanced.py` (append)

**Interfaces — Produces:** `QdrantStore.scroll(name, where=None, limit=1000, ranges: dict[str, tuple[int, int]] | None = None)` (inclusive `gte`/`lte` bounds).

- [ ] **Step 1: failing test.** Store 30 chunks of one document (fake 3-dim vectors, `chunk_index` 0..29) in a Qdrant `:memory:` collection. Wrap `store.scroll` in a spy that records the length of each returned list. Retrieve with `ParentDocumentRetriever(top_k=1, window=1)` and assert every scroll returned ≤ 3 points, and that the result text is the 3 neighbours joined in order.
- [ ] **Step 2:** expect FAIL (returns 30). **Step 3: implement.** `_payload_filter(where, ranges)` adds `FieldCondition(key=k, range=Range(gte=lo, lte=hi))` for each range (import `Range` from `qdrant_client.models`). The retriever calls `scroll(collection, where={"source_doc": source}, ranges={"chunk_index": (index - window, index + window)})`.
- [ ] **Step 4:** `pytest -q` green. **Step 5:** commit `perf(retrieval): parent-document fetches only the neighbour window`.

---

### Task 10: Docs

- [ ] Spec: the status line says Phases 3.4 and 4 are implemented (part 2 plan), with the `on_disk` ruling. Section 3.4 notes that the escape hatch is `staged: false` in the experiment config.
- [ ] README memory section: one paragraph on staged execution (three stages, and when the embedder still loads during generation). CLAUDE.md: one line under Estrutura for `app/core/memory/leases.py`.
- [ ] `graphify update .`, commit `docs: staged experiments`.
