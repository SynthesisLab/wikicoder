from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")


class Pruner(ABC, Generic[T]):
    @abstractmethod
    def accept(self, obj: T) -> bool:
        pass


class UnionPruner(Pruner, Generic[U]):
    def __init__(self, *pruners: Pruner[U]) -> None:
        self.pruners = list(pruners)

    def accept(self, obj: U) -> bool:
        return all(p.accept(obj) for p in self.pruners)
