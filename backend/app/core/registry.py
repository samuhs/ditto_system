"""Generic registry for pluggable techniques (chunking, embedding, rag, etc.)."""
from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Named map of implementations for a technique category."""

    def __init__(self, kind: str) -> None:
        """Initialize the registry for the given technique category."""
        self._kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str, item: T) -> None:
        """Register an implementation under a unique name."""
        if name in self._items:
            raise ValueError(f"{self._kind} '{name}' already registered")
        self._items[name] = item

    def get(self, name: str) -> T:
        """Return the registered implementation or raise KeyError."""
        if name not in self._items:
            raise KeyError(
                f"{self._kind} '{name}' not found. "
                f"Available: {sorted(self._items)}"
            )
        return self._items[name]

    def names(self) -> list[str]:
        """List the registered names."""
        return list(self._items)
