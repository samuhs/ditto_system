"""Statistics behind a Comparação: paired bootstrap CI and mean CI.

Expected values come from worked examples (by hand, or scipy run once offline),
never from the code under test.
"""
import pytest

from app.experiments.stats import mean_ci, paired_diff_ci


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
