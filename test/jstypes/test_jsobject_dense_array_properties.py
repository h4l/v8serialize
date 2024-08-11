from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Self, TypeVar

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
)

from v8serialize.jstypes.jsobject import (
    ArrayProperties,
    DenseArrayProperties,
    EmptyRegion,
    JSHole,
    JSHoleType,
    OccupiedRegion,
)

T = TypeVar("T")


@ArrayProperties.register
class SimpleArrayProperties(list[T | JSHoleType]):
    """Very simple but inefficient implementation of ArrayProperties to compare
    against real implementations.
    """

    @property
    def has_holes(self) -> bool:
        return any(x is JSHole for x in self)

    @property
    def max_index(self) -> int:
        for i in range(len(self) - 1, -1, -1):
            if self[i] is not JSHole:
                return i
        return -1

    @property
    def elements_used(self) -> int:
        return len(self) - sum(1 for x in self if x is JSHole)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ArrayProperties):
            return other.__eq__(self)
        return super().__eq__(other)

    def __repr__(self) -> str:
        return (
            f"< SimpleArrayProperties({super().__repr__()}) "
            f"has_holes={self.has_holes!r}, max_index={self.max_index!r}, "
            f"elements_used={self.elements_used!r} >"
        )


values_or_gaps = st.one_of(st.integers(), st.just(JSHole))


class DenseArrayPropertiesComparisonMachine(RuleBasedStateMachine):
    _dense: DenseArrayProperties[object] | None
    _simple: SimpleArrayProperties[object] | None

    def __init__(self) -> None:
        super().__init__()
        self._dense = None
        self._simple = None

    @property
    def dense(self) -> DenseArrayProperties[object]:
        assert self._dense is not None
        return self._dense

    @property
    def simple(self) -> SimpleArrayProperties[object]:
        assert self._simple is not None
        return self._simple

    @property
    def valid_indexes(self) -> st.SearchStrategy[int]:
        """Get a strategy generating in-range indexes, negative or positive."""
        if len(self.simple) == 0:
            # Should never get used if preconditions prevent calling a method
            # using this strategy.
            return st.nothing()
        return st.integers(min_value=-len(self.simple), max_value=len(self.simple) - 1)

    @staticmethod
    def get_valid_indexes(
        self: DenseArrayPropertiesComparisonMachine,
    ) -> st.SearchStrategy[int]:
        return self.valid_indexes

    @staticmethod
    def not_empty(self: DenseArrayPropertiesComparisonMachine) -> bool:
        return self._simple is not None and len(self._simple) > 0

    @initialize(initial_items=st.lists(elements=values_or_gaps))
    def init(self, initial_items: list[int | JSHoleType]) -> None:
        self._simple = SimpleArrayProperties(list(initial_items))
        self._dense = DenseArrayProperties(list(initial_items))

    @rule(index=st.runner().flatmap(get_valid_indexes), value=st.integers())
    @precondition(not_empty)
    def setitem(self, index: int, value: int) -> None:
        assert self.simple[index] == self.dense[index]
        self.simple[index] = value
        self.dense[index] = value
        assert self.simple[index] == value
        assert self.simple[index] == self.dense[index]

    @rule(index=st.runner().flatmap(get_valid_indexes))
    @precondition(not_empty)
    def del_(self, index: int) -> None:
        del self.simple[index]
        del self.dense[index]

    @rule(index=st.runner().flatmap(get_valid_indexes), value=st.integers())
    def insert(self, index: int, value: int) -> None:
        self.simple.insert(index, value)
        self.dense.insert(index, value)

    @rule(value=st.integers())
    def append(self, value: int) -> None:
        self.simple.append(value)
        self.dense.append(value)

    @invariant()
    def implementations_equal(self) -> None:
        assert self.dense == self.simple

    @invariant()
    def implementations_same_length(self) -> None:
        assert len(self.dense) == len(self.simple)

    @invariant()
    def implementations_same_has_holes(self) -> None:
        assert self.dense.has_holes == self.simple.has_holes

    @invariant()
    def implementations_same_max_index(self) -> None:
        assert self.dense.max_index == self.simple.max_index

    @invariant()
    def implementations_same_elements_used(self) -> None:
        assert self.dense.elements_used == self.simple.elements_used


TestDenseArrayPropertiesComparison = DenseArrayPropertiesComparisonMachine.TestCase


@pytest.mark.parametrize(
    "elements,result",
    [
        ([], []),
        (["a"], ["a"]),
        (["a", JSHole, "b"], ["a", JSHole, "b"]),
    ],
)
def test_init(elements: Iterable[object], result: list[object]) -> None:
    assert list(DenseArrayProperties(elements)) == result


def test_init_initial_state() -> None:
    array = DenseArrayProperties([JSHole, "a", JSHole, "b", JSHole])
    assert array.elements_used == 2
    assert array.max_index == 3


def test_regions() -> None:
    array = DenseArrayProperties([JSHole, JSHole, "a", "b", JSHole, "c", JSHole])
    regions = [r for r in array.regions()]

    assert regions == [
        EmptyRegion(start=0, length=2),
        OccupiedRegion(items=[(2, "a"), (3, "b")]),
        EmptyRegion(start=4, length=1),
        OccupiedRegion(items=[(5, "c")]),
        EmptyRegion(start=6, length=1),
    ]
