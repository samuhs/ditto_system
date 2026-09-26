"""Model-specific question difficulty without the model's output: perplexity.

How much the question's own text surprises a given LLM, from one forward pass
over the question (no generation). Only MLX models are supported: the MLX
server scores generated tokens but not a prompt's, so a short-lived process
(scripts/mlx_perplexity.py, run with the MLX virtualenv) loads the model once
and scores every question. Ollama and Gemini expose no prompt log-probabilities.

A question is scored once per model: results are cached by (model, question)
for the life of the API process, and experiments store them per question.
"""
import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

import psutil

from app.core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Loading a model beside the running MLX server needs this much free memory on
# top of the weights (activations, runtime).
_MEMORY_HEADROOM = 512 * 1024 * 1024
_TIMEOUT_S = 900
_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "mlx_perplexity.py"

_cache: dict[tuple[str, str], float] = {}


class PerplexitySkipped(Exception):
    """Scoring was not attempted: too little free memory (and swapping not allowed)."""

    def __init__(self, free_mb: int, needed_mb: int) -> None:
        super().__init__(f"{free_mb} MB free, needs about {needed_mb} MB")
        self.free_mb = free_mb
        self.needed_mb = needed_mb


class PerplexityScorer(ABC):
    """Scores questions under one model: {question: perplexity}."""

    @abstractmethod
    def score(self, model: str, questions: list[str]) -> dict[str, float]:
        """One forward pass per question; questions it cannot score are left out."""


def mlx_python() -> Path:
    """The MLX virtualenv's Python (DITTO_HOME moves it, as in scripts/common.sh)."""
    home = Path(os.environ.get("DITTO_HOME") or Path.home() / ".ditto")
    return home / "mlx" / "bin" / "python"


def _model_bytes(model: str) -> int | None:
    """Size of the model's Hugging Face cache folder, if it is there."""
    hub = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
    folder = hub / f"models--{model.replace('/', '--')}"
    if not folder.is_dir():
        return None
    return sum(f.stat().st_size for f in (folder / "blobs").glob("*") if f.is_file())


class MlxPerplexityScorer(PerplexityScorer):
    """Runs scripts/mlx_perplexity.py once per call with every question."""

    def __init__(self, python: Path | None = None, script: Path = _SCRIPT) -> None:
        self._python = python or mlx_python()
        self._script = script

    def score(self, model: str, questions: list[str]) -> dict[str, float]:
        size = _model_bytes(model)
        available = psutil.virtual_memory().available
        if size is not None and available < size + _MEMORY_HEADROOM:
            free_mb, needed_mb = available // 2**20, (size + _MEMORY_HEADROOM) // 2**20
            if not get_settings().perplexity_allow_swap:
                raise PerplexitySkipped(free_mb, needed_mb)
            logger.warning(
                "perplexity for %s will swap: %d MB free, needs about %d MB",
                model, free_mb, needed_mb,
            )
        completed = subprocess.run(
            [str(self._python), str(self._script)],
            input=json.dumps({"model": model, "questions": questions}),
            capture_output=True, text=True, timeout=_TIMEOUT_S, check=True,
        )
        scores = json.loads(completed.stdout)["perplexity"]
        return {q: v for q, v in scores.items() if v == v}  # drops NaN


def perplexity_scorer_for(model: str) -> PerplexityScorer | None:
    """The scorer for a local LLM server model, or None when it cannot be scored.

    MLX models are Hugging Face ids ("org/repo"); Ollama tags ("qwen3:1.7b")
    and Gemini have no scorer.
    """
    if "/" not in model or not mlx_python().exists() or not _SCRIPT.exists():
        return None
    return MlxPerplexityScorer()


def cached_perplexities(
    scorer: PerplexityScorer, model: str, questions: list[str]
) -> dict[str, float]:
    """Perplexity per question, scoring only the (model, question) pairs not seen yet."""
    missing = [q for q in dict.fromkeys(questions) if (model, q) not in _cache]
    if missing:
        for question, value in scorer.score(model, missing).items():
            _cache[(model, question)] = value
    return {q: _cache[(model, q)] for q in questions if (model, q) in _cache}
