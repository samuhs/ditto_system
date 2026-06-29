import pytest

from app.core.registry import Registry


def test_register_and_get():
    reg: Registry[str] = Registry("chunker")
    reg.register("recursive", "impl")
    assert reg.get("recursive") == "impl"


def test_names_lists_registered():
    reg: Registry[int] = Registry("embedder")
    reg.register("a", 1)
    reg.register("b", 2)
    assert sorted(reg.names()) == ["a", "b"]


def test_get_unknown_raises_with_helpful_message():
    reg: Registry[int] = Registry("retriever")
    reg.register("known", 1)
    with pytest.raises(KeyError) as exc:
        reg.get("missing")
    assert "retriever" in str(exc.value)
    assert "known" in str(exc.value)


def test_register_duplicate_raises():
    reg: Registry[int] = Registry("llm")
    reg.register("x", 1)
    with pytest.raises(ValueError):
        reg.register("x", 2)
