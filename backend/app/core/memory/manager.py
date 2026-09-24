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
from app.core.memory.profile import active_profile

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
    embedder: Embedder | None
    local: bool
    refs: int = 0
    ready: bool = False  # False while the model is still loading


class ModelManager:
    """Shares embedders by (name, device) and keeps at most `max_local` local ones loaded.

    A model in use is never evicted. When every slot is in use, a caller
    waits up to `wait_timeout_s` for one to free up; a caller that already
    holds a model (it could never free its own slot) or whose wait times out
    loads beyond the limit, with a warning, and the extra model is evicted
    as soon as it is released. Loading happens outside the lock, so status
    reads and other models are never stuck behind a slow load or download.
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
        # Leases held per thread: a caller that already holds one must not wait.
        self._held_by: dict[int, int] = {}

    @property
    def max_local(self) -> int:
        """How many local models may stay resident."""
        return self._max_local

    @contextmanager
    def acquire(
        self, name: str, device: str = "auto", wait_timeout_s: float | None = None
    ) -> Iterator[Embedder]:
        """Lease the embedder for the duration of the block, loading it if needed.

        `wait_timeout_s` overrides how long to wait for a free slot (interactive
        callers wait less).
        """
        local = self._is_local(name)
        key = (name, device if local else _REMOTE)
        entry = self._checkout(key, local, wait_timeout_s)
        # Counted against the thread that took the lease, even if another thread
        # releases it (a lease opened in a worker and closed by the orchestrator).
        owner = threading.get_ident()
        with self._cond:
            self._held_by[owner] = self._held_by.get(owner, 0) + 1
        try:
            yield entry.embedder
        finally:
            with self._cond:
                remaining = self._held_by.get(owner, 0) - 1
                if remaining > 0:
                    self._held_by[owner] = remaining
                else:
                    self._held_by.pop(owner, None)
            self._checkin(key)

    def loaded(self) -> list[LoadedModel]:
        """Resident models, least recently used first (models still loading are left out)."""
        with self._cond:
            return [
                LoadedModel(name=n, device=d, local=e.local, in_use=e.refs)
                for (n, d), e in self._entries.items()
                if e.ready
            ]

    def evict_idle(self) -> int:
        """Unload every idle local model (before handing the machine to the LLM)."""
        with self._cond:
            idle = [k for k, e in self._entries.items() if e.local and e.ready and e.refs == 0]
            for key in idle:
                self._evict(key)
            self._cond.notify_all()
            return len(idle)

    def _held(self) -> int:
        return self._held_by.get(threading.get_ident(), 0)

    def _local_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.local)

    def _checkout(self, key: tuple[str, str], local: bool, wait_timeout_s: float | None) -> _Entry:
        with self._cond:
            while True:
                entry = self._entries.get(key)
                if entry is None:
                    break
                if entry.ready:
                    entry.refs += 1
                    self._entries.move_to_end(key)
                    return entry
                self._cond.wait()  # another thread is loading this model
            if local:
                self._evict_other_devices(key)
                self._make_room(wait_timeout_s)
            # A placeholder holds the slot (and makes same-key callers wait) during the load.
            entry = self._entries[key] = _Entry(embedder=None, local=local, refs=1)
        try:
            embedder = self._load(key, local)
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
        for other in [
            k for k, e in self._entries.items() if k[0] == key[0] and e.ready and e.refs == 0
        ]:
            self._evict(other)

    def _make_room(self, wait_timeout_s: float | None = None) -> None:
        """Evict idle local models until one more fits, waiting for busy ones if allowed."""
        timeout = self._wait_timeout_s if wait_timeout_s is None else wait_timeout_s
        deadline = time.monotonic() + timeout
        while self._local_count() >= self._max_local:
            idle = next(
                (k for k, e in self._entries.items() if e.local and e.ready and e.refs == 0), None
            )
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
            _manager = ModelManager(build_embedder, max_local=active_profile().max_local_models)
        return _manager
