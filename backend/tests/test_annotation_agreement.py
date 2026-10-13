"""Agreement statistics of the Anotação humana, against hand-worked and published values."""
import pytest

from app.annotation.agreement import (
    bootstrap_ci,
    confusion_matrix,
    krippendorff_alpha,
    weighted_kappa,
)

# Krippendorff (2011), "Computing Krippendorff's Alpha-Reliability": 4 coders x 12 units,
# None = missing. Published: nominal 0.743, ordinal 0.815, interval 0.849.
K_DATA = {
    "A": [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
    "B": [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
    "C": [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None],
    "D": [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None],
}


def _units(data):
    """Coder-major rows to one list of ratings per unit."""
    return [list(values) for values in zip(*data.values())]


def test_alpha_matches_krippendorffs_published_nominal_value():
    assert krippendorff_alpha(_units(K_DATA), level="nominal") == pytest.approx(0.743, abs=0.001)


def test_alpha_matches_krippendorffs_published_ordinal_value():
    assert krippendorff_alpha(_units(K_DATA), level="ordinal") == pytest.approx(0.815, abs=0.001)


def test_alpha_matches_krippendorffs_published_interval_value():
    assert krippendorff_alpha(_units(K_DATA), level="interval") == pytest.approx(0.849, abs=0.001)


def test_alpha_is_one_on_perfect_agreement_and_undefined_without_variation():
    assert krippendorff_alpha([[0, 0], [1, 1], [2, 2]]) == pytest.approx(1.0)
    assert krippendorff_alpha([[1, 1], [1, 1]]) is None
    assert krippendorff_alpha([[1, None], [2, None]]) is None  # no unit with two values


def test_weighted_kappa_matches_a_hand_worked_example():
    # Quadratic weights (i-j)^2/4 over 0..2. Do = 0.125, De = 0.34375, kappa = 1 - Do/De = 7/11.
    assert weighted_kappa([0, 1, 2, 2], [0, 2, 2, 1], categories=[0, 1, 2]) == pytest.approx(7 / 11)


def test_weighted_kappa_is_one_on_perfect_agreement_and_undefined_without_variation():
    assert weighted_kappa([0, 1, 2], [0, 1, 2], categories=[0, 1, 2]) == pytest.approx(1.0)
    assert weighted_kappa([1, 1], [1, 1], categories=[0, 1, 2]) is None


def test_confusion_matrix_counts_pairs():
    assert confusion_matrix([0, 1, 2, 2], [0, 2, 2, 1], categories=[0, 1, 2]) == [
        [1, 0, 0],
        [0, 0, 1],
        [0, 1, 1],
    ]


def test_bootstrap_ci_brackets_the_estimate_and_is_reproducible():
    units = [[0, 0], [1, 1], [2, 2], [2, 1], [0, 1], [1, 1], [2, 2], [0, 0], [1, 2], [2, 2]]
    point = krippendorff_alpha(units)

    first = bootstrap_ci(units, krippendorff_alpha, resamples=500)
    second = bootstrap_ci(units, krippendorff_alpha, resamples=500)

    assert first == second
    low, high = first
    assert low <= point <= high
