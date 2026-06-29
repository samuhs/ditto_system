"""Registry generico para tecnicas plugaveis (chunking, embedding, rag, etc.)."""
from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Mapa nomeado de implementacoes de uma categoria de tecnica."""

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str, item: T) -> None:
        """Registra uma implementacao sob um nome unico."""
        if name in self._items:
            raise ValueError(f"{self._kind} '{name}' ja registrado")
        self._items[name] = item

    def get(self, name: str) -> T:
        """Retorna a implementacao registrada ou levanta KeyError."""
        if name not in self._items:
            raise KeyError(
                f"{self._kind} '{name}' nao encontrado. "
                f"Disponiveis: {sorted(self._items)}"
            )
        return self._items[name]

    def names(self) -> list[str]:
        """Lista os nomes registrados."""
        return list(self._items)
