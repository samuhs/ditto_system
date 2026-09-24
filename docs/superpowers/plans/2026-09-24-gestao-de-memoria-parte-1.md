# Gestão de memória, parte 1: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the RAM Ditto uses with local models. Memory profiles (`low`/`standard`), a process-wide `ModelManager` that caps resident local embedders, embedders that never share the GPU with a local LLM, an LLM-major orchestrator with a one-experiment queue, memory telemetry, and scripts that make the profile visible and switchable.

**Architecture:** `app/core/memory/` holds the profile (`profile.py`), the device policy (`device.py`), the model cache (`manager.py`) and process stats (`stats.py`). Every place that builds an embedder (orchestrator, chat, ingestion) leases it from the `ModelManager` instead of calling the factory. The shell side reads `MEMORY_PROFILE` from `.env` through helpers in `scripts/common.sh` and derives the LLM-server flags and container limits from it.

**Tech Stack:** FastAPI, SQLAlchemy, sentence-transformers/torch (optional), psutil (new), bash, Docker Compose, React + Mantine + vitest.

**Spec:** `docs/superpowers/specs/2026-09-24-gestao-de-memoria-design.md`

**Scope:** spec Phases 0, 1, 2 and 3.1–3.3. Phase 3.4 (staged execution) and Phase 4 (code polish) go in part 2. Until part 2 lands, an experiment whose local eval embedder differs from its local retrieval embedder briefly exceeds the 1-model limit. The manager logs it, and the preflight warns about it.

## Global Constraints

- Identifiers, docstrings and errors in English. UI text and user-facing script messages in PT-BR.
- Tests never touch the network, Postgres or a real LLM server (Qdrant `:memory:`, SQLite, fakes).
- Profiles: `low` = 1 local model, embedders on CPU, max concurrency 2; `standard` = 3 local models, device `auto`, max concurrency 32.
- `low` is detected when RAM ≤ 8 GB (threshold 9 000 000 000 bytes). Explicit `.env` values win over the profile.
- The embedder never shares the GPU with a local LLM. There is no setting that forces GPU.
- `make up` on `low` recommends `make up-local` and never switches on its own.
- MLX on `low`: `--decode-concurrency 2 --prompt-cache-size 2 --prompt-cache-bytes 512M`. Ollama on `low`: `NUM_PARALLEL=2 MAX_LOADED_MODELS=1 FLASH_ATTENTION=1 KV_CACHE_TYPE=q8_0`.
- Switch command: `make memory-profile PROFILE=low|standard`. Show: `make memory-profile`.

## Review Focus

1. `MEMORY_PROFILE` with a typo or wrong case (`Low`, `lwo`) → case-insensitive; unknown values fall back to `standard` with a logged warning, and nothing crashes (Task 1).
2. Empty `.env` passthrough from Compose (`MAX_LOCAL_MODELS=`) → treated as unset, not a validation error at startup (Task 1).
3. One thread needs two different local models at once (eval + retrieval) with the limit at 1 → loads beyond the limit with a warning instead of deadlocking (Task 4).
4. A chat turn needs a model while an experiment holds the only slot → waits up to 30 s, then loads beyond the limit, and never hangs (Task 4).
5. LLM server replies to `/api/ps` with non-JSON, or is down → a malformed reply counts as resident (CPU); an unreachable server counts as not resident; the probe never raises (Task 2).

---

### Task 1: Memory profile

**Files:**
- Modify: `backend/app/core/config/settings.py`
- Create: `backend/app/core/memory/__init__.py`, `backend/app/core/memory/profile.py`
- Test: `backend/tests/test_memory_profile.py`

**Interfaces:**
- Produces: `MemoryProfile(name: str, max_local_models: int, embedding_device: str, max_concurrency: int)`, `PROFILES: dict[str, MemoryProfile]`, `active_profile() -> MemoryProfile`. `Settings` gains `memory_profile: str`, `max_local_models: int | None`, `embedding_device: str | None`, `max_experiment_concurrency: int | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""Memory profile selection and env overrides."""
import pytest

from app.core.config.settings import get_settings
from app.core.memory.profile import PROFILES, active_profile


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_profile_is_standard():
    assert active_profile() == PROFILES["standard"]


def test_low_profile_limits(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    profile = active_profile()
    assert (profile.name, profile.max_local_models, profile.embedding_device, profile.max_concurrency) == (
        "low", 1, "cpu", 2,
    )


def test_profile_name_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", " Low ")
    assert active_profile().name == "low"


def test_unknown_profile_falls_back_to_standard(monkeypatch, caplog):
    monkeypatch.setenv("MEMORY_PROFILE", "lwo")
    assert active_profile().name == "standard"
    assert "lwo" in caplog.text


def test_explicit_env_values_override_the_profile(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    monkeypatch.setenv("MAX_LOCAL_MODELS", "2")
    monkeypatch.setenv("MAX_EXPERIMENT_CONCURRENCY", "4")
    profile = active_profile()
    assert (profile.max_local_models, profile.max_concurrency) == (2, 4)


def test_empty_env_values_mean_unset(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    monkeypatch.setenv("MAX_LOCAL_MODELS", "")
    monkeypatch.setenv("EMBEDDING_DEVICE", "")
    assert active_profile() == PROFILES["low"]


def test_embedding_device_cannot_force_the_gpu(monkeypatch):
    monkeypatch.setenv("MEMORY_PROFILE", "low")
    monkeypatch.setenv("EMBEDDING_DEVICE", "mps")
    assert active_profile().embedding_device == "cpu"
    monkeypatch.setenv("MEMORY_PROFILE", "standard")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    assert active_profile().embedding_device == "cpu"
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_memory_profile.py -v`
Expected: FAIL, `ModuleNotFoundError: app.core.memory`

- [ ] **Step 3: Implement**

`settings.py`, new fields on `Settings` plus a validator:

```python
    # Memory profile (low | standard) and explicit overrides; empty means unset.
    memory_profile: str = "standard"
    max_local_models: int | None = None
    embedding_device: str | None = None
    max_experiment_concurrency: int | None = None

    @field_validator(
        "max_local_models", "embedding_device", "max_experiment_concurrency", mode="before"
    )
    @classmethod
    def _empty_is_unset(cls, value):
        """Compose passes unset .env keys through as empty strings."""
        return None if value == "" else value
```

(import `field_validator` from `pydantic`).

`backend/app/core/memory/__init__.py`:

```python
"""Memory management: profiles, the local-model cache, and device policy."""
```

`backend/app/core/memory/profile.py`:

```python
"""Memory profiles: how many local models stay resident and how hard the machine is pushed."""
import logging
from dataclasses import dataclass, replace

from app.core.config.settings import get_settings

logger = logging.getLogger(__name__)

CPU = "cpu"
AUTO = "auto"


@dataclass(frozen=True)
class MemoryProfile:
    """Limits one memory profile applies."""

    name: str
    max_local_models: int
    # "cpu" always; "auto" lets the device policy pick the GPU when the LLM leaves it free.
    embedding_device: str
    max_concurrency: int


PROFILES: dict[str, MemoryProfile] = {
    "low": MemoryProfile("low", max_local_models=1, embedding_device=CPU, max_concurrency=2),
    "standard": MemoryProfile("standard", max_local_models=3, embedding_device=AUTO, max_concurrency=32),
}


def active_profile() -> MemoryProfile:
    """The profile named by MEMORY_PROFILE, with explicit env overrides applied."""
    settings = get_settings()
    name = settings.memory_profile.strip().lower()
    if name not in PROFILES:
        logger.warning("unknown MEMORY_PROFILE %r; using 'standard'", settings.memory_profile)
        name = "standard"
    profile = PROFILES[name]
    if settings.max_local_models is not None:
        profile = replace(profile, max_local_models=max(1, settings.max_local_models))
    if settings.max_experiment_concurrency is not None:
        profile = replace(profile, max_concurrency=max(1, settings.max_experiment_concurrency))
    # Only CPU can be forced: the GPU belongs to the LLM (see app.core.memory.device).
    if (settings.embedding_device or "").strip().lower() == CPU:
        profile = replace(profile, embedding_device=CPU)
    return profile
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_memory_profile.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit** — `feat(memory): add low/standard memory profiles`

---

### Task 2: Device policy and local-LLM probe

**Files:**
- Modify: `backend/app/core/llm/factory.py`, `backend/app/core/llm/ollama.py`, `backend/tests/conftest.py`
- Create: `backend/app/core/memory/device.py`
- Test: `backend/tests/test_memory_device.py`

**Interfaces:**
- Consumes: `MemoryProfile`, `CPU`, `AUTO` (Task 1).
- Produces: `is_local_llm(name: str) -> bool` (llm/factory.py); `local_llm_resident(base_url: str | None = None, timeout: float = 1.0) -> bool` (llm/ollama.py); `resolve_embedding_device(profile: MemoryProfile, llm_names: Iterable[str] = (), llm_resident: Callable[[], bool] | None = None) -> str` returning `"cpu"` or `"auto"`.

- [ ] **Step 1: Write the failing tests**

```python
"""Where local embedders run: never on the GPU a local LLM is using."""
import httpx
import pytest

from app.core.llm.factory import is_local_llm
from app.core.llm.ollama import local_llm_resident
from app.core.memory.device import resolve_embedding_device
from app.core.memory.profile import PROFILES

LOW, STANDARD = PROFILES["low"], PROFILES["standard"]


def _never_called():
    raise AssertionError("probe should not run")


@pytest.mark.parametrize(
    ("name", "local"),
    [("gemini", False), ("gemini-2.5-flash-lite", False), ("qwen3:1.7b", True),
     ("mlx-community/Qwen2.5-3B-Instruct-4bit", True), ("ollama", True), ("custom", True)],
)
def test_is_local_llm(name, local):
    assert is_local_llm(name) is local


def test_low_profile_is_always_cpu():
    assert resolve_embedding_device(LOW, ["gemini"], _never_called) == "cpu"


def test_standard_with_a_local_llm_is_cpu():
    assert resolve_embedding_device(STANDARD, ["gemini", "qwen3:1.7b"], _never_called) == "cpu"


def test_standard_with_remote_llm_and_idle_server_uses_gpu():
    assert resolve_embedding_device(STANDARD, ["gemini"], lambda: False) == "auto"


def test_standard_with_a_resident_local_model_is_cpu():
    assert resolve_embedding_device(STANDARD, [], lambda: True) == "cpu"


class _Resp:
    def __init__(self, status, payload=None, raw=False):
        self.status_code, self._payload, self._raw = status, payload, raw

    def json(self):
        if self._raw:
            raise ValueError("not json")
        return self._payload


def _fake_get(routes):
    def get(url, timeout):
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise httpx.ConnectError("no route")
    return get


def test_ollama_with_loaded_models_is_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(200, {"models": [{"name": "q"}]})}))
    assert local_llm_resident("http://x/v1") is True


def test_ollama_with_nothing_loaded_is_not_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(200, {"models": []})}))
    assert local_llm_resident("http://x/v1") is False


def test_mlx_server_counts_as_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(404), "/v1/models": _Resp(200, {})}))
    assert local_llm_resident("http://x/v1") is True


def test_malformed_reply_counts_as_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({"/api/ps": _Resp(200, raw=True)}))
    assert local_llm_resident("http://x/v1") is True


def test_unreachable_server_is_not_resident(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fake_get({}))
    assert local_llm_resident("http://x/v1") is False
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_memory_device.py -v`
Expected: FAIL on imports

- [ ] **Step 3: Implement**

`llm/factory.py`, appended:

```python
def is_local_llm(name: str) -> bool:
    """Whether the named LLM runs on this machine: anything Gemini does not serve."""
    return not (name == "gemini" or name.startswith("gemini-"))
```

`llm/ollama.py`, appended:

```python
def local_llm_resident(base_url: str | None = None, timeout: float = 1.0) -> bool:
    """Whether the local LLM server may hold a model in memory right now.

    Ollama lists loaded models at /api/ps. Servers without it (MLX, llama.cpp)
    cannot say, so a reachable one counts as resident; so does a malformed
    reply. An unreachable server holds nothing. Never raises.
    """
    import httpx

    root = (base_url or get_settings().ollama_base_url).rstrip("/").removesuffix("/v1")
    try:
        resp = httpx.get(f"{root}/api/ps", timeout=timeout)
        if resp.status_code < 400:
            return bool(resp.json().get("models"))
        return httpx.get(f"{root}/v1/models", timeout=timeout).status_code < 400
    except httpx.HTTPError:
        return False
    except (ValueError, AttributeError):
        return True
```

`memory/device.py`:

```python
"""Where local embedders run. The GPU belongs to the LLM; embedders get it only when it is free."""
from collections.abc import Callable, Iterable

from app.core.llm import ollama
from app.core.llm.factory import is_local_llm
from app.core.memory.profile import AUTO, CPU, MemoryProfile


def resolve_embedding_device(
    profile: MemoryProfile,
    llm_names: Iterable[str] = (),
    llm_resident: Callable[[], bool] | None = None,
) -> str:
    """CPU unless the profile allows the GPU and no local LLM can be on it."""
    if profile.embedding_device == CPU:
        return CPU
    if any(is_local_llm(name) for name in llm_names):
        return CPU
    probe = llm_resident or ollama.local_llm_resident
    return CPU if probe() else AUTO
```

`tests/conftest.py`, a new autouse fixture so no test probes a real server:

```python
@pytest.fixture(autouse=True)
def _no_llm_probe(monkeypatch):
    """Device policy never probes a real LLM server in tests: none is resident."""
    from app.core.llm import ollama

    monkeypatch.setattr(ollama, "local_llm_resident", lambda *a, **k: False)
```

The probe tests import `local_llm_resident` directly before the fixture patches the module attribute, so they still test the real function.

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_memory_device.py -v`
Expected: all pass

- [ ] **Step 5: Commit** — `feat(memory): keep local embedders off the GPU a local LLM uses`

---

### Task 3: Embedders declare locality and accept a device

**Files:**
- Modify: `backend/app/core/embedding/base.py`, `backend/app/core/embedding/huggingface.py`
- Test: `backend/tests/test_embedding.py` (append)

**Interfaces:**
- Produces: class attribute `Embedder.is_local: bool` (False), `HuggingFaceEmbedder.is_local = True`; `HuggingFaceEmbedder(model_name, model=None, device=None)`, `E5Embedder(model=None, device=None)`, `ParaphraseEmbedder(model=None, device=None)`. The `"auto"` device and `None` both let sentence-transformers choose.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_embedding.py`)

```python
def test_local_embedders_declare_locality():
    from app.core.embedding import E5Embedder, GeminiEmbedder, ParaphraseEmbedder

    assert E5Embedder.is_local and ParaphraseEmbedder.is_local
    assert not GeminiEmbedder.is_local


def test_huggingface_embedder_passes_the_device(monkeypatch):
    import sys
    import types

    seen = {}

    class _ST:
        def __init__(self, name, device=None):
            seen["args"] = (name, device)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=_ST))
    from app.core.embedding import E5Embedder

    E5Embedder(device="cpu")
    assert seen["args"] == ("intfloat/multilingual-e5-small", "cpu")
    E5Embedder(device="auto")
    assert seen["args"] == ("intfloat/multilingual-e5-small", None)
```

- [ ] **Step 2: Run to see them fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_embedding.py -v`
Expected: the 2 new tests FAIL

- [ ] **Step 3: Implement**

`embedding/base.py`, in `Embedder`:

```python
    # True when the model's weights live in this process (counted by the ModelManager).
    is_local: bool = False
```

`embedding/huggingface.py`:

```python
class HuggingFaceEmbedder(Embedder):
    """Embeds text with a local SentenceTransformer model."""

    is_local = True

    def __init__(self, model_name: str, model=None, device: str | None = None) -> None:
        if model is None:
            from sentence_transformers import SentenceTransformer

            # "auto" (or None) lets sentence-transformers pick the device.
            model = SentenceTransformer(model_name, device=None if device in (None, "auto") else device)
        self._model = model
```

and the subclasses:

```python
class E5Embedder(HuggingFaceEmbedder):
    """Local embedder using multilingual-e5-small."""

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("intfloat/multilingual-e5-small", model=model, device=device)


class ParaphraseEmbedder(HuggingFaceEmbedder):
    """Local embedder using paraphrase-multilingual-MiniLM."""

    def __init__(self, model=None, device: str | None = None) -> None:
        super().__init__("paraphrase-multilingual-MiniLM-L12-v2", model=model, device=device)
```

- [ ] **Step 4: Run** `pytest tests/test_embedding.py -v`. Expected: pass.
- [ ] **Step 5: Commit** — `feat(embedding): local embedders take a device and declare locality`

---

### Task 4: ModelManager

**Files:**
- Create: `backend/app/core/memory/manager.py`
- Test: `backend/tests/test_model_manager.py`

**Interfaces:**
- Consumes: `Embedder.is_local`, `embedding_registry`, `build_embedder`, `active_profile()`.
- Produces:
  - `ModelManager(factory: Callable[..., Embedder], max_local: int, wait_timeout_s: float = 30.0, is_local: Callable[[str], bool] = is_local_embedding, on_evict: Callable[[], None] = release_device_memory)`
  - `ModelManager.acquire(name: str, device: str = "auto") -> ContextManager[Embedder]`
  - `ModelManager.loaded() -> list[LoadedModel]`, where `LoadedModel(name: str, device: str, local: bool, in_use: int)`
  - `ModelManager.max_local: int` (property)
  - `get_model_manager() -> ModelManager` (process singleton, built from `active_profile()`)
  - `is_local_embedding(name: str) -> bool`, `release_device_memory() -> None`

- [ ] **Step 1: Write the failing tests**

```python
"""ModelManager: shares embedders and caps how many local ones stay resident."""
import threading
import time

from app.core.memory.manager import ModelManager


class _Emb:
    def __init__(self, name, device):
        self.name, self.device = name, device

    def embed_documents(self, texts):
        return [[1.0] for _ in texts]

    def embed_query(self, text):
        return [1.0]

    @property
    def dimension(self):
        return 1


def _manager(max_local=1, timeout=0.2):
    loads, evictions = [], []

    def factory(name, **kwargs):
        loads.append((name, kwargs.get("device")))
        return _Emb(name, kwargs.get("device"))

    manager = ModelManager(
        factory, max_local=max_local, wait_timeout_s=timeout,
        is_local=lambda name: name != "gemini", on_evict=lambda: evictions.append(1),
    )
    return manager, loads, evictions


def test_same_model_loads_once():
    manager, loads, _ = _manager(max_local=1)
    with manager.acquire("e5", "cpu") as a:
        pass
    with manager.acquire("e5", "cpu") as b:
        pass
    assert a is b and loads == [("e5", "cpu")]


def test_limit_evicts_the_idle_model():
    manager, loads, evictions = _manager(max_local=1)
    with manager.acquire("e5", "cpu"):
        pass
    with manager.acquire("paraphrase", "cpu"):
        pass
    assert [m.name for m in manager.loaded()] == ["paraphrase"]
    assert evictions == [1]


def test_remote_models_do_not_count_and_get_no_device():
    manager, loads, _ = _manager(max_local=1)
    with manager.acquire("gemini", "cpu"), manager.acquire("e5", "cpu"):
        pass
    assert loads == [("gemini", None), ("e5", "cpu")]
    assert {m.name for m in manager.loaded()} == {"gemini", "e5"}


def test_same_thread_needing_two_locals_overflows_instead_of_deadlocking(caplog):
    manager, loads, _ = _manager(max_local=1, timeout=5)
    started = time.monotonic()
    with manager.acquire("e5", "cpu"), manager.acquire("paraphrase", "cpu"):
        assert len(manager.loaded()) == 2
    assert time.monotonic() - started < 1
    assert "limit" in caplog.text
    # The overflow is undone as soon as the extra model is released.
    assert len(manager.loaded()) == 1


def test_other_thread_waits_for_the_slot_then_gets_it():
    manager, loads, _ = _manager(max_local=1, timeout=5)
    got = []
    holding = threading.Event()
    release = threading.Event()

    def holder():
        with manager.acquire("e5", "cpu"):
            holding.set()
            release.wait(2)

    t = threading.Thread(target=holder)
    t.start()
    holding.wait(2)

    def waiter():
        with manager.acquire("paraphrase", "cpu") as emb:
            got.append((emb.name, len(manager.loaded())))

    w = threading.Thread(target=waiter)
    w.start()
    time.sleep(0.1)
    assert got == []          # still waiting while e5 is in use
    release.set()
    t.join(2)
    w.join(2)
    assert got == [("paraphrase", 1)]


def test_waiting_thread_overflows_after_the_timeout():
    manager, _, _ = _manager(max_local=1, timeout=0.1)
    holding, release = threading.Event(), threading.Event()

    def holder():
        with manager.acquire("e5", "cpu"):
            holding.set()
            release.wait(2)

    t = threading.Thread(target=holder)
    t.start()
    holding.wait(2)
    with manager.acquire("paraphrase", "cpu"):
        assert len(manager.loaded()) == 2
    release.set()
    t.join(2)


def test_device_change_reloads_on_the_new_device():
    manager, loads, _ = _manager(max_local=3)
    with manager.acquire("e5", "auto"):
        pass
    with manager.acquire("e5", "cpu"):
        pass
    assert loads == [("e5", "auto"), ("e5", "cpu")]
    assert [(m.name, m.device) for m in manager.loaded()] == [("e5", "cpu")]


def test_failed_load_leaves_no_entry():
    def factory(name, **kwargs):
        raise OSError("no weights")

    manager = ModelManager(factory, max_local=1, is_local=lambda n: True, on_evict=lambda: None)
    try:
        with manager.acquire("e5", "cpu"):
            pass
    except OSError:
        pass
    assert manager.loaded() == []
```

- [ ] **Step 2: Run to see them fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_model_manager.py -v`
Expected: FAIL, module missing

- [ ] **Step 3: Implement** `backend/app/core/memory/manager.py`

```python
"""Process-wide cache of embedders that caps how many local models stay in memory."""
import gc
import logging
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from app.core.embedding.base import Embedder, build_embedder, embedding_registry

logger = logging.getLogger(__name__)

_REMOTE = "remote"


def is_local_embedding(name: str) -> bool:
    """Whether the registered embedder keeps its weights in this process."""
    try:
        return bool(getattr(embedding_registry.get(name), "is_local", False))
    except KeyError:
        return False


def release_device_memory() -> None:
    """Collect dropped models and hand cached tensor memory back to the OS."""
    gc.collect()
    torch = sys.modules.get("torch")  # never import torch just to free nothing
    if torch is None:
        return
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@dataclass(frozen=True)
class LoadedModel:
    """A resident embedder, as /system/memory reports it."""

    name: str
    device: str
    local: bool
    in_use: int


@dataclass
class _Entry:
    embedder: Embedder
    local: bool
    refs: int = 0


class ModelManager:
    """Shares embedders by (name, device) and keeps at most `max_local` local ones loaded.

    A model in use is never evicted. When every slot is in use, a caller
    waits up to `wait_timeout_s` for one to free up; a caller that already
    holds a model (it could never free its own slot) or whose wait times out
    loads beyond the limit, with a warning, and the extra model is evicted
    as soon as it is released.
    """

    def __init__(
        self,
        factory: Callable[..., Embedder],
        max_local: int,
        wait_timeout_s: float = 30.0,
        is_local: Callable[[str], bool] = is_local_embedding,
        on_evict: Callable[[], None] = release_device_memory,
    ) -> None:
        self._factory = factory
        self._max_local = max(1, max_local)
        self._wait_timeout_s = wait_timeout_s
        self._is_local = is_local
        self._on_evict = on_evict
        self._entries: OrderedDict[tuple[str, str], _Entry] = OrderedDict()  # LRU first
        self._cond = threading.Condition()
        self._leases = threading.local()

    @property
    def max_local(self) -> int:
        """How many local models may stay resident."""
        return self._max_local

    @contextmanager
    def acquire(self, name: str, device: str = "auto") -> Iterator[Embedder]:
        """Lease the embedder for the duration of the block, loading it if needed."""
        local = self._is_local(name)
        key = (name, device if local else _REMOTE)
        entry = self._checkout(key, local)
        self._leases.count = self._held() + 1
        try:
            yield entry.embedder
        finally:
            self._leases.count = self._held() - 1
            self._checkin(key)

    def loaded(self) -> list[LoadedModel]:
        """Resident models, least recently used first."""
        with self._cond:
            return [
                LoadedModel(name=n, device=d, local=e.local, in_use=e.refs)
                for (n, d), e in self._entries.items()
            ]

    def _held(self) -> int:
        return getattr(self._leases, "count", 0)

    def _local_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.local)

    def _checkout(self, key: tuple[str, str], local: bool) -> _Entry:
        with self._cond:
            entry = self._entries.get(key)
            if entry is None:
                if local:
                    self._evict_other_devices(key)
                    self._make_room()
                embedder = self._load(key, local)
                entry = self._entries[key] = _Entry(embedder, local)
            entry.refs += 1
            self._entries.move_to_end(key)
            return entry

    def _load(self, key: tuple[str, str], local: bool) -> Embedder:
        name, device = key
        logger.info("loading embedder %s on %s", name, device)
        return self._factory(name, device=device) if local else self._factory(name)

    def _checkin(self, key: tuple[str, str]) -> None:
        with self._cond:
            entry = self._entries[key]
            entry.refs -= 1
            if entry.local and entry.refs == 0 and self._local_count() > self._max_local:
                self._evict(key)
            self._cond.notify_all()

    def _evict_other_devices(self, key: tuple[str, str]) -> None:
        """Drop idle copies of the same model on another device."""
        for other in [k for k, e in self._entries.items() if k[0] == key[0] and e.refs == 0]:
            self._evict(other)

    def _make_room(self) -> None:
        """Evict idle local models until one more fits, waiting for busy ones if allowed."""
        deadline = time.monotonic() + self._wait_timeout_s
        while self._local_count() >= self._max_local:
            idle = next((k for k, e in self._entries.items() if e.local and e.refs == 0), None)
            if idle is not None:
                self._evict(idle)
                continue
            remaining = deadline - time.monotonic()
            if self._held() > 0 or remaining <= 0:
                logger.warning(
                    "loading beyond the %d-local-model limit: every resident model is in use",
                    self._max_local,
                )
                return
            self._cond.wait(remaining)

    def _evict(self, key: tuple[str, str]) -> None:
        logger.info("unloading embedder %s from %s", *key)
        del self._entries[key]
        self._on_evict()


_manager: ModelManager | None = None
_manager_lock = threading.Lock()


def get_model_manager() -> ModelManager:
    """The process-wide manager, sized by the active memory profile."""
    global _manager
    with _manager_lock:
        if _manager is None:
            from app.core.memory.profile import active_profile

            _manager = ModelManager(build_embedder, max_local=active_profile().max_local_models)
        return _manager
```

- [ ] **Step 4: Run** `pytest tests/test_model_manager.py -v`. Expected: 8 passed.
- [ ] **Step 5: Commit** — `feat(memory): add ModelManager to cap resident local embedders`

---

### Task 5: Route every embedder through the manager (chat, ingestion)

**Files:**
- Modify: `backend/app/core/chat/deps.py`, `backend/app/core/chat/graph.py`, `backend/app/api/chat.py`, `backend/app/ingestion/pipeline.py`, `backend/app/api/ingest.py`, `backend/tests/test_chat_graph.py`
- Test: `backend/tests/test_memory_wiring.py`

**Interfaces:**
- Consumes: `ModelManager`, `get_model_manager`, `resolve_embedding_device`, `active_profile`.
- Produces: `ChatDeps.models: ModelManager | None` (filled in `__post_init__` from `embedder_factory`); `ingest_documents(documents, config, store, embedder_factory=build_embedder, models: ModelManager | None = None)`; `app.api.ingest.get_models(embedder_factory) -> ModelManager`.

- [ ] **Step 1: Write the failing tests** `tests/test_memory_wiring.py`

```python
"""Chat and ingestion lease embedders from the ModelManager instead of rebuilding them."""
from qdrant_client import QdrantClient

from app.core.chat.deps import ChatDeps
from app.core.memory.manager import ModelManager
from app.core.vectorstore.qdrant import QdrantStore
from app.ingestion.pipeline import ingest_documents
from app.ingestion.schemas import Document, IngestConfig


class _Emb:
    def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]

    @property
    def dimension(self):
        return 3


def _counting_factory(loads):
    def factory(name, **kwargs):
        loads.append(name)
        return _Emb()
    return factory


def test_chat_deps_default_manager_wraps_the_factory():
    loads = []
    deps = ChatDeps(store=None, session_factory=None, embedder_factory=_counting_factory(loads))
    with deps.models.acquire("gemini"), deps.models.acquire("gemini"):
        pass
    assert loads == ["gemini"]


def test_ingestion_loads_each_embedding_once_across_calls():
    loads = []
    models = ModelManager(_counting_factory(loads), max_local=1, is_local=lambda n: False)
    store = QdrantStore(client=QdrantClient(":memory:"))
    config = IngestConfig(base="b", chunkings=["recursive"], embeddings=["gemini"])
    for _ in range(2):
        ingest_documents([Document(name="a.txt", text="Um texto.")], config, store, models=models)
    assert loads == ["gemini"]
```

Also a chat test: running `run_flow` twice with the same `ChatDeps` loads once. Append to `tests/test_chat_graph.py`, reusing that file's fakes. First read the file and adapt `_Deps` (line ~67) to carry `models = ModelManager(lambda name, **kw: object(), max_local=1, is_local=lambda n: False)`.

- [ ] **Step 2: Run to see them fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_memory_wiring.py -v`
Expected: FAIL (`ChatDeps` has no `models`, `ingest_documents` has no `models`)

- [ ] **Step 3: Implement**

`core/chat/deps.py`: add the field and `__post_init__`:

```python
    agent_runner: Callable = run_flow
    # Shared embedder cache; None builds a private one around embedder_factory.
    models: ModelManager | None = None

    def __post_init__(self) -> None:
        if self.models is None:
            self.models = ModelManager(self.embedder_factory, max_local=active_profile().max_local_models)
```

(imports: `from app.core.memory.manager import ModelManager`, `from app.core.memory.profile import active_profile`).

`api/chat.py` line 42: `ChatDeps(store=QdrantStore(), session_factory=SessionLocal, models=get_model_manager())`.

`core/chat/graph.py` `run_flow`:

```python
def run_flow(cfg: ChatConfigView, messages: list[ChatMessage], deps) -> ChatTurnResult:
    """Build the graph from a config snapshot and run one conversational turn."""
    llm = deps.llm_factory(cfg.llm)
    device = resolve_embedding_device(active_profile(), [cfg.llm])
    with deps.models.acquire(cfg.embedding, device) as embedder:
        collection = collection_name(cfg.base, cfg.chunking, cfg.embedding)
        kwargs = {"store": deps.store, "collection": collection, "embedder": embedder}
        if cfg.retriever == "multi_query":
            kwargs["llm"] = llm
        retriever = deps.retriever_factory(cfg.retriever, **kwargs)
        rag = deps.rag_factory(cfg.rag, retriever=retriever, llm=llm)
        persona_text = load_persona(cfg.persona)
        graph = build_graph(llm, rag, persona_text, load_flow_prompts())
        question = messages[-1].content if messages else ""
        history = messages[:-1]
        result = graph.invoke({"question": question, "history": history})
    return ChatTurnResult(answer=result.get("answer", ""), contexts=result.get("contexts", []))
```

`ingestion/pipeline.py`:

```python
def ingest_documents(
    documents: list[Document],
    config: IngestConfig,
    store: QdrantStore,
    embedder_factory: Callable[..., Embedder] = build_embedder,
    models: ModelManager | None = None,
) -> IngestResult:
    """Chunk, embed, and store every chunking x embedding combination."""
    profile = active_profile()
    models = models or ModelManager(embedder_factory, max_local=profile.max_local_models)
    device = resolve_embedding_device(profile)
    collections: list[str] = []
    total_chunks = 0
    for embedding in config.embeddings:
        with models.acquire(embedding, device) as embedder:
            for chunking in config.chunkings:
                ...  # loop body unchanged, one indent deeper
    return IngestResult(collections=collections, total_chunks=total_chunks)
```

`api/ingest.py`:

```python
def get_models(
    embedder_factory: Callable[..., Embedder] = Depends(get_embedder_factory),
) -> ModelManager:
    """The shared model cache; a test-injected factory gets a private one."""
    if embedder_factory is build_embedder:
        return get_model_manager()
    return ModelManager(embedder_factory, max_local=active_profile().max_local_models)
```

and the endpoint takes `models: ModelManager = Depends(get_models)` in place of `embedder_factory` and calls `ingest_documents(documents, config, store, models=models)`.

- [ ] **Step 4: Run the whole backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all pass (chat/ingest API tests unchanged)

- [ ] **Step 5: Commit** — `feat(memory): chat and ingestion lease embedders from the ModelManager`

---

### Task 6: Orchestrator: LLM-major order, single slot, concurrency cap, RSS log

**Files:**
- Create: `backend/app/core/memory/stats.py`
- Modify: `backend/pyproject.toml` (add `psutil>=5.9`), `backend/app/experiments/orchestrator.py`, `backend/app/api/experiments.py`
- Test: `backend/tests/test_orchestrator.py` (append)

**Interfaces:**
- Consumes: `ModelManager`, `get_model_manager`, `active_profile`, `resolve_embedding_device`.
- Produces: `ExperimentDeps.models: ModelManager | None`; `stats.process_rss_bytes() -> int`, `stats.total_memory_bytes() -> int`, `stats.available_memory_bytes() -> int`; `orchestrator._combinations(config) -> Iterator[tuple[str, tuple[str, str], str, str]]` in `(llm, (chunking, embedding), rag, retriever)` order.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_orchestrator.py`, reusing its fixtures and fakes)

```python
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

    from app.experiments import orchestrator

    active, peak, lock = [0], [0], threading.Lock()
    real = orchestrator._run_experiment

    def tracked(*args, **kwargs):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            import time
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
```


- [ ] **Step 2: Run to see them fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_orchestrator.py -v`
Expected: the 4 new tests FAIL

- [ ] **Step 3: Implement**

`pyproject.toml` dependencies: add `"psutil>=5.9",`, then `./.venv/bin/python -m pip install -e ".[dev]"`.

`backend/app/core/memory/stats.py`:

```python
"""Process and machine memory figures (inside Docker: the VM's)."""
import psutil


def process_rss_bytes() -> int:
    """Resident memory of this API process."""
    return psutil.Process().memory_info().rss


def total_memory_bytes() -> int:
    """Physical memory of the machine (or of the Docker VM)."""
    return psutil.virtual_memory().total


def available_memory_bytes() -> int:
    """Memory the OS can hand out without swapping."""
    return psutil.virtual_memory().available
```

`orchestrator.py`:

- `ExperimentDeps` gains `models: ModelManager | None = None` and a `__post_init__` identical to `ChatDeps`.
- A module-level slot:

```python
# One experiment at a time: queued ones stay "pending" (shown as "Na fila").
# Single uvicorn process, so a module-level semaphore is enough.
_run_slot = threading.Semaphore(1)
```

- A combination generator:

```python
def _combinations(config: ExperimentConfig):
    """Every run in LLM-major order, so each LLM loads once per experiment."""
    return itertools.product(config.llms, index_pairs(config), config.rags, config.retrievers)
```

- `run_experiment` becomes the queue wrapper; the old body moves to `_run_experiment`:

```python
def run_experiment(experiment_id, config, questions, deps) -> None:
    """Run the experiment once the single experiment slot is free."""
    with _run_slot:
        _run_experiment(experiment_id, config, questions, deps)
```

- In `_run_experiment`, replace the eval embedder line and the product loop:

```python
        prompt_snapshot = (experiment.config or {}).get("prompts", {})
        profile = active_profile()
        device = resolve_embedding_device(profile, config.llms)
        concurrency = min(config.concurrency, profile.max_concurrency)
        if concurrency < config.concurrency:
            logger.info("concurrency %d capped to %d by the %s memory profile",
                        config.concurrency, concurrency, profile.name)

        paused = False
        loaded_llm_name, llm = None, None
        with deps.models.acquire(config.eval_embedding, device) as eval_embedder:
            for llm_name, (chunking, embedding), rag_name, retriever_name in _combinations(config):
                if _pause_requested(experiment_id):
                    paused = True
                    break
                run = ExperimentRun(...)  # unchanged
                session.add(run)
                session.commit()

                if llm_name != loaded_llm_name:
                    llm, loaded_llm_name = deps.llm_factory(llm_name), llm_name
                with deps.models.acquire(embedding, device) as embedder:
                    col = collection_name(config.base, chunking, embedding)
                    retriever = _build_retriever(...)  # unchanged
                    ...
                    for question, outcome in _run_questions(
                        rag, questions, config.metrics, eval_embedder, concurrency, experiment_id,
                    ):
                        ...  # unchanged persistence
                logger.info("run %d done; API RSS %.0f MB", run.id, process_rss_bytes() / 1e6)
                if paused:
                    run.status = "paused"
                    session.commit()
                    break
                run.status = "done"
                session.commit()
```

`api/experiments.py` `get_experiment_deps`: `ExperimentDeps(store=QdrantStore(), session_factory=SessionLocal, models=get_model_manager())`.

- [ ] **Step 4: Run the backend suite** `./.venv/bin/python -m pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** — `feat(experiments): LLM-major runs, one experiment at a time, profile concurrency cap`

---

### Task 7: Preflight warnings on experiment creation

**Files:**
- Create: `backend/app/experiments/preflight.py`
- Modify: `backend/app/api/experiments.py`, `frontend/src/api/types.ts`, `frontend/src/pages/ExperimentPage.tsx`
- Test: `backend/tests/test_preflight.py`, `frontend/src/pages/ExperimentPage.test.tsx` (append)

**Interfaces:**
- Consumes: `MemoryProfile`, `is_local_embedding`, `index_pairs`.
- Produces: `memory_warnings(config: ExperimentConfig, profile: MemoryProfile, is_local: Callable[[str], bool] = is_local_embedding) -> list[str]` (PT-BR messages); `POST /experiments` returns `warnings: list[str]`; the TS type `ExperimentRef.warnings?: string[]`.

- [ ] **Step 1: Write the failing backend tests**

```python
"""Memory warnings shown before an experiment starts."""
from app.core.memory.profile import PROFILES
from app.experiments.preflight import memory_warnings
from app.experiments.schemas import ExperimentConfig

LOCAL = {"e5", "paraphrase"}


def _config(**kw):
    base = dict(base="b", chunkings=["recursive"], embeddings=["e5"], rags=["naive"],
                retrievers=["similarity"], metrics=["answer_relevancy"])
    return ExperimentConfig(**{**base, **kw})


def _warn(config, profile="low"):
    return memory_warnings(config, PROFILES[profile], is_local=lambda n: n in LOCAL)


def test_no_warning_when_eval_matches_retrieval():
    assert _warn(_config(eval_embedding="e5")) == []


def test_no_warning_with_remote_eval():
    assert _warn(_config(eval_embedding="gemini")) == []


def test_warns_when_two_local_models_must_coexist_on_low():
    [msg] = _warn(_config(eval_embedding="paraphrase"))
    assert "paraphrase" in msg and "e5" in msg and "low" in msg


def test_standard_allows_two_local_models():
    assert _warn(_config(eval_embedding="paraphrase"), "standard") == []


def test_warns_when_concurrency_is_capped():
    [msg] = _warn(_config(eval_embedding="e5", concurrency=8))
    assert "8" in msg and "2" in msg
```

- [ ] **Step 2: Run** `pytest tests/test_preflight.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement** `backend/app/experiments/preflight.py`

```python
"""Memory checks run before an experiment starts; they warn, never block."""
from collections.abc import Callable

from app.core.memory.manager import is_local_embedding
from app.core.memory.profile import MemoryProfile
from app.experiments.schemas import ExperimentConfig, index_pairs


def memory_warnings(
    config: ExperimentConfig,
    profile: MemoryProfile,
    is_local: Callable[[str], bool] = is_local_embedding,
) -> list[str]:
    """PT-BR warnings about limits this experiment will hit under the profile."""
    warnings: list[str] = []
    eval_name = config.eval_embedding
    retrieval_locals = sorted({e for _, e in index_pairs(config) if is_local(e) and e != eval_name})
    if is_local(eval_name) and retrieval_locals and profile.max_local_models < 2:
        warnings.append(
            f"O embedding de avaliação ({eval_name}) e o de busca ({', '.join(retrieval_locals)}) "
            f"são modelos locais diferentes e ficarão carregados juntos, acima do limite de "
            f"{profile.max_local_models} modelo local do perfil {profile.name}. Para economizar "
            f"memória, use o mesmo embedding na avaliação ou o Gemini."
        )
    if config.concurrency > profile.max_concurrency:
        warnings.append(
            f"A concorrência pedida ({config.concurrency}) passa do limite do perfil "
            f"{profile.name}; o experimento vai rodar com {profile.max_concurrency}."
        )
    return warnings
```

`api/experiments.py`, at the end of `create_experiment`:

```python
    background_tasks.add_task(run_experiment, experiment_id, parsed, items, deps)
    warnings = memory_warnings(parsed, active_profile())
    return {"id": experiment_id, "name": name, "status": "pending", "warnings": warnings}
```

Frontend `types.ts`: `ExperimentRef` gains `warnings?: string[];`. In `ExperimentPage.tsx`, inside the `{created && (...)}` block, after the `<p>`:

```tsx
          {created?.warnings?.map((w) => (
            <Note key={w}>{w}</Note>
          ))}
```

(Check `Note`'s props in `components/Notice.tsx` before using it; if it needs a `title`, pass `title="Atenção à memória"`.)

Frontend test (append to `ExperimentPage.test.tsx`):

```tsx
  it("shows memory warnings returned on creation", async () => {
    vi.mocked(client.createExperiment).mockResolvedValue({
      id: 8, name: "x", status: "pending", warnings: ["A concorrência pedida (8) passa do limite"],
    });
    renderPage();
    const user = userEvent.setup();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: /gerar experimento/i }));
    expect(await screen.findByText(/concorrência pedida \(8\)/)).toBeInTheDocument();
  });
```

- [ ] **Step 4: Run** `make test` and `make front-test`. Expected: all pass.
- [ ] **Step 5: Commit** — `feat(experiments): warn about memory limits when creating an experiment`

---

### Task 8: `GET /system/memory` and the Memória block in Configurações

**Files:**
- Create: `backend/app/api/system.py`
- Modify: `backend/app/main.py`, `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/SettingsPage.tsx`
- Test: `backend/tests/test_system_api.py`, `frontend/src/pages/SettingsPage.test.tsx` (append)

**Interfaces:**
- Consumes: `active_profile`, `get_model_manager`, `stats.*`.
- Produces: `GET /system/memory` → `{"profile": {"name", "max_local_models", "embedding_device", "max_concurrency"}, "total_bytes", "available_bytes", "process_rss_bytes", "loaded_models": [{"name","device","local","in_use"}]}`; TS `MemoryStatus` and `getMemory(): Promise<MemoryStatus>`.

- [ ] **Step 1: Failing backend test** `tests/test_system_api.py`

```python
"""GET /system/memory reports the profile and what is loaded."""
from app.core.memory.manager import ModelManager, get_model_manager


class _Emb:
    dimension = 1


def test_memory_endpoint_reports_profile_and_models(client):
    manager = ModelManager(lambda name, **kw: _Emb(), max_local=1, is_local=lambda n: True)
    client.app.dependency_overrides[get_model_manager] = lambda: manager
    with manager.acquire("e5", "cpu"):
        body = client.get("/system/memory").json()
    assert body["profile"]["name"] == "standard"
    assert body["loaded_models"] == [{"name": "e5", "device": "cpu", "local": True, "in_use": 1}]
    assert body["total_bytes"] > 0 and body["process_rss_bytes"] > 0
```

- [ ] **Step 2: Run** `pytest tests/test_system_api.py -v`. Expected: 404/FAIL.

- [ ] **Step 3: Implement** `backend/app/api/system.py`

```python
"""Memory telemetry: the active profile, resident models, and process/machine memory."""
from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.core.memory import stats
from app.core.memory.manager import ModelManager, get_model_manager
from app.core.memory.profile import active_profile

router = APIRouter()


@router.get("/system/memory")
def memory(models: ModelManager = Depends(get_model_manager)) -> dict:
    """What the memory profile allows and what is using memory right now."""
    return {
        "profile": asdict(active_profile()),
        "total_bytes": stats.total_memory_bytes(),
        "available_bytes": stats.available_memory_bytes(),
        "process_rss_bytes": stats.process_rss_bytes(),
        "loaded_models": [asdict(m) for m in models.loaded()],
    }
```

Register it in `main.py` (`app.include_router(system.router)`).

Frontend `types.ts`:

```ts
export interface MemoryStatus {
  profile: { name: string; max_local_models: number; embedding_device: string; max_concurrency: number };
  total_bytes: number;
  available_bytes: number;
  process_rss_bytes: number;
  loaded_models: { name: string; device: string; local: boolean; in_use: number }[];
}
```

`client.ts`:

```ts
export async function getMemory(): Promise<MemoryStatus> {
  return asJson<MemoryStatus>(await fetch(`${BASE}/system/memory`));
}
```

`SettingsPage.tsx`: state `memory: MemoryStatus | null` and `memoryError: boolean`, loaded in its own `useEffect` so a failure does not affect the rest of the page. A new first `<section className="ditto-sec">`:

```tsx
const PROFILE_TEXT: Record<string, string> = {
  low: "Para máquinas com até 8 GB. Um modelo local na memória por vez, embeddings na CPU e menos perguntas em paralelo. Os experimentos ficam mais lentos, mas a RAM não estoura.",
  standard: "Para máquinas com folga de RAM. Até 3 modelos locais na memória, embeddings na GPU quando o LLM não a está usando e mais perguntas em paralelo. Mais rápido, mas pode usar swap se a RAM não comportar.",
};
const OTHER: Record<string, string> = { low: "standard", standard: "low" };
const gb = (b: number) => `${(b / 1024 ** 3).toFixed(1)} GB`;

        <section className="ditto-sec">
          <div className="ditto-sec-head">
            <h2 className="ditto-h2">Memória</h2>
            <p className="ditto-read">Quanto o Ditto pode ocupar com modelos locais nesta máquina.</p>
          </div>
          <div className="ditto-sec-body">
            {memoryError && <p className="ditto-read">Não foi possível ler o estado da memória.</p>}
            {memory && (
              <>
                <StatusTag status="done" label={`Perfil ${memory.profile.name}`} />
                <p className="ditto-read">{PROFILE_TEXT[memory.profile.name]}</p>
                <p className="ditto-read">
                  Em vigor: até {memory.profile.max_local_models} modelo(s) local(is) carregado(s) ·
                  embeddings {memory.profile.embedding_device === "cpu" ? "na CPU" : "na GPU quando livre"} ·
                  até {memory.profile.max_concurrency} pergunta(s) em paralelo.
                </p>
                <p className="ditto-read">
                  Memória: {gb(memory.available_bytes)} livres de {gb(memory.total_bytes)} · API usando{" "}
                  {gb(memory.process_rss_bytes)} · modelos carregados:{" "}
                  {memory.loaded_models.length === 0
                    ? "nenhum"
                    : memory.loaded_models.map((m) => `${m.name} (${m.device})`).join(", ")}
                </p>
                <p className="ditto-read">
                  Para trocar de perfil, rode no terminal, na pasta do projeto:{" "}
                  <code>make memory-profile PROFILE={OTHER[memory.profile.name] ?? "low"}</code>. Depois
                  reinicie a API com <code>make up</code> ou <code>make up-local</code>.
                </p>
              </>
            )}
          </div>
        </section>
```

Frontend test (append; add `getMemory` to the `beforeEach` mocks):

```tsx
  vi.mocked(client.getMemory).mockResolvedValue({
    profile: { name: "low", max_local_models: 1, embedding_device: "cpu", max_concurrency: 2 },
    total_bytes: 8 * 1024 ** 3, available_bytes: 2 * 1024 ** 3, process_rss_bytes: 1024 ** 3,
    loaded_models: [{ name: "e5", device: "cpu", local: true, in_use: 0 }],
  });

  it("shows the memory profile and how to switch it", async () => {
    renderPage();
    expect(await screen.findByText("Perfil low")).toBeInTheDocument();
    expect(screen.getByText("make memory-profile PROFILE=standard")).toBeInTheDocument();
    expect(screen.getByText(/e5 \(cpu\)/)).toBeInTheDocument();
  });

  it("keeps the page working when memory status fails", async () => {
    vi.mocked(client.getMemory).mockRejectedValue(new Error("down"));
    renderPage();
    expect(await screen.findByText(/Não foi possível ler o estado da memória/)).toBeInTheDocument();
    expect(await screen.findByDisplayValue("qwen")).toBeInTheDocument();
  });
```

- [ ] **Step 4: Run** `make test` and `make front-test`. Expected: all pass.
- [ ] **Step 5: Commit** — `feat(system): expose memory status and show the profile in Configurações`

---

### Task 9: Scripts: detection, switching, LLM flags, container limits, mem-watch

**Files:**
- Modify: `scripts/common.sh`, `scripts/setup.sh`, `scripts/setup-dev.sh`, `scripts/llm.sh`, `scripts/llm-setup-mlx.sh`, `scripts/llm-setup.sh`, `scripts/local.sh`, `scripts/doctor.sh`, `Makefile`, `docker-compose.yml`
- Create: `scripts/memory-profile.sh`, `scripts/mem-watch.sh`, `docker-compose.low-memory.yml`

**Interfaces:**
- Produces (shell): `total_ram_bytes`, `detect_memory_profile`, `memory_profile`, `profile_value LOW STANDARD`, `ollama_profile_vars` in `common.sh`; `scripts/memory-profile.sh show|set <p>|init|hint-up`; make targets `memory-profile [PROFILE=]`, `mem-watch`.

- [ ] **Step 1: `common.sh` helpers** (append)

```bash
# --- Memory profile ------------------------------------------------------------
# low (<= 8 GB of RAM) or standard, stored as MEMORY_PROFILE in .env.
# See docs/superpowers/specs/2026-09-24-gestao-de-memoria-design.md.
total_ram_bytes() {
  case "$(uname -s)" in
    Darwin) sysctl -n hw.memsize 2>/dev/null ;;
    Linux) awk '/^MemTotal:/ {printf "%d\n", $2 * 1024}' /proc/meminfo 2>/dev/null ;;
  esac
}
detect_memory_profile() {
  local ram; ram="$(total_ram_bytes)"
  if [ -n "$ram" ] && [ "$ram" -le 9000000000 ]; then echo low; else echo standard; fi
}
memory_profile() {
  case "$(env_get MEMORY_PROFILE | tr '[:upper:]' '[:lower:]' | tr -d ' ')" in
    low) echo low ;; standard) echo standard ;; *) detect_memory_profile ;;
  esac
}
# profile_value LOW STANDARD -> the one for the active profile
profile_value() { if [ "$(memory_profile)" = low ]; then echo "$1"; else echo "$2"; fi; }
# Extra Ollama variables of the active profile, one KEY=VALUE per line.
ollama_profile_vars() {
  [ "$(memory_profile)" = low ] || return 0
  printf '%s\n' OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0
}
```

- [ ] **Step 2: `scripts/memory-profile.sh`**

```bash
#!/usr/bin/env bash
# Shows or switches the memory profile (MEMORY_PROFILE in .env).
#   low      - up to 8 GB of RAM: 1 local model at a time, embedders on CPU, less parallelism
#   standard - more RAM: up to 3 local models, embedders on the GPU when the LLM leaves it free
# Usage: scripts/memory-profile.sh show | set low|standard | init | hint-up
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

describe() {
  case "$1" in
    low)
      echo "  low: 1 modelo local na memória por vez, embeddings na CPU, até 2 perguntas em paralelo,"
      echo "  cache de prompts do MLX limitado (2 entradas, 512 MB) e containers com limite de memória."
      echo "  Experimentos mais lentos, mas a RAM não estoura." ;;
    standard)
      echo "  standard: até 3 modelos locais na memória, embeddings na GPU quando o LLM não a usa,"
      echo "  até 32 perguntas em paralelo. Mais rápido; pode usar swap se a RAM não comportar." ;;
  esac
}
other() { [ "$1" = low ] && echo standard || echo low; }

# Records the profile in .env (and the Compose override that goes with it).
record() {
  env_set MEMORY_PROFILE "$1"
  if [ "$1" = low ]; then
    env_set COMPOSE_FILE "docker-compose.yml:docker-compose.low-memory.yml"
  else
    env_unset COMPOSE_FILE
  fi
}

show() {
  local p ram; p="$(memory_profile)"; ram="$(total_ram_bytes)"
  step "Perfil de memória: $p"
  [ -n "$ram" ] && ok "RAM desta máquina: $(( (ram + 536870912) / 1073741824 )) GB (perfil sugerido: $(detect_memory_profile))"
  describe "$p"
  echo "  Para trocar: make memory-profile PROFILE=$(other "$p")"
}

case "${1:-show}" in
  show) show ;;
  set)
    p="$(printf '%s' "${2:-}" | tr '[:upper:]' '[:lower:]')"
    case "$p" in low|standard) ;; *) fail "perfil inválido: '${2:-}'. Use: make memory-profile PROFILE=low ou PROFILE=standard" ;; esac
    record "$p"
    ok ".env: MEMORY_PROFILE=$p"
    describe "$p"
    if curl -sf "$(./scripts/llm.sh url)/models" >/dev/null 2>&1; then
      step "Reiniciando o servidor de LLM com o perfil novo"
      ./scripts/llm.sh down || true
      ./scripts/llm.sh up
    fi
    step "Falta reiniciar a API para o perfil valer"
    echo "  make up         # tudo no Docker"
    echo "  make up-local   # ou API e front no host (recomendado no perfil low)"
    ;;
  init)
    # First run on this machine: record the detected profile and say how to change it.
    if [ -z "$(env_file_get MEMORY_PROFILE)" ]; then
      p="$(detect_memory_profile)"
      record "$p"
      ok "perfil de memória: $p (detectado pela RAM). Para trocar: make memory-profile PROFILE=$(other "$p")"
    fi
    ;;
  hint-up)
    if [ "$(memory_profile)" = low ]; then
      warn "perfil de memória low: recomendado 'make up-local' (sem a VM do Docker para a API, sobra RAM para o LLM)."
      warn "para trocar o perfil: make memory-profile PROFILE=standard"
    fi
    ;;
  *) fail "uso: scripts/memory-profile.sh show | set low|standard | init | hint-up" ;;
esac
```

- [ ] **Step 3: `scripts/mem-watch.sh`**

```bash
#!/usr/bin/env bash
# Prints memory use every INTERVAL seconds (default 2) while you run something in the app:
# free memory, swap, API RSS and loaded embedders, and the MLX server's RSS. Ctrl+C stops.
set -uo pipefail
cd "$(dirname "$0")/.."
. scripts/common.sh

INTERVAL="${INTERVAL:-2}"
API_PORT="$(env_get API_PORT | grep . || echo 8000)"
PY="$(command -v python3)"

api_json() {
  curl -sf "http://localhost:$API_PORT/system/memory" 2>/dev/null \
    || curl -sf "http://[::1]:$API_PORT/system/memory" 2>/dev/null
}
free_pct() {
  if has memory_pressure; then memory_pressure -Q 2>/dev/null | awk -F': ' '/percentage/ {print $2}'
  else awk '/MemTotal/ {t=$2} /MemAvailable/ {a=$2} END {printf "%d%%", a*100/t}' /proc/meminfo; fi
}
swap_used() {
  if [ "$(uname -s)" = Darwin ]; then sysctl -n vm.swapusage | awk '{print $6}'
  else free -m | awk '/Swap/ {print $3 "M"}'; fi
}
mlx_rss() {
  local pid; pid="$(pgrep -f 'mlx_lm.server' | head -1)"
  [ -n "$pid" ] && echo "$(( $(ps -o rss= -p "$pid") / 1024 ))M" || echo "-"
}

echo "perfil: $(memory_profile) · a cada ${INTERVAL}s · Ctrl+C para parar"
printf '%-8s %-6s %-8s %-9s %-8s %s\n' hora livre swap api_rss mlx_rss modelos
while true; do
  body="$(api_json)"
  api="-" models="-"
  if [ -n "$body" ]; then
    read -r api models < <(printf '%s' "$body" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
ms = ",".join(f"{m[\"name\"]}@{m[\"device\"]}" for m in d["loaded_models"]) or "nenhum"
print(f"{d[\"process_rss_bytes\"] // 2**20}M", ms)')
  fi
  printf '%-8s %-6s %-8s %-9s %-8s %s\n' "$(date +%H:%M:%S)" "$(free_pct)" "$(swap_used)" "$api" "$(mlx_rss)" "$models"
  sleep "$INTERVAL"
done
```

- [ ] **Step 4: `docker-compose.low-memory.yml`**

```yaml
# Loaded through COMPOSE_FILE when MEMORY_PROFILE=low (make memory-profile).
# Caps the containers so the Docker VM leaves RAM for the LLM server on 8 GB machines.
services:
  api:
    mem_limit: 2g
  qdrant:
    mem_limit: 512m
  postgres:
    mem_limit: 256m
  frontend:
    mem_limit: 128m
  ollama:
    environment:
      OLLAMA_NUM_PARALLEL: 2
      OLLAMA_MAX_LOADED_MODELS: 1
      OLLAMA_FLASH_ATTENTION: 1
      OLLAMA_KV_CACHE_TYPE: q8_0
```

`docker-compose.yml`, api `environment`:

```yaml
      # Memory profile (make memory-profile); empty overrides mean "use the profile".
      MEMORY_PROFILE: ${MEMORY_PROFILE:-standard}
      MAX_LOCAL_MODELS: ${MAX_LOCAL_MODELS:-}
      EMBEDDING_DEVICE: ${EMBEDDING_DEVICE:-}
      MAX_EXPERIMENT_CONCURRENCY: ${MAX_EXPERIMENT_CONCURRENCY:-}
```

- [ ] **Step 5: LLM servers follow the profile**

`llm.sh` `mlx_start`: replace the launch with:

```bash
  local parallel cache_size cache_bytes
  parallel="$(env_get MLX_PARALLEL | grep . || profile_value 2 4)"
  cache_size="$(env_get MLX_PROMPT_CACHE_SIZE | grep . || profile_value 2 10)"
  cache_bytes="$(env_get MLX_PROMPT_CACHE_BYTES | grep . || profile_value 512M '')"
  local extra=(--prompt-cache-size "$cache_size")
  [ -n "$cache_bytes" ] && extra+=(--prompt-cache-bytes "$cache_bytes")
  # Loopback only (see mlx_host): never exposed to the network.
  nohup "$MLX_DIR/bin/mlx_lm.server" --host "$(mlx_host)" --port "$(mlx_port)" \
    --decode-concurrency "$parallel" "${extra[@]}" --max-tokens 1024 \
    >"$MLX_LOG" 2>&1 &
```

`llm.sh` `ollama_host_start`: `export OLLAMA_NUM_PARALLEL="${parallel:-$(profile_value 2 4)}"` and `while IFS= read -r kv; do [ -n "$kv" ] && export "$kv"; done < <(ollama_profile_vars)`.

`llm-setup-mlx.sh`: `PARALLEL="${PARALLEL:-}"`. Write `MLX_PARALLEL` only when given, otherwise `env_unset MLX_PARALLEL`, so the profile decides. Messages print the effective value `${PARALLEL:-$(profile_value 2 4)}`.

`llm-setup.sh`: `PARALLEL="${PARALLEL:-$(profile_value 2 4)}"`. `serve_env` appends `$(ollama_profile_vars | tr '\n' ' ')`. The systemd override writes one `Environment=` line per profile var. The macOS app branch runs `launchctl setenv` for each profile var, and also checks them when deciding whether to restart.

- [ ] **Step 6: Wire into setup, up, up-local, doctor, Makefile**

- `setup.sh`: before "Portas", `step "Memória"` + `./scripts/memory-profile.sh init` + `./scripts/memory-profile.sh show`.
- `setup-dev.sh`: `./scripts/memory-profile.sh init` near the end.
- `local.sh` `up`: `./scripts/memory-profile.sh init` at the start. Pass `MEMORY_PROFILE="$(memory_profile)" MAX_LOCAL_MODELS="$(env_get MAX_LOCAL_MODELS)" EMBEDDING_DEVICE="$(env_get EMBEDDING_DEVICE)" MAX_EXPERIMENT_CONCURRENCY="$(env_get MAX_EXPERIMENT_CONCURRENCY)"` in the uvicorn `env`.
- `doctor.sh`: a final `./scripts/memory-profile.sh show`, plus `hint-up`.
- `Makefile`: `up:` gets `@./scripts/memory-profile.sh init` before compose and `@./scripts/memory-profile.sh hint-up` at the end. New targets (and add them to `.PHONY` and `help`):

```make
# Memory profile: show it, or switch with PROFILE=low|standard (restarts the LLM server).
memory-profile:
	@./scripts/memory-profile.sh $(if $(PROFILE),set "$(PROFILE)",show)

# Prints free memory, swap, API RSS/loaded models and MLX RSS every INTERVAL seconds.
mem-watch:
	@INTERVAL="$(or $(INTERVAL),2)" ./scripts/mem-watch.sh
```

`help` gains: `@echo "Memória:   make memory-profile [PROFILE=low|standard] | mem-watch"`.

- [ ] **Step 7: Verify**

```bash
bash -n scripts/*.sh
cp .env /tmp/env.bak   # keep the real .env safe
./scripts/memory-profile.sh show
./scripts/memory-profile.sh set Standard && grep MEMORY_PROFILE .env
./scripts/memory-profile.sh set low && grep -E 'MEMORY_PROFILE|COMPOSE_FILE' .env
./scripts/memory-profile.sh set lwo; echo "exit $?"   # expect the PT-BR error, exit 1
docker compose config | grep -A1 mem_limit             # low override applied
./scripts/memory-profile.sh hint-up
```

Restore the user's original profile afterwards (`set` back to what `show` said first).

- [ ] **Step 8: Commit** — `feat(infra): memory profiles in the scripts: detection, switching, LLM flags, container limits`

---

### Task 10: Docs

**Files:** `CLAUDE.md`, `README.md`, `.env.example`, the spec.

- [ ] **Step 1:** `CLAUDE.md` "Como iniciar" block gains:

```
make memory-profile                        # perfil de memória ativo (low ≤ 8 GB, standard) e o que ele muda
make memory-profile PROFILE=low|standard   # troca o perfil (reinicia o servidor de LLM; depois make up/up-local)
make mem-watch                             # memória livre, swap, RSS da API/MLX e modelos carregados, a cada 2s
```

Fix the Docker note: the image **does** include the local embedders (torch CPU). Add a line under Estrutura: `backend/app/core/memory/` — perfis de memória, `ModelManager` (cache de embedders com limite de modelos locais) e política de device (embedder nunca divide a GPU com LLM local).

- [ ] **Step 2:** `README.md`: a "Memória (Macs de 8 GB)" section with the spec's profile table, how to switch, and `mem-watch`.
- [ ] **Step 3:** `.env.example`: commented `# MEMORY_PROFILE=low|standard (make memory-profile)` and the three overrides.
- [ ] **Step 4:** Spec: rename `make mem-profile` → `make mem-watch` (a monitor, not a canned experiment), and mark phases 0–3.3 as implemented in the header.
- [ ] **Step 5:** `graphify update .`, then commit — `docs: memory profiles and mem-watch`
