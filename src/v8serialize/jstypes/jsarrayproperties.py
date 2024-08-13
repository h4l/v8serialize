from __future__ import annotations

from abc import ABC, abstractmethod
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass, field
from itertools import groupby, repeat
from typing import (
    TYPE_CHECKING,
    Final,
    Generator,
    Generic,
    Iterable,
    Iterator,
    MutableMapping,
    MutableSequence,
    Sequence,
    Sized,
    TypeGuard,
    TypeVar,
    cast,
    overload,
)

if TYPE_CHECKING:
    from _typeshed import SupportsItems, SupportsKeysAndGetItem

_KT = TypeVar("_KT")
KT = TypeVar("KT", bound=int | str)
T = TypeVar("T")


@dataclass(slots=True, frozen=True)
class JSHoleType:
    """Explicit representation of the empty elements in JavaScript arrays.

    JavaScript arrays are sparse, in that you can set the value of indexes
    beyond the current length. Accessing empty elements returns `undefined` in
    JavaScript. There is a distinction between an empty element and one that
    explicitly contains `undefined` — `i in array` is `true` when
    `array[i] = undefined` and `false` when `array[i]` is empty. The JavaScript
    `delete` operator makes an index empty.

    To model this behaviour in Python, JSHole is used to represent reads of
    array indexes that are empty. This allows us to model JavaScript arrays as
    regular Python Sequence types, without white lies about them containing
    JSUndefined values.
    """

    def __init__(self) -> None:
        if "JSHole" in globals():
            raise AssertionError("Cannot instantiate JSHoleType")

    def __repr__(self) -> str:
        return "JSHole"


JSHole: Final = JSHoleType()


class ArrayProperties(
    MutableSequence[T | JSHoleType], Sequence[T | JSHoleType], Generic[T], ABC
):
    @property
    def has_holes(self) -> bool:
        """True if any index between 0 and max_index is an empty hole."""
        return self.elements_used < self.length

    @property
    def length(self) -> int:
        """The number of elements in the array, either values or empty gaps."""
        return len(self)

    @length.setter
    @abstractmethod
    def length(self, length: int) -> None:
        """Change the length of the array. Elements are dropped if the length is
        reduced, or gaps are created at the end if the length is increased."""

    @property
    @abstractmethod
    def elements_used(self) -> int: ...

    @abstractmethod
    def regions(self) -> Generator[EmptyRegion | OccupiedRegion[T], None, None]: ...

    def __eq__(self, other: object) -> bool:
        return (
            other is self
            or isinstance(other, ArrayProperties)
            # TODO: using regions would be better to avoid reading gaps
            and list(self) == list(other)
        )

    def __str__(self) -> str:
        elements = ", ".join(
            x
            for r in self.regions()
            for x in ([str(r)] if r.items is None else map(lambda r: repr(r), r.items))
        )
        return f"[ {elements} ]"


def array_properties_regions(
    array_properties: ArrayProperties[T],
) -> Generator[EmptyRegion | OccupiedRegion[T], None, None]:
    for is_hole, items in groupby(
        enumerate(array_properties), lambda x: x[1] is JSHole
    ):
        if is_hole:
            first, _ = next(items)
            dq = deque(items, 1)  # consume & throw away gaps except last
            last = first if len(dq) == 0 else dq[0][0]
            yield EmptyRegion(start=first, length=last - first + 1)
        else:
            occupied = OccupiedRegion(items=cast(Iterator[tuple[int, T]], items))
            yield occupied


@dataclass(slots=True)
class EmptyRegion:
    start: int
    length: int
    items: None = field(init=False, default=None)

    def __str__(self) -> str:
        return f"<{self.length} empty items>"

    def __len__(self) -> int:
        return self.length


@dataclass(slots=True, init=False)
class OccupiedRegion(Generic[T]):
    start: int
    length: int
    items: Sequence[T]

    @overload
    def __init__(self, items: Sequence[T], start: int) -> None: ...

    @overload
    def __init__(self, items: Iterable[tuple[int, T]]) -> None: ...

    def __init__(
        self, items: Sequence[T] | Iterable[tuple[int, T]], start: int | None = None
    ) -> None:
        if start is not None:
            self.items = cast(Sequence[T], items)
            self.start = start
            self.length = len(self.items)
            return

        items = iter(cast(Iterable[tuple[int, T]], items))
        try:
            i, v = next(items)
        except StopIteration:
            raise ValueError("items cannot be empty")
        self.start = i
        self.items = [v for group in [[(i, v)], items] for (_, v) in group]
        self.length = len(self.items)

    def __len__(self) -> int:
        return self.length


MAX_ARRAY_LENGTH: Final = 2**32 - 1
MAX_ARRAY_LENGTH_REPR: Final = "2**32 - 1"
MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4
MAX_DENSE_ARRAY_HOLE_RATIO = 1 / 4


def iter_items(
    items: (
        Iterable[tuple[_KT, T]] | SupportsKeysAndGetItem[_KT, T] | SupportsItems[_KT, T]
    )
) -> Iterable[tuple[_KT, T]]:
    if callable(getattr(items, "items", None)):
        supports_items = cast("SupportsItems[_KT, T]", items)
        return supports_items.items()
    elif all(callable(getattr(items, attr, None)) for attr in ["keys", "__getitem__"]):
        supports_kagi = cast("SupportsKeysAndGetItem[_KT, T]", items)
        return ((k, supports_kagi[k]) for k in supports_kagi.keys())
    return cast(Iterable[tuple[_KT, T]], items)


def supports_sized(obj: object) -> TypeGuard[Sized]:
    return callable(getattr(obj, "__len__", None))


@dataclass(slots=True, init=False, eq=False)
class DenseArrayProperties(ArrayProperties[T]):
    _items: list[T | JSHoleType]
    _elements_used: int

    def __init__(self, values: Iterable[T | JSHoleType] | None = None) -> None:
        _items = []
        elements_used = 0
        for v in values or []:
            if v is not JSHole:
                elements_used += 1
            _items.append(v)
        self._items = _items
        self._elements_used = elements_used

    @property
    def length(self) -> int:
        return len(self._items)

    @length.setter
    def length(self, length: int) -> None:
        if length < 0 or length > MAX_ARRAY_LENGTH:
            raise ValueError(f"length must be >= 0 and < {MAX_ARRAY_LENGTH_REPR}")
        items = self._items
        current = len(items)
        if length < current:
            proportion_retained = length / current  # cannot be 0
            if proportion_retained < 0.5:
                elements_used_after = sum(
                    1 for i in range(0, length) if items[i] is not JSHole
                )
            else:
                elements_used_after = self._elements_used - sum(
                    1 for i in range(length, len(items)) if items[i] is not JSHole
                )
            del items[length:]
            self._elements_used = elements_used_after
        else:
            items.extend([JSHole] * (length - current))
            # _elements_used is unchanged

    @property
    def elements_used(self) -> int:
        """The number of elements that are not empty holes."""
        return self._elements_used

    def _normalise_index(self, i: int) -> int:
        """Flip a negative index (offset from end) to non-negative and check bounds."""
        if i < 0:
            _i = len(self) + i
            if _i < 0:
                raise IndexError(i)
            return _i
        # We don't validate out of range above as we assume accessing the list
        # will check and throw.
        return i

    @overload
    def __getitem__(self, i: int, /) -> T | JSHoleType: ...

    @overload
    def __getitem__(self, i: slice, /) -> ArrayProperties[T]: ...

    def __getitem__(self, i: int | slice, /) -> T | JSHoleType | ArrayProperties[T]:
        if isinstance(i, slice):
            raise NotImplementedError
        return self._items[i]

    @overload
    def __setitem__(self, i: int, value: T | JSHoleType, /) -> None: ...

    @overload
    def __setitem__(self, i: slice, value: Iterable[T | JSHoleType], /) -> None: ...

    def __setitem__(
        self,
        i: int | slice,
        value: T | JSHoleType | Iterable[T | JSHoleType],
        /,
    ) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)

        current = self._items[i]
        self._items[i] = cast(T | JSHoleType, value)
        if current is JSHole:
            if value is not JSHole:
                self._elements_used += 1
        elif value is JSHole:
            self._elements_used -= 1

    @overload
    def __delitem__(self, i: int, /) -> None: ...

    @overload
    def __delitem__(self, i: slice, /) -> None: ...

    def __delitem__(self, i: int | slice, /) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)

        items = self._items
        current = items[i]
        del items[i]

        if current is JSHole:
            return

        self._elements_used -= 1

    def insert(self, i: int, o: T | JSHoleType) -> None:
        i = self._normalise_index(i)

        self._items.insert(i, o)

        if o is not JSHole:
            self._elements_used += 1

    def append(self, value: T | JSHoleType) -> None:
        items = self._items
        items.append(value)
        if value is not JSHole:
            self._elements_used += 1

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T | JSHoleType]:
        return iter(self._items)

    def regions(self) -> Generator[EmptyRegion | OccupiedRegion[T], None, None]:
        return array_properties_regions(self)


@dataclass(slots=True, init=False, eq=False)
class SparseArrayProperties(ArrayProperties[T]):
    _items: dict[int, T]
    _sorted_keys: list[int] | None
    _max_index: int

    """Indexes which have been added or removed from _items, but are not
    reflected in _sorted_keys.

    True = added, False = removed."""

    @overload
    def __init__(
        self,
        *,
        entries: Iterable[tuple[int, T]] | SupportsKeysAndGetItem[int, T] | None = None,
        length: int | None = None,
    ) -> None: ...

    @overload
    def __init__(self, values: Iterable[T | JSHoleType] | None = None) -> None: ...

    def __init__(
        self,
        values: Iterable[T | JSHoleType] | None = None,
        *,
        entries: Iterable[tuple[int, T]] | SupportsKeysAndGetItem[int, T] | None = None,
        length: int | None = None,
    ) -> None:
        if values is not None:
            if length is not None:  # Enforce type signature
                raise ValueError("length cannot be used with values argument")
            if supports_sized(values):
                length = len(values)
            entries = (
                (i, v)
                for i, v in enumerate(cast(Iterable[T], values))
                if v is not JSHole
            )
        elif entries is None:
            entries = []

        invalid_index = None
        if length is None:
            self._max_index = -1
            self._items = _items = dict(entries)
            # We need to establish the max_index and validate there are no negative
            # indexes, so we might as well sort now rather than scanning for min/max
            self._sorted_keys = _sorted_keys = sorted(_items)
            if _sorted_keys:
                if _sorted_keys[0] < 0:
                    invalid_index = _sorted_keys[0]
                elif _sorted_keys[-1] >= MAX_ARRAY_LENGTH:
                    invalid_index = _sorted_keys[-1]
                self._max_index = _sorted_keys[-1]
        else:
            if length < 0 or length > MAX_ARRAY_LENGTH:
                raise ValueError(
                    f"length must be >= 0 and <= {MAX_ARRAY_LENGTH_REPR}: {length}"
                )
            self._max_index = length - 1
            self._items = _items = dict[int, T]()
            for i, v in iter_items(entries):
                if i < 0:
                    invalid_index = i
                    break
                if i < length:
                    _items[i] = v
            self._sorted_keys = None if len(_items) > 1 else list(_items)

        if invalid_index is not None:
            raise IndexError(
                f"initial item indexes must be 0 <= index < 2**32-1: {invalid_index}"
            )

    @property
    def length(self) -> int:
        return self._max_index + 1

    @length.setter
    def length(self, length: int) -> None:
        if length < 0 or length > MAX_ARRAY_LENGTH:
            raise ValueError(f"length must be >= 0 and < {MAX_ARRAY_LENGTH_REPR}")
        items = self._items
        sorted_keys = self._get_sorted_keys()

        # binary search to find the position of the new length in the key list.
        first_removed = bisect_left(sorted_keys, length)
        sorted_keys_after = sorted_keys[:first_removed]

        proportion_retained = (
            1 if len(sorted_keys) == 0 else first_removed / len(sorted_keys) <= 0.5
        )
        if proportion_retained <= 0.5:
            # copy just the retained elements as there are less kept than removed
            items_after = {i: items[i] for i in sorted_keys_after}
        else:
            # unset just the removed elements are more are kept
            items_after = items
            for i in sorted_keys[first_removed:]:
                del items_after[i]

        self._items = items_after
        self._sorted_keys = sorted_keys_after
        self._max_index = length - 1

    @property
    def elements_used(self) -> int:
        """The number of elements that are not empty holes."""
        return len(self._items)

    def _normalise_index(self, i: int) -> int:
        """Flip a negative index (offset from end) to non-negative and check bounds."""
        if i < 0:
            _i = len(self) + i
            if _i < 0:
                raise IndexError(i)
            return _i
        if i >= len(self):
            raise IndexError(i)
        return i

    @overload
    def __getitem__(self, i: int, /) -> T | JSHoleType: ...

    @overload
    def __getitem__(self, i: slice, /) -> ArrayProperties[T]: ...

    def __getitem__(self, i: int | slice, /) -> T | JSHoleType | ArrayProperties[T]:
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)
        return self._items.get(i, JSHole)

    @overload
    def __setitem__(self, i: int, value: T | JSHoleType, /) -> None: ...

    @overload
    def __setitem__(self, i: slice, value: Iterable[T | JSHoleType], /) -> None: ...

    def __setitem__(
        self,
        i: int | slice,
        value: T | JSHoleType | Iterable[T | JSHoleType],
        /,
    ) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)

        items = self._items
        if i in items:
            if value is JSHole:
                del items[i]
                # Note: making the final element a hole does not reduce the
                # max_index, as the hole is included in the length.

                # Creating a hole invalidates the sorted keys, but if it's the
                # last value we can update the sorted keys in place in O(1).

                # TODO: ensure we set an empty sorted_keys when
                #   appending/inserting from empty list
                sorted_keys = self._sorted_keys
                assert sorted_keys is not None if len(items) <= 1 else True

                if sorted_keys is None:
                    return
                if i == sorted_keys[-1]:
                    sorted_keys.pop()
                else:
                    self._sorted_keys = None
                return
            items[i] = cast(T, value)
        else:
            if value is JSHole:
                return
            items[i] = cast(T, value)
            # When filling a hole after the last existing element we can update
            # sorted_keys in place in O(1).
            sorted_keys = self._sorted_keys
            # TODO: ensure we set an empty sorted_keys when appending/inserting
            #   from empty list
            assert sorted_keys is not None if len(items) <= 1 else True
            if sorted_keys is not None and i > (
                -1 if len(sorted_keys) == 0 else sorted_keys[-1]
            ):
                sorted_keys.append(i)
            else:
                # Otherwise we need to invalidate it and re-generate later.
                self._sorted_keys = None

    @overload
    def __delitem__(self, i: int, /) -> None: ...

    @overload
    def __delitem__(self, i: slice, /) -> None: ...

    def __delitem__(self, i: int | slice, /) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)

        items = self._items
        items.pop(i, None)
        # Deleting from a list shifts all elements after i back by one
        self._items = items = {k if k <= i else k - 1: v for k, v in items.items()}
        self._max_index -= 1

        if len(items) <= 1:
            self._sorted_keys = list(self._items)
        else:
            self._sorted_keys = None

    def insert(self, i: int, value: T | JSHoleType, /) -> None:
        i = self._normalise_index(i)
        if len(self) >= MAX_ARRAY_LENGTH:
            raise IndexError("Cannot insert, array is already at max allowed length")

        # Inserting into a list shifts all elements at or after i up by one
        self._items = items = {
            (k if k < i else k + 1): v for k, v in self._items.items()
        }
        self._max_index += 1
        if value is not JSHole:
            items[i] = cast(T, value)

        if self._sorted_keys is None and len(items) <= 1:
            self._sorted_keys = list(items)
        else:
            self._sorted_keys = None

    def append(self, value: T | JSHoleType) -> None:
        if value is JSHole:
            return
        i = self._max_index + 1
        if i >= MAX_ARRAY_LENGTH:
            raise IndexError(
                f"Cannot extend array beyond max length: {MAX_ARRAY_LENGTH}"
            )

        items = self._items
        sorted_keys = self._sorted_keys
        items[i] = cast(T, value)

        if sorted_keys is None:
            if len(items) == 1:
                self._sorted_keys = [i]
        else:
            assert len(sorted_keys) == len(self._items) - 1
            assert len(sorted_keys) == 0 or sorted_keys[-1] < i
            sorted_keys.append(i)
        self._max_index = i

    def __len__(self) -> int:
        return self._max_index + 1

    def _get_sorted_keys(self) -> list[int]:
        """Get the sorted list of indexes with non-gap values.

        The sorted list invalidated after various mutation operations. Calling
        this will re-generate and cache the list.
        """
        if self._sorted_keys is None:
            self._sorted_keys = sorted(self._items)
        return self._sorted_keys

    def regions(self) -> Generator[EmptyRegion | OccupiedRegion[T], None, None]:
        items = self._items
        sorted_keys = self._get_sorted_keys()
        max_index = self._max_index

        if len(sorted_keys) == 0:
            length = len(self)
            if length == 0:
                return
            yield EmptyRegion(0, length=length)
            return

        prev_index: int = -1
        first_index: int = 0

        def first_index_of_preceding_adjacent_elements(i: int) -> int:
            nonlocal prev_index, first_index
            # start a new group if we're not connected to an ongoing group
            if i - 1 != prev_index:
                first_index = i
            prev_index = i
            return first_index

        groups = groupby(sorted_keys, first_index_of_preceding_adjacent_elements)
        first, adjacent_indexes = next(groups)

        if first > 0:
            yield EmptyRegion(0, length=sorted_keys[0])
        occupied = OccupiedRegion([items[i] for i in adjacent_indexes], start=first)
        yield occupied

        for first, adjacent_indexes in groups:
            empty_start = occupied.start + occupied.length
            yield EmptyRegion(start=empty_start, length=first - empty_start)
            occupied = OccupiedRegion([items[i] for i in adjacent_indexes], start=first)
            yield occupied

        empty_start = occupied.start + occupied.length
        if empty_start <= max_index:
            yield EmptyRegion(start=empty_start, length=max_index - empty_start + 1)

    def __iter__(self) -> Iterator[T | JSHoleType]:
        for region in self.regions():
            if region.items is None:
                yield from repeat(JSHole, region.length)
            else:
                yield from region.items
