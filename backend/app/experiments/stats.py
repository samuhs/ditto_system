"""Statistics behind a Comparação: bootstrap confidence intervals.

The same procedure as the campaign paper (2026-10-10), so a Comparação reproduces
its numbers: 10,000 resamples with `random.Random(0)`, the 2.5th and 97.5th
percentiles of the sorted resampled means.
"""
import random
from dataclasses import dataclass

RESAMPLES = 10_000
SEED = 0


@dataclass(frozen=True)
class Interval:
    """A mean with its 95% bootstrap CI; significant when the CI does not cross zero."""

    mean: float
    low: float
    high: float

    @property
    def significant(self) -> bool:
        return self.low > 0 or self.high < 0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _bootstrap(values: list[float], resamples: int, seed: int) -> Interval:
    rng = random.Random(seed)
    n = len(values)
    draws = sorted(
        _mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)
    )
    return Interval(
        mean=_mean(values),
        low=draws[int(0.025 * resamples)],
        high=draws[int(0.975 * resamples) - 1],
    )


def paired_diff_ci(diffs: list[float], resamples: int = RESAMPLES, seed: int = SEED) -> Interval:
    """Mean per-question difference and its CI, resampling questions with replacement.

    `diffs` holds one difference per paired question (item minus Linha de base), in
    a stable order: the resample depends on it.
    """
    return _bootstrap(diffs, resamples, seed)


def mean_ci(values: list[float], resamples: int = RESAMPLES, seed: int = SEED) -> Interval:
    """Mean of unpaired values and its CI (items of another Base)."""
    return _bootstrap(values, resamples, seed)
