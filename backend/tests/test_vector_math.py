"""Tests for shared vector math helpers."""
from app.core.vector_math import cosine_distance, cosine_similarity


def test_cosine_similarity_identical():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_distance_is_complement():
    assert cosine_distance([1.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_distance([1.0, 0.0], [0.0, 1.0]) == 1.0
