from __future__ import annotations

import dataclasses
from typing import Any, ClassVar, Iterable, Iterator, Protocol, Sequence, TypeVar, cast

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
    MAX_ARRAY_LENGTH,
    MAX_ARRAY_LENGTH_REPR,
    ArrayProperties,
    ArrayPropertiesElementsView,
    DenseArrayProperties,
    EmptyRegion,
    JSHole,
    JSHoleType,
    OccupiedRegion,
    SparseArrayProperties,
    alternating_regions,
)
from v8serialize.typing import ElementsView, Order

T = TypeVar("T")


# The ignore[misc] here is for the same reason as for AbstractArrayProperties in
# jsarrayproperties.py.


@ArrayProperties.register
class SimpleArrayProperties(  # type: ignore[misc]
    list[T | JSHoleType], ArrayProperties[T]
):
    """Very simple but inefficient implementation of ArrayProperties to compare
    against real implementations.
    """

    hole_value: ClassVar[JSHoleType] = JSHole

    def __init__(self, values: Iterable[T | JSHoleType] | None = None) -> None:
        if values is not None:
            super().__init__(values)

    def resize(self, length: int) -> None:
        if length < 0 or length > MAX_ARRAY_LENGTH:
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

    def element_indexes(self, *, order: Order = Order.ASCENDING) -> Iterator[int]:
        if order is not Order.DESCENDING:
            return (i for i, v in enumerate(self) if v is not JSHole)
        last_index = len(self) - 1
        return (last_index - i for i, v in enumerate(reversed(self)) if v is not JSHole)

    def elements(self, *, order: Order = Order.ASCENDING) -> ElementsView[T]:
        return ArrayPropertiesElementsView(self, order=order)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ArrayProperties):
            return other.__eq__(self)
        return super().__eq__(other)

    def __repr__(self) -> str:
        return (
            f"< SimpleArrayProperties({super().__repr__()}) "
            f"length={len(self)!r}, "
            f"elements_used={self.elements_used!r} >"
        )


class ArrayPropertiesConstructor(Protocol[T]):
    def __call__(
        self, values: Iterable[T | JSHoleType] | None = None
    ) -> ArrayProperties[T]: ...


ARRAY_PROPERTIES_IMPLEMENTATIONS: Sequence[ArrayPropertiesConstructor[Any]] = (
    SimpleArrayProperties,
    DenseArrayProperties,
    SparseArrayProperties,
)

values_or_gaps = st.one_of(st.integers(), st.just(JSHole))


@pytest.fixture(scope="session", params=ARRAY_PROPERTIES_IMPLEMENTATIONS)
def impl(request: pytest.FixtureRequest) -> ArrayPropertiesConstructor[Any]:
    return cast(ArrayPropertiesConstructor[Any], request.param)


class AbstractArrayPropertiesComparisonMachine(RuleBasedStateMachine):
    actual_type: ClassVar[ArrayPropertiesConstructor[object]]
    reference_type: ClassVar[ArrayPropertiesConstructor[object]] = SimpleArrayProperties

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
        new_length = len(self.reference) + length_increase
        self.reference.resize(new_length)
        self.actual.resize(new_length)

        assert len(self.reference) == new_length
        assert len(self.actual) == new_length

    @rule(new_length=st.runner().flatmap(get_lengths_lte_current))
    def truncate_with_length(self, new_length: int) -> None:
        self.reference.resize(new_length)
        self.actual.resize(new_length)

        assert len(self.reference) == new_length
        assert len(self.actual) == new_length

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
    def implementations_same_elements_used(self) -> None:
        assert self.actual.elements_used == self.reference.elements_used

    @invariant()
    def implementations_same_element_indexes(self) -> None:
        actual_indexes_asc = list(self.actual.element_indexes(order=Order.ASCENDING))
        actual_indexes_desc = list(self.actual.element_indexes(order=Order.DESCENDING))
        reference_indexes_asc = list(self.actual.element_indexes(order=Order.ASCENDING))
        reference_indexes_desc = list(
            self.actual.element_indexes(order=Order.DESCENDING)
        )

        assert actual_indexes_asc == reference_indexes_asc
        assert actual_indexes_desc == reference_indexes_desc
        assert list(reversed(actual_indexes_asc)) == actual_indexes_desc

    @invariant()
    def implementations_iter_equal(self) -> None:
        assert list(iter(self.actual)) == list(iter(self.reference))

    @invariant()
    def elements_views_reflect_sequence(self) -> None:
        assert (
            SparseArrayProperties(
                entries=self.actual.elements(), length=len(self.actual)
            )
            == self.reference
        )


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
    assert len(array) == 5


@pytest.mark.parametrize(
    "values, regions",
    [
        ([], []),
        ([JSHole], [EmptyRegion(start=0, length=1)]),
        ([JSHole, JSHole], [EmptyRegion(start=0, length=2)]),
        (["a"], [OccupiedRegion(items=[(0, "a")])]),
        (["a", "b"], [OccupiedRegion(items=[(0, "a"), (1, "b")])]),
        (
            [JSHole, JSHole, "a", "b", JSHole, "c", JSHole],
            [
                EmptyRegion(start=0, length=2),
                OccupiedRegion(items=[(2, "a"), (3, "b")]),
                EmptyRegion(start=4, length=1),
                OccupiedRegion(items=[(5, "c")]),
                EmptyRegion(start=6, length=1),
            ],
        ),
    ],
)
def test_alternating_regions(
    values: Sequence[JSHoleType | str],
    regions: Sequence[EmptyRegion | OccupiedRegion[T]],
) -> None:
    array = DenseArrayProperties(values)
    actual_regions = [r for r in alternating_regions(array)]

    assert actual_regions == regions


def test_empty_region_str() -> None:
    assert str(EmptyRegion(start=3, length=4)) == "<4 empty items>"


def test_empty_region_dunder_len() -> None:
    assert len(EmptyRegion(start=3, length=4)) == 4


@pytest.mark.parametrize(
    "args, kwargs, result",
    [
        ([[]], {}, None),
        ([["a"], 0], {}, dict(start=0, length=1, items=["a"])),
        ([["a", "b"], 1], {}, dict(start=1, length=2, items=["a", "b"])),
        (
            [],
            {"start": 1, "items": ["a", "b"]},
            dict(start=1, length=2, items=["a", "b"]),
        ),
        ([[(3, "a"), (4, "b")]], {}, dict(start=3, length=2, items=["a", "b"])),
        (
            [],
            {"items": [(3, "a"), (4, "b")]},
            dict(start=3, length=2, items=["a", "b"]),
        ),
    ],
)
def test_occupied_region_init(
    args: list[Any], kwargs: dict[str, Any], result: dict[str, object] | None
) -> None:
    try:
        region = OccupiedRegion(*args, **kwargs)
    except ValueError as e:
        assert result is None
        assert str(e) == "items cannot be empty"
        return
    assert dataclasses.asdict(region) == result


def test_occupied_region_dunder_len() -> None:
    assert len(OccupiedRegion(["a", "b", "c"], 10)) == 3


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


@pytest.mark.parametrize("invalid_length", [-1, MAX_ARRAY_LENGTH + 1])
def test_cannot_resize_to_invalid_length(
    impl: ArrayPropertiesConstructor[T], invalid_length: int
) -> None:
    arr = impl()
    with pytest.raises(ValueError, match=r"length must be >= 0 and < 2\*\*32 - 1"):
        arr.resize(invalid_length)


###############################
# ArrayPropertiesElementsView #
###############################


def test_ArrayPropertiesElementsView_dunder_eq() -> None:
    a = DenseArrayProperties(["a", JSHole, "b"])
    b = DenseArrayProperties(["a", JSHole, "b"])
    c = SparseArrayProperties(entries=[(2, "b"), (0, "a")])

    assert a.elements() == b.elements()
    assert a.elements() == c.elements()

    # not eq when order is different, even when actual elements match (this
    # avoids varying eq behaviour depending on unspecified ordering):
    # In practice the elements happen to be in order because of c's entries order
    assert list(a.elements(order=Order.UNORDERED).items()) == list(
        c.elements(order=Order.ASCENDING).items()
    )
    # But not eq because of different order arg
    assert a.elements(order=Order.UNORDERED) != c.elements(order=Order.ASCENDING)
    # Eq with explicit unordered (even though though iteration order is different)
    assert a.elements(order=Order.UNORDERED) == c.elements(order=Order.UNORDERED)
