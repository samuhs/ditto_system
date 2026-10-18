"""Agreement statistics of the Anotação humana, against hand-worked and published values."""
import pytest

from app.annotation.agreement import (
    bootstrap_ci,
    confusion_matrix,
    krippendorff_alpha,
    sign_test,
    weighted_kappa,
    wilson_ci,
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


def test_spearman_matches_a_hand_worked_example():
    from app.annotation.agreement import spearman
    # ranks equal values; d = [0, 1, 1, 0]: rho = 1 - 6*2 / (4*15) = 0.8
    assert spearman([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)


def test_spearman_uses_mid_ranks_for_ties():
    from app.annotation.agreement import spearman
    # x ranks [1.5, 1.5, 3, 4]; Pearson of ranks = 4.5 / sqrt(4.5 * 5)
    assert spearman([1, 1, 2, 3], [1, 2, 3, 4]) == pytest.approx(4.5 / (4.5 * 5) ** 0.5)


def test_spearman_is_undefined_without_variation():
    from app.annotation.agreement import spearman
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert spearman([1], [2]) is None


# ---- pairwise comparison rounds: unweighted/linear kappa, sign test, Wilson CI ----

def test_weighted_kappa_unweighted_matches_plain_cohens_kappa():
    # Same ratings as the quadratic hand-worked example above; Do = 0.5, De = 0.375 -> kappa 0.2.
    assert weighted_kappa([0, 1, 2, 2], [0, 2, 2, 1], categories=[0, 1, 2],
                          weights="unweighted") == pytest.approx(0.2)


def test_weighted_kappa_linear_matches_a_hand_worked_example():
    # Linear weights |i-j|/2. Do = 0.25, De = 0.4375, kappa = 1 - Do/De = 3/7.
    assert weighted_kappa([0, 1, 2, 2], [0, 2, 2, 1], categories=[0, 1, 2],
                          weights="linear") == pytest.approx(3 / 7)


def test_weighted_kappa_defaults_to_quadratic_weights():
    assert weighted_kappa([0, 1, 2, 2], [0, 2, 2, 1], categories=[0, 1, 2]) == pytest.approx(7 / 11)


def test_an_unknown_kappa_weighting_is_refused():
    with pytest.raises(ValueError):
        weighted_kappa([0, 1], [0, 1], categories=[0, 1], weights="cubic")


def test_sign_test_matches_a_hand_worked_binomial_tail():
    # n=10, k=2: 2 * sum_{i=0..2} C(10,i) / 2**10 = 2 * 56/1024 = 0.109375.
    assert sign_test(8, 2) == pytest.approx(0.109375)
    assert sign_test(5, 5) == pytest.approx(1.0)  # an even split is never significant
    assert sign_test(0, 0) is None


def test_wilson_ci_matches_a_published_score_interval():
    # Wilson (1927) 95% interval for 5/10 is commonly tabulated as about (0.237, 0.763).
    low, high = wilson_ci(5, 10)
    assert low == pytest.approx(0.2366, abs=0.001)
    assert high == pytest.approx(0.7634, abs=0.001)
    assert wilson_ci(0, 0) is None
