"""GPU encodes are serialized across every embedder (Metal aborts on concurrent encodes)."""
import threading
import time

from app.core.embedding.huggingface import E5Embedder, EmbeddingGemmaEmbedder


class _CountingModel:
    """Records how many encodes overlap; sleeps so threads would collide without a lock."""

    def __init__(self, device: str, state: dict) -> None:
        self.device = device
        self._state = state

    def encode(self, inputs, convert_to_numpy=True, **kwargs):
        with self._state["lock"]:
            self._state["active"] += 1
            self._state["peak"] = max(self._state["peak"], self._state["active"])
        time.sleep(0.01)
        with self._state["lock"]:
            self._state["active"] -= 1
        if isinstance(inputs, list):
            return [[0.0, 1.0] for _ in inputs]
        return [0.0, 1.0]


def _hammer(embedders, calls=6):
    def work(e):
        for _ in range(calls):
            e.embed_query("q")
            e.embed_documents(["a", "b"])

    threads = [threading.Thread(target=work, args=(e,)) for e in embedders for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def _state():
    return {"lock": threading.Lock(), "active": 0, "peak": 0}


def test_gpu_encodes_never_overlap_even_across_different_embedders():
    state = _state()
    embedders = [EmbeddingGemmaEmbedder(model=_CountingModel("mps:0", state)),
                 E5Embedder(model=_CountingModel("mps:0", state))]
    _hammer(embedders)
    assert state["peak"] == 1


def test_cpu_embedders_keep_their_own_lock_and_still_return_vectors():
    state = _state()
    a = E5Embedder(model=_CountingModel("cpu", state))
    b = E5Embedder(model=_CountingModel("cpu", state))
    _hammer([a, b])
    # each CPU instance is serialized on itself; two instances may run side by side
    assert 1 <= state["peak"] <= 2
    assert a.embed_query("x") == [0.0, 1.0]
    assert a.embed_documents(["x", "y"]) == [[0.0, 1.0], [0.0, 1.0]]


class _OomOnceModel:
    device = "mps:0"

    def __init__(self) -> None:
        self.calls = []

    def encode(self, inputs, convert_to_numpy=True, **kwargs):
        self.calls.append(kwargs.get("batch_size"))
        if len(self.calls) == 1:
            raise RuntimeError("MPS backend out of memory (MPS allocated: 9.04 GiB)")
        return [[0.0, 1.0] for _ in inputs]


def test_a_gpu_out_of_memory_frees_the_cache_and_retries_in_small_batches(monkeypatch):
    import app.core.embedding.huggingface as hf

    freed = []
    monkeypatch.setattr(hf, "free_gpu_cache", lambda: freed.append(1))
    model = _OomOnceModel()
    assert E5Embedder(model=model).embed_documents(["a", "b"]) == [[0.0, 1.0], [0.0, 1.0]]
    assert model.calls == [32, 4]
    assert len(freed) >= 2  # before the retry and after the encode


def test_other_errors_and_cpu_errors_are_not_swallowed(monkeypatch):
    import pytest

    class _Broken:
        device = "cpu"

        def encode(self, *a, **k):
            raise RuntimeError("MPS backend out of memory")

    with pytest.raises(RuntimeError):
        E5Embedder(model=_Broken()).embed_query("x")
