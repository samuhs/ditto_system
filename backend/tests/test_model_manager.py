"""ModelManager: shares embedders and caps how many local ones stay resident."""
import threading
import time

import pytest

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


def _hold(manager, name):
    """Hold `name` on another thread until the returned event is set."""
    holding, release = threading.Event(), threading.Event()

    def holder():
        with manager.acquire(name, "cpu"):
            holding.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    holding.wait(5)
    return release, thread


def test_same_model_loads_once():
    manager, loads, _ = _manager(max_local=1)
    with manager.acquire("e5", "cpu") as a:
        pass
    with manager.acquire("e5", "cpu") as b:
        pass
    assert a is b and loads == [("e5", "cpu")]


def test_limit_evicts_the_idle_model():
    manager, _, evictions = _manager(max_local=1)
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
    manager, _, _ = _manager(max_local=1, timeout=5)
    started = time.monotonic()
    with manager.acquire("e5", "cpu"), manager.acquire("paraphrase", "cpu"):
        assert len(manager.loaded()) == 2
    assert time.monotonic() - started < 1
    assert "limit" in caplog.text
    # The overflow is undone as soon as the extra model is released.
    assert len(manager.loaded()) == 1


def test_other_thread_waits_for_the_slot_then_gets_it():
    manager, _, _ = _manager(max_local=1, timeout=5)
    release, holder = _hold(manager, "e5")
    got = []

    def waiter():
        with manager.acquire("paraphrase", "cpu") as emb:
            got.append((emb.name, len(manager.loaded())))

    w = threading.Thread(target=waiter)
    w.start()
    time.sleep(0.1)
    assert got == []  # still waiting while e5 is in use
    release.set()
    holder.join(5)
    w.join(5)
    assert got == [("paraphrase", 1)]


def test_waiting_thread_overflows_after_the_timeout():
    manager, _, _ = _manager(max_local=1, timeout=0.1)
    release, holder = _hold(manager, "e5")
    try:
        with manager.acquire("paraphrase", "cpu"):
            assert len(manager.loaded()) == 2
    finally:
        release.set()
        holder.join(5)


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
    with pytest.raises(OSError):
        with manager.acquire("e5", "cpu"):
            pass
    assert manager.loaded() == []


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

    def use():
        with manager.acquire("e5", "cpu"):
            pass

    t = threading.Thread(target=use)
    t.start()
    started.wait(5)
    began = time.monotonic()
    try:
        assert manager.loaded() == []          # the loading model is not listed yet
        assert time.monotonic() - began < 0.5  # and the call did not block
    finally:
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
    time.sleep(0.05)
    release.set()
    for t in threads:
        t.join(5)
    assert loads == ["e5"] and got[0] is got[1]


def test_the_slot_is_freed_when_a_load_fails():
    calls = []

    def factory(name, **kwargs):
        calls.append(name)
        if len(calls) == 1:
            raise OSError("boom")
        return _Emb(name, kwargs.get("device"))

    manager = ModelManager(factory, max_local=1, is_local=lambda n: True, on_evict=lambda: None,
                           wait_timeout_s=5)
    with pytest.raises(OSError):
        with manager.acquire("e5", "cpu"):
            pass
    began = time.monotonic()
    with manager.acquire("paraphrase", "cpu") as emb:  # no leaked slot to wait for
        assert emb.name == "paraphrase"
    assert time.monotonic() - began < 1


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
