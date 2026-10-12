"""Statistics behind a Comparação: paired bootstrap CI and mean CI.

Expected values come from worked examples (by hand, or scipy run once offline),
never from the code under test.
"""
import pytest

from app.experiments.stats import friedman, mean_ci, paired_diff_ci


def test_a_constant_difference_has_a_zero_width_interval():
    ci = paired_diff_ci([0.2, 0.2, 0.2, 0.2])
    assert ci.mean == pytest.approx(0.2)
    assert (ci.low, ci.high) == (pytest.approx(0.2), pytest.approx(0.2))
    assert ci.significant


def test_differences_on_both_sides_of_zero_are_not_significant():
    ci = paired_diff_ci([0.5, -0.5, 0.4, -0.4, 0.3, -0.3])
    assert ci.mean == pytest.approx(0.0)
    assert ci.low < 0 < ci.high
    assert not ci.significant


def test_all_positive_differences_are_significant():
    ci = paired_diff_ci([0.1, 0.3, 0.2, 0.4, 0.1, 0.2, 0.3, 0.2])
    assert 0 < ci.low <= ci.mean <= ci.high
    assert ci.significant


def test_the_bootstrap_is_reproducible():
    """Seed 0, 10,000 resamples: the same Comparação always shows the same CI."""
    diffs = [0.3, -0.1, 0.2, 0.0, 0.5, -0.2, 0.1]
    assert paired_diff_ci(diffs) == paired_diff_ci(list(diffs))


def test_mean_ci_brackets_the_mean():
    ci = mean_ci([0.2, 0.4, 0.6, 0.8])
    assert ci.mean == pytest.approx(0.5)
    assert 0.2 <= ci.low < 0.5 < ci.high <= 0.8


def test_friedman_uses_mid_ranks_for_ties():
    """3 questions x 3 Combinações, worked by hand:
    q1 (1, 0, 0) -> ranks 3, 1.5, 1.5; q2 (1, 1, 0) -> 2.5, 2.5, 1; q3 (.5, .2, .9) -> 2, 1, 3.
    Rank sums 7.5, 5, 5.5: chi2 = 12/(3*3*4) * 111.5 - 3*3*4 = 1.1667, df 2, p = e^(-chi2/2)."""
    result = friedman([[1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.5, 0.2, 0.9]])
    assert result.chi2 == pytest.approx(7 / 6)
    assert result.df == 2
    assert result.p == pytest.approx(0.5580351457700471)
    assert result.n == 3


@pytest.mark.parametrize("chi2, df, p", [
    (33.34, 7, 2.2880938893476784e-05),  # the campaign's phase 3 (scipy, offline)
    (10.0, 5, 0.07523524614651216),
])
def test_friedman_p_value_is_the_chi_square_tail(chi2, df, p):
    from app.experiments.stats import chi2_sf

    assert chi2_sf(chi2, df) == pytest.approx(p, rel=1e-6)
