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


def test_concurrent_misses_load_the_model_once():
    import threading
    import time

    loads = []

    def slow_fallback():
        loads.append(1)
        time.sleep(0.05)
        return _Emb()

    emb = CachedQueryEmbedder({}, slow_fallback, dimension=1)
    threads = [threading.Thread(target=emb.embed_query, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert loads == [1]


def test_lease_opened_in_a_worker_and_closed_elsewhere_is_fully_released():
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    manager = ModelManager(lambda n, **k: _Emb(n), max_local=1, is_local=lambda n: True,
                           on_evict=lambda: None, wait_timeout_s=0.3)
    leases = LeaseSwitcher(manager)
    with ThreadPoolExecutor(max_workers=1) as pool:  # always the same worker thread
        pool.submit(leases.get, "e5", "cpu").result()
        leases.close()  # released from the main thread

        holding, release = threading.Event(), threading.Event()

        def holder():
            with manager.acquire("paraphrase", "cpu"):
                holding.set()
                release.wait(5)

        t = threading.Thread(target=holder)
        t.start()
        holding.wait(5)

        def timed_acquire():
            began = time.monotonic()
            with manager.acquire("other", "cpu"):
                return time.monotonic() - began

        # The worker holds nothing now, so it must wait for the slot (then time out),
        # not overflow at once as if it still held e5.
        waited = pool.submit(timed_acquire).result()
        release.set()
        t.join(5)
    assert waited >= 0.25
