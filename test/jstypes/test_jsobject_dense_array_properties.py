from __future__ import annotations

from typing import ClassVar, Iterable, Protocol, Self, TypeVar

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
    SparseArrayProperties,
)

T = TypeVar("T")


@ArrayProperties.register
class SimpleArrayProperties(list[T | JSHoleType]):
    """Very simple but inefficient implementation of ArrayProperties to compare
    against real implementations.
    """

    @classmethod
    def create(cls, values: Iterable[T | JSHoleType]) -> Self:
        return cls(values)

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


class ArrayPropertiesConstructor(Protocol):
    def __call__(self, values: Iterable[T | JSHoleType]) -> ArrayProperties[T]: ...


class AbstractArrayPropertiesComparisonMachine(RuleBasedStateMachine):
    actual_type: ClassVar[ArrayPropertiesConstructor]
    reference_type: ClassVar[ArrayPropertiesConstructor] = SimpleArrayProperties.create  # type: ignore[assignment]

    _actual: ArrayProperties[object] | None
    _reference: ArrayProperties[object] | None

    def __init__(self) -> None:
        super().__init__()
        self._actual = None
        self._reference = None

    @property
    def actual(self) -> ArrayProperties[object]:
        assert self._actual is not None
        return self._actual

    @property
    def reference(self) -> ArrayProperties[object]:
        assert self._reference is not None
        return self._reference

    @property
    def valid_indexes(self) -> st.SearchStrategy[int]:
        """Get a strategy generating in-range indexes, negative or positive."""
        if len(self.reference) == 0:
            # Should never get used if preconditions prevent calling a method
            # using this strategy.
            return st.nothing()
        return st.integers(
            min_value=-len(self.reference), max_value=len(self.reference) - 1
        )

    @staticmethod
    def get_valid_indexes(
        self: AbstractArrayPropertiesComparisonMachine,
    ) -> st.SearchStrategy[int]:
        return self.valid_indexes

    @staticmethod
    def not_empty(self: AbstractArrayPropertiesComparisonMachine) -> bool:
        return self._reference is not None and len(self._reference) > 0

    @initialize(initial_items=st.lists(elements=values_or_gaps))
    def init(self, initial_items: list[int | JSHoleType]) -> None:
        self._reference = self.reference_type(list(initial_items))
        self._actual = self.actual_type(list(initial_items))

    @rule(index=st.runner().flatmap(get_valid_indexes), value=st.integers())
    @precondition(not_empty)
    def setitem(self, index: int, value: int) -> None:
        assert self.reference[index] == self.actual[index]
        self.reference[index] = value
        self.actual[index] = value
        assert self.reference[index] == value
        assert self.reference[index] == self.actual[index]

    @rule(index=st.runner().flatmap(get_valid_indexes))
    @precondition(not_empty)
    def del_(self, index: int) -> None:
        del self.reference[index]
        del self.actual[index]

    @rule(index=st.runner().flatmap(get_valid_indexes), value=st.integers())
    def insert(self, index: int, value: int) -> None:
        self.reference.insert(index, value)
        self.actual.insert(index, value)

    @rule(value=st.integers())
    def append(self, value: int) -> None:
        self.reference.append(value)
        self.actual.append(value)

    @invariant()
    def implementations_equal(self) -> None:
        assert self.actual == self.reference

    @invariant()
    def implementations_same_length(self) -> None:
        assert len(self.actual) == len(self.reference)

    @invariant()
    def implementations_same_has_holes(self) -> None:
        assert self.actual.has_holes == self.reference.has_holes

    @invariant()
    def implementations_same_max_index(self) -> None:
        assert self.actual.max_index == self.reference.max_index

    @invariant()
    def implementations_same_elements_used(self) -> None:
        assert self.actual.elements_used == self.reference.elements_used


class DenseArrayPropertiesComparisonMachine(AbstractArrayPropertiesComparisonMachine):
    actual_type = DenseArrayProperties


# TODO: test
class SparseArrayPropertiesComparisonMachine(AbstractArrayPropertiesComparisonMachine):
    reference_type = SparseArrayProperties


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
