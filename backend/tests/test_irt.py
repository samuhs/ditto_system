"""Tests for the Rasch fit over experiment results."""
import pytest

from app.experiments.irt import fit_rasch


def test_harder_questions_get_higher_difficulty_and_better_configs_higher_ability():
    scores = {"easy": 0.9, "mid": 0.6, "hard": 0.2}
    responses = {}
    for config, skill in [("strong", 0.1), ("weak", -0.2)]:
        for question, base in scores.items():
            responses[(config, question)] = min(1.0, max(0.0, base + skill))
    difficulty, ability = fit_rasch(responses)
    assert difficulty["hard"] > difficulty["mid"] > difficulty["easy"]
    assert sum(difficulty.values()) == pytest.approx(0.0, abs=1e-9)
    assert ability["strong"] > ability["weak"]


def test_perfect_scores_stay_finite_and_repeats_are_averaged():
    difficulty, _ = fit_rasch({("a", "q1"): 1.0, ("a", "q2"): 0.0, ("b", "q1"): 1.0})
    assert all(abs(v) < 20 for v in difficulty.values())
    assert difficulty["q2"] > difficulty["q1"]


def test_empty_input():
    assert fit_rasch({}) == ({}, {})
