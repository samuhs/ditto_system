"""Memory warnings shown before an experiment starts."""
from app.core.memory.profile import PROFILES
from app.experiments.preflight import memory_warnings
from app.experiments.schemas import ExperimentConfig

LOCAL = {"e5", "paraphrase"}


def _config(**kw):
    base = dict(base="b", chunkings=["recursive"], embeddings=["e5"], rags=["naive"],
                retrievers=["similarity"], metrics=["answer_relevancy"], llms=["qwen3:1.7b"])
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
