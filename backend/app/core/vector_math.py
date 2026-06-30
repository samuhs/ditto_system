"""Shared vector math helpers."""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity between two vectors (0 if either is zero)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Return 1 - cosine similarity between two vectors."""
    return 1.0 - cosine_similarity(a, b)
