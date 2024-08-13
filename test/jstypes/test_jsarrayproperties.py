from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generator,
    Iterable,
    Protocol,
    Self,
    TypeVar,
    cast,
)

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
)

from v8serialize.jstypes.jsarrayproperties import (
    MAX_ARRAY_LENGTH_REPR,
    ArrayProperties,
    DenseArrayProperties,
    EmptyRegion,
    JSHole,
    JSHoleType,
    OccupiedRegion,
    SparseArrayProperties,
    array_properties_regions,
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
    def length(self) -> int:
        return len(self)

    @length.setter
    def length(self, length: int) -> None:
        if length < 0:
            raise ValueError(f"length must be >= 0 and < {MAX_ARRAY_LENGTH_REPR}")
        current_length = len(self)
        if length > current_length:
            self.extend([JSHole] * (length - current_length))
        else:
            del self[length:]
        assert len(self) == length

    @property
    def elements_used(self) -> int:
        return len(self) - sum(1 for x in self if x is JSHole)

    def regions(self) -> Generator[EmptyRegion | OccupiedRegion[T], None, None]:
        return array_properties_regions(self)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ArrayProperties):
            return other.__eq__(self)
        return super().__eq__(other)

    def __repr__(self) -> str:
        return (
            f"< SimpleArrayProperties({super().__repr__()}) "
            f"has_holes={self.has_holes!r}, length={self.length!r}, "
            f"elements_used={self.elements_used!r} >"
        )


if TYPE_CHECKING:
    t0: type[ArrayProperties[object]] = SimpleArrayProperties[object]
    t1: type[ArrayProperties[object]] = DenseArrayProperties[object]
    t2: type[ArrayProperties[object]] = SparseArrayProperties[object]


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

    @property
    def lengths_lte_current(self) -> st.SearchStrategy[int]:
        """Get a strategy generating array lengths <= current length."""
        return st.integers(min_value=0, max_value=len(self.reference))

    @staticmethod
    def get_lengths_lte_current(
        self: AbstractArrayPropertiesComparisonMachine,
    ) -> st.SearchStrategy[int]:
        return self.lengths_lte_current

    @staticmethod
    def not_empty(self: AbstractArrayPropertiesComparisonMachine) -> bool:
        return self._reference is not None and len(self._reference) > 0

    @staticmethod
    def not_too_large(self: AbstractArrayPropertiesComparisonMachine) -> bool:
        return self._reference is not None and len(self._reference) < 2048

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

    # arbitrary max to avoid creating needlessly large arrays
    @rule(length_increase=st.integers(min_value=0, max_value=200))
    @precondition(not_too_large)
    def extend_length(self, length_increase: int) -> None:
        new_length = self.reference.length + length_increase
        self.reference.length = new_length
        self.actual.length = new_length

        assert self.reference.length == new_length
        assert self.actual.length == new_length

    @rule(new_length=st.runner().flatmap(get_lengths_lte_current))
    def truncate_with_length(self, new_length: int) -> None:
        self.reference.length = new_length
        self.actual.length = new_length

        assert self.reference.length == new_length
        assert self.actual.length == new_length

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
    def implementations_same_dunder_len(self) -> None:
        assert len(self.actual) == len(self.reference)

    @invariant()
    def implementations_same_has_holes(self) -> None:
        assert self.actual.has_holes == self.reference.has_holes

    @invariant()
    def implementations_same_length(self) -> None:
        assert self.actual.length == self.reference.length

    @invariant()
    def implementations_same_elements_used(self) -> None:
        assert self.actual.elements_used == self.reference.elements_used

    @invariant()
    def implementations_regions_equal(self) -> None:
        assert list(self.actual.regions()) == list(self.reference.regions())

    @invariant()
    def implementations_iter_equal(self) -> None:
        assert list(iter(self.actual)) == list(iter(self.reference))


class DenseArrayPropertiesComparisonMachine(AbstractArrayPropertiesComparisonMachine):
    actual_type = DenseArrayProperties

    @invariant()
    def dense_array_elements_used_correspond_to_items(self) -> None:
        actual = cast(DenseArrayProperties[object], self.actual)
        assert actual._elements_used == sum(1 for i in actual._items if i is not JSHole)


class SparseArrayPropertiesComparisonMachine(AbstractArrayPropertiesComparisonMachine):
    actual_type = SparseArrayProperties

    @invariant()
    def sparse_array_sorted_keys_correspond_to_items(self) -> None:
        actual = cast(SparseArrayProperties[object], self.actual)
        if actual._sorted_keys is not None:
            assert actual._sorted_keys == sorted(actual._items)

    @invariant()
    def sparse_array_max_index_gte_items(self) -> None:
        actual = cast(SparseArrayProperties[object], self.actual)
        if len(actual._items) > 0:
            assert actual._max_index >= max(actual._items)


TestDenseArrayPropertiesComparison = DenseArrayPropertiesComparisonMachine.TestCase
TestSparseArrayPropertiesComparison = SparseArrayPropertiesComparisonMachine.TestCase


@pytest.mark.parametrize(
    "args, kwargs, result",
    [
        ([], {}, []),
        ([[]], {}, []),
        ([["a"]], {}, ["a"]),
        ([["a", JSHole, "b"]], {}, ["a", JSHole, "b"]),
        ([], {"values": ["a"]}, ["a"]),
    ],
)
def test_DenseArrayProperties_init(
    args: list[Any], kwargs: dict[str, Any], result: list[JSHoleType | str]
) -> None:
    assert list(DenseArrayProperties(*args, **kwargs)) == result


def test_init_initial_state() -> None:
    array = DenseArrayProperties([JSHole, "a", JSHole, "b", JSHole])
    assert array.elements_used == 2
    assert array.length == 5
    assert len(array) == 5


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


@pytest.mark.parametrize(
    "args, kwargs, result",
    [
        ([], {}, []),
        ([None], {"entries": None}, []),
        ([], {"entries": None}, []),
        ([None], {}, []),
        ([[JSHole]], {}, [JSHole]),
        ([], {"values": [JSHole]}, [JSHole]),
        (
            [[JSHole, JSHole, "a", "b", JSHole, "c", JSHole]],
            {},
            [JSHole, JSHole, "a", "b", JSHole, "c", JSHole],
        ),
        ([], {"entries": []}, []),
        ([], {"entries": {}}, []),
        (
            [],
            {"entries": {2: "a", 3: "b", 5: "c"}},
            [JSHole, JSHole, "a", "b", JSHole, "c"],
        ),
        (
            [],
            {"entries": {2: "a", 3: "b", 5: "c"}, "length": 4},
            [JSHole, JSHole, "a", "b"],
        ),
        (
            [],
            {"entries": {2: "a", 3: "b", 5: "c"}, "length": 9},
            [JSHole, JSHole, "a", "b", JSHole, "c", JSHole, JSHole, JSHole],
        ),
    ],
)
def test_SparseArrayProperties_init__(
    args: list[Any], kwargs: dict[str, Any], result: list[JSHoleType | str]
) -> None:
    assert list(SparseArrayProperties(*args, **kwargs)) == result
