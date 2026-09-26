"""Tests for the perplexity signal (fake scorers; no MLX, no subprocess)."""
import pytest

from app.core.difficulty import perplexity
from app.core.difficulty.perplexity import cached_perplexities, perplexity_scorer_for


class _CountingScorer(perplexity.PerplexityScorer):
    def __init__(self):
        self.calls = []

    def score(self, model, questions):
        self.calls.append(list(questions))
        return {q: float(len(q)) for q in questions}


def test_each_question_is_scored_once_per_model(monkeypatch):
    monkeypatch.setattr(perplexity, "_cache", {})
    scorer = _CountingScorer()
    first = cached_perplexities(scorer, "org/m", ["a?", "bb?", "a?"])
    second = cached_perplexities(scorer, "org/m", ["bb?", "ccc?"])
    assert first == {"a?": 2.0, "bb?": 3.0}
    assert second == {"bb?": 3.0, "ccc?": 4.0}
    assert scorer.calls == [["a?", "bb?"], ["ccc?"]]
    cached_perplexities(scorer, "org/other", ["a?"])
    assert scorer.calls[-1] == ["a?"]  # another model is scored anew


def test_only_mlx_models_get_a_scorer(monkeypatch, tmp_path):
    python = tmp_path / "mlx" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setenv("DITTO_HOME", str(tmp_path))
    assert perplexity_scorer_for("qwen3:1.7b") is None
    assert perplexity_scorer_for("gemini-2.5-flash-lite") is None
    assert isinstance(perplexity_scorer_for("mlx-community/Qwen2.5-3B-Instruct-4bit"),
                      perplexity.MlxPerplexityScorer)
    monkeypatch.setenv("DITTO_HOME", str(tmp_path / "missing"))
    assert perplexity_scorer_for("mlx-community/Qwen2.5-3B-Instruct-4bit") is None


def test_low_memory_skips_scoring(monkeypatch):
    class _Mem:
        available = 100 * 2**20

    monkeypatch.setattr(perplexity.psutil, "virtual_memory", lambda: _Mem())
    monkeypatch.setattr(perplexity, "_model_bytes", lambda model: 2 * 2**30)
    monkeypatch.setattr(perplexity.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    with pytest.raises(perplexity.PerplexitySkipped) as info:
        perplexity.MlxPerplexityScorer().score("org/m", ["q?"])
    assert info.value.free_mb == 100 and info.value.needed_mb == 2048 + 512


def test_allowing_swap_scores_anyway(monkeypatch):
    import json
    from types import SimpleNamespace

    from app.core.config.settings import get_settings

    class _Mem:
        available = 100 * 2**20

    monkeypatch.setenv("PERPLEXITY_ALLOW_SWAP", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(perplexity.psutil, "virtual_memory", lambda: _Mem())
    monkeypatch.setattr(perplexity, "_model_bytes", lambda model: 2 * 2**30)
    monkeypatch.setattr(
        perplexity.subprocess, "run",
        lambda *a, **k: SimpleNamespace(stdout=json.dumps({"perplexity": {"q?": 7.0}})),
    )
    try:
        assert perplexity.MlxPerplexityScorer().score("org/m", ["q?"]) == {"q?": 7.0}
    finally:
        get_settings.cache_clear()
