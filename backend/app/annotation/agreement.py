"""Agreement between Avaliadores: weighted kappa, Krippendorff's alpha and bootstrap CIs.

Only the standard library: the formulas are small, and the test suite checks them against
hand-worked examples and Krippendorff's published values.
"""
import random
from collections import Counter
from collections.abc import Callable, Sequence

Rating = int | None
RESAMPLES = 10_000
SEED = 0


def _delta(level: str, categories: list, freq: Counter) -> Callable[[object, object], float]:
    """Squared difference function of Krippendorff's alpha for a level of measurement."""
    if level == "nominal":
        return lambda c, k: 0.0 if c == k else 1.0
    if level == "interval":
        return lambda c, k: float((c - k) ** 2)
    if level == "ordinal":
        index = {c: i for i, c in enumerate(categories)}

        def ordinal(c, k):
            lo, hi = sorted((index[c], index[k]))
            between = sum(freq[categories[g]] for g in range(lo, hi + 1))
            return (between - (freq[c] + freq[k]) / 2) ** 2
        return ordinal
    raise ValueError(f"unknown level {level!r}")


def krippendorff_alpha(units: Sequence[Sequence[Rating]], level: str = "ordinal") -> float | None:
    """Krippendorff's alpha over units (each a list of ratings, None = missing).

    Units with fewer than two ratings are not pairable and are dropped. None when there is
    nothing to compare or no variation at all (the expected disagreement is zero).
    """
    pairable = [[v for v in unit if v is not None] for unit in units]
    pairable = [u for u in pairable if len(u) >= 2]
    if not pairable:
        return None
    # Coincidence matrix: each ordered pair of values within a unit weighs 1/(m_u - 1).
    coincidence: Counter = Counter()
    for unit in pairable:
        m = len(unit)
        for i, a in enumerate(unit):
            for j, b in enumerate(unit):
                if i != j:
                    coincidence[(a, b)] += 1 / (m - 1)
    freq: Counter = Counter()
    for (a, _), weight in coincidence.items():
        freq[a] += weight
    n = sum(freq.values())
    categories = sorted(freq)
    delta = _delta(level, categories, freq)
    observed = sum(w * delta(a, b) for (a, b), w in coincidence.items())
    expected = sum(freq[a] * freq[b] * delta(a, b) for a in categories for b in categories) / (n - 1)
    if expected == 0:
        return None
    return 1 - observed / expected


def weighted_kappa(a: Sequence[int], b: Sequence[int], categories: Sequence[int]) -> float | None:
    """Cohen's kappa with quadratic weights, for two raters over the same items."""
    k = len(categories)
    index = {c: i for i, c in enumerate(categories)}
    n = len(a)
    if n == 0 or k < 2:
        return None

    def weight(i, j):
        return (i - j) ** 2 / (k - 1) ** 2

    observed = sum(weight(index[x], index[y]) for x, y in zip(a, b)) / n
    pa, pb = Counter(index[x] for x in a), Counter(index[y] for y in b)
    expected = sum(pa[i] * pb[j] * weight(i, j) for i in range(k) for j in range(k)) / n**2
    if expected == 0:
        return None
    return 1 - observed / expected


def confusion_matrix(a: Sequence[int], b: Sequence[int], categories: Sequence[int]) -> list[list[int]]:
    """Counts of (rater a's value, rater b's value): rows are a, columns are b."""
    index = {c: i for i, c in enumerate(categories)}
    matrix = [[0] * len(categories) for _ in categories]
    for x, y in zip(a, b):
        matrix[index[x]][index[y]] += 1
    return matrix


def bootstrap_ci(units: Sequence, statistic: Callable[[Sequence], float | None],
                 resamples: int = RESAMPLES, seed: int = SEED) -> tuple[float, float] | None:
    """95% percentile CI of `statistic` by resampling units with replacement (fixed seed).

    Resamples where the statistic is undefined are skipped; None if all of them are.
    """
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        value = statistic([units[rng.randrange(len(units))] for _ in units])
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    return values[int(0.025 * len(values))], values[min(len(values) - 1, int(0.975 * len(values)))]
