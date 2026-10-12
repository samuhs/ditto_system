"""Statistics behind a Comparação: bootstrap confidence intervals and Friedman.

The same procedure as the campaign paper (2026-10-10), so a Comparação reproduces
its numbers: 10,000 resamples with `random.Random(0)`, the 2.5th and 97.5th
percentiles of the sorted resampled means.
"""
import math
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


@dataclass(frozen=True)
class Friedman:
    """Friedman test over complete blocks: one question scored by every Combinação."""

    chi2: float
    df: int
    p: float
    n: int


def _mid_ranks(values: list[float]) -> list[float]:
    """Rank 1 for the lowest; tied values share the mean of the ranks they span."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def friedman(blocks: list[list[float]]) -> Friedman:
    """Friedman's chi2 over `blocks` (one list per question, one value per Combinação).

    Mid-ranks for ties and no tie correction of the statistic: the formula the
    campaign paper used (chi2 = 33.34 for its phase 3).
    """
    n, k = len(blocks), len(blocks[0])
    rank_sums = [0.0] * k
    for block in blocks:
        for j, rank in enumerate(_mid_ranks(block)):
            rank_sums[j] += rank
    chi2 = 12 / (n * k * (k + 1)) * sum(r * r for r in rank_sums) - 3 * n * (k + 1)
    return Friedman(chi2=chi2, df=k - 1, p=chi2_sf(chi2, k - 1), n=n)


def chi2_sf(x: float, df: int) -> float:
    """P(X > x) for a chi-square with `df` degrees of freedom (upper regularized gamma)."""
    if x <= 0:
        return 1.0
    a, z = df / 2, x / 2
    if z < a + 1:  # series for the lower gamma, then its complement
        term = total = 1 / a
        denominator = a
        while abs(term) > abs(total) * 1e-15:
            denominator += 1
            term *= z / denominator
            total += term
        return 1 - total * math.exp(-z + a * math.log(z) - math.lgamma(a))
    # Continued fraction (Lentz) for the upper gamma.
    tiny = 1e-300
    b = z + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    i = 1
    while True:
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
        i += 1
    return math.exp(-z + a * math.log(z) - math.lgamma(a)) * h
