from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from itertools import groupby
from typing import (
    TYPE_CHECKING,
    Final,
    Generator,
    Generic,
    Iterable,
    Iterator,
    MutableMapping,
    MutableSequence,
    Protocol,
    Sequence,
    TypeVar,
    cast,
    overload,
)

from sortedcontainers import SortedDict

if TYPE_CHECKING:
    from sortedcontainers.sorteddict import SortedKeysView

from v8serialize.jstypes.jsundefined import JSUndefined, JSUndefinedType

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
    @abstractmethod
    def has_holes(self) -> bool: ...

    @property
    @abstractmethod
    def max_index(self) -> int: ...

    @property
    @abstractmethod
    def elements_used(self) -> int: ...

    @abstractmethod
    def regions(self) -> Generator[EmptyRegion | OccupiedRegion[T], None, None]: ...

    def __eq__(self, other: object) -> bool:
        return (
            other is self
            or isinstance(other, ArrayProperties)
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

    def __init__(self, items: Iterable[tuple[int, T]]) -> None:
        items = iter(items)
        try:
            i, v = next(items)
        except StopIteration:
            raise ValueError("items cannot be empty")
        self.start = i
        self.items = [v for group in [[(i, v)], items] for (_, v) in group]
        self.length = len(self.items)

    def __len__(self) -> int:
        return self.length


# @dataclass(slots=True)
# class SparseArrayRequired(IndexError):
#     elements_used: int
#     length: int

#     def __str__(self) -> str:
#         return repr(self)


MAX_ARRAY_LENGTH: Final = 2**32 - 1
MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4
MAX_DENSE_ARRAY_HOLE_RATIO = 1 / 4

# TODO: should we be explicit about Holes? e.g. treat elements as explicitly T | HoleType
# Then in the JSObject we can hide this detail and return JSUndefined


@dataclass(slots=True, init=False, eq=False)
class DenseArrayProperties(ArrayProperties[T]):
    _items: list[T | JSHoleType]
    _max_index: int
    _elements_used: int

    def __init__(self, items: Iterable[T | JSHoleType]) -> None:
        _items = []
        max_index = -1
        elements_used = 0
        for i, v in enumerate(items):
            if v is not JSHole:
                max_index = i
                elements_used += 1
            _items.append(v)
        self._items = _items
        self._max_index = max_index
        self._elements_used = elements_used

    @property
    def has_holes(self) -> bool:
        return self._elements_used < len(self._items)

    @property
    def max_index(self) -> int:
        """The highest index containing a value that isn't a JSHole.
        -1 if no values exist.
        """
        return self._max_index

    @property
    def elements_used(self) -> int:
        """The highest index containing a value that isn't a JSHole.
        -1 if no values exist.
        """
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
                self._max_index = max(i, self._max_index)
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
        max_index = self._max_index
        del items[i]

        if i > max_index:
            assert current is JSHole
            return

        if current is JSHole:
            assert i < max_index
            self._max_index = max_index - 1
            return

        self._elements_used -= 1
        if i == max_index:
            # find the next lowest used element to be the next max_index
            for n in range(i - 1, -1, -1):
                if items[n] is not JSHole:
                    self._max_index = n
                    break
            else:  # all elements were holes
                self._max_index = -1
            return
        self._max_index = max_index - 1

    def insert(self, i: int, o: T | JSHoleType) -> None:
        i = self._normalise_index(i)

        max_index = self._max_index
        self._items.insert(i, o)

        if o is JSHole:
            if i > max_index:
                return
            self._max_index = max_index + 1
        else:
            self._elements_used += 1
            self._max_index = max(max_index + 1, i)

    def append(self, value: T | JSHoleType) -> None:
        items = self._items
        items.append(value)
        if value is not JSHole:
            self._max_index = len(items) - 1
            self._elements_used += 1

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T | JSHoleType]:
        return iter(self._items)

    def regions(self) -> Generator[EmptyRegion | OccupiedRegion[T], None, None]:
        return array_properties_regions(self)


# # TODO: throw this away and just use a simple list which can contain Hole
# @dataclass(slots=True, init=False)
# class DenseArrayProperties(ArrayProperties[T]):
#     _items: list[T | HoleType]
#     _max_index: int
#     _elements_used: int

#     def __init__(self, items: Iterable[T]) -> None:
#         self._items = list(items)
#         self._max_index = len(self._items) - 1
#         self._elements_used = len(self._items)

#     def _ensure_capacity(self, elements_used: int, length: int) -> None:
#         if (
#             elements_used >= MIN_SPARSE_ARRAY_SIZE
#             and elements_used / length < MIN_DENSE_ARRAY_USED_RATIO
#         ):
#             raise SparseArrayRequired(elements_used=elements_used, length=length)
#         required_capacity = length - len(self._items)
#         assert required_capacity > 0
#         self._items.extend([Hole] * required_capacity)

#     @property
#     def _has_holes(self) -> bool:
#         return self._elements_used < len(self._items)

#     def _normalise_index(self, i: int) -> int:
#         """Flip a negative index (offset from end) to non-negative and check bounds."""
#         if i >= 0:
#             if i >= MAX_ARRAY_LENGTH:
#                 raise IndexError(i)
#             return i
#         _i = len(self) - i
#         if _i < 0:
#             raise IndexError(i)
#         return _i

#     @overload
#     def __getitem__(self, i: int, /) -> T | JSUndefinedType: ...

#     @overload
#     def __getitem__(self, i: slice, /) -> ArrayProperties[T]: ...

#     def __getitem__(
#         self, i: int | slice, /
#     ) -> T | JSUndefinedType | ArrayProperties[T]:
#         if isinstance(i, slice):
#             raise NotImplementedError
#         i = self._normalise_index(i)
#         if self._has_holes:
#             value = self._items[i]
#             return JSUndefined if value is Hole else value
#         return self._items[i]

#     @overload
#     def __setitem__(self, i: int, value: T, /) -> None: ...

#     @overload
#     def __setitem__(self, i: slice, value: Iterable[T], /) -> None: ...

#     def __setitem__(
#         self,
#         i: int | slice,
#         value: T | Iterable[T],
#         /,
#     ) -> None:
#         if isinstance(i, slice):
#             raise NotImplementedError
#         i = self._normalise_index(i)

#         if i >= len(self._items):
#             self._ensure_capacity(self._elements_used + 1, i + 1)

#         if self._items[i] is Hole:
#             self._elements_used += 1
#         if i > self._max_index:
#             self._max_index = i
#         self._items[i] = value

#     @overload
#     def __delitem__(self, i: int, /) -> None: ...

#     @overload
#     def __delitem__(self, i: slice, /) -> None: ...

#     def __delitem__(self, i: int | slice, /) -> None:
#         """Delete the item at index i.

#         This implements the normal Python list behaviour of shifting following
#         elements back, not the JavaScript behaviour of leaving a hole.
#         """
#         if isinstance(i, slice):
#             raise NotImplementedError
#         i = self._normalise_index(i)
#         if len(self) <= i:
#             return

#         if self._has_holes and i == self._max_index:
#             self._items[i] = Hole
#             # find the next lowest used element to be the next max_index
#             for n in range(i - 1, -1, -1):
#                 if self._items[n] is not Hole:
#                     self._max_index = n
#                     break
#             else:  # all elements were holes
#                 self._max_index = -1
#             return
#         del self._items[i]
#         self._max_index -= 1

#     def insert(self, i: int, o: T) -> None:
#         """Insert a value before the values at index i.

#         This implements the normal Python list behaviour of inserting indexes
#         beyond end of the list immediately after the end. I.e. it doesn't create
#         a gap at the end.
#         """
#         i = self._normalise_index(i)

#         # Python arrays treat inserting beyond the end as inserting immediately
#         # after the final element.

#         i = min(i, self._max_index + 1)
#         self._items.insert(i, o)
#         self._max_index += 1

#     def append(self, value: T) -> None:
#         self.insert(len(self), value)

#     def __len__(self) -> int:
#         return self._max_index + 1


# @dataclass(slots=True, init=False)
# class SparseArrayProperties(ArrayProperties[T]):
#     _items: SortedDict[int, T | JSUndefinedType]
#     _items_keys: SortedKeysView[int]
#     _max_index: int

#     def __init__(self, items: Iterable[tuple[int, T | JSUndefinedType]]) -> None:
#         max_index = -1
#         _items = SortedDict[int, T | JSUndefinedType]()
#         for i, v in items:
#             if not (0 <= i < MAX_ARRAY_LENGTH):
#                 raise IndexError(i)
#             max_index = max(max_index, i)
#             _items[i] = v
#         self._items = _items
#         self._max_index = max_index

#     @overload
#     def __getitem__(self, i: int, /) -> T | JSUndefinedType: ...

#     @overload
#     def __getitem__(self, i: slice, /) -> MutableSequence[T | JSUndefinedType]: ...

#     def __getitem__(
#         self, i: int | slice, /
#     ) -> T | JSUndefinedType | MutableSequence[T | JSUndefinedType]:
#         if isinstance(i, slice):
#             raise NotImplementedError

#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i
#         return self._items.get(i, JSUndefined)

#     @overload
#     def __setitem__(self, i: int, value: T | JSUndefinedType, /) -> None: ...

#     @overload
#     def __setitem__(
#         self, i: slice, value: Iterable[T | JSUndefinedType], /
#     ) -> None: ...

#     def __setitem__(
#         self,
#         i: int | slice,
#         value: T | JSUndefinedType | Iterable[T | JSUndefinedType],
#         /,
#     ) -> None:
#         if isinstance(i, slice):
#             raise NotImplementedError
#         if i >= MAX_ARRAY_LENGTH:
#             raise IndexError(i)
#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i

#         if i > self._max_index:
#             self._max_index = i
#         self._items[i] = cast(T, value)

#     @overload
#     def __delitem__(self, i: int, /) -> None: ...

#     @overload
#     def __delitem__(self, i: slice, /) -> None: ...

#     def __delitem__(self, i: int | slice, /) -> None:
#         if isinstance(i, slice):
#             raise NotImplementedError
#         if i >= MAX_ARRAY_LENGTH:
#             raise IndexError(i)
#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i

#         if len(self) <= i < MAX_ARRAY_LENGTH:
#             return
#         del self._items[i]
#         if i == self._max_index:
#             self._max_index = -1 if len(self._items) == 0 else self._items_keys[-1]

#     def insert(self, i: int, o: T | JSUndefinedType) -> None:
#         if i >= MAX_ARRAY_LENGTH:
#             raise IndexError(i)
#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i

#         if i >= self._max_index:
#             self._items[i] = o
#             self._max_index = max(i, self._max_index)
#             return

#         # shift all keys >= i
#         # TODO: how do we find the closest index to a key? Or get a slice of all
#         #   things >= a key?
#         # TODO: maybe implement w/ bisect, I feel like this'll be simpler
#         #   Plus we can have 0 deps. :)
#         # for ii in self._items_keys[i:]
#         raise NotImplementedError
#         self._items.insert(i, o)

#     def append(self, value: T | JSUndefinedType) -> None:
#         self._items.append(value)

#     def __len__(self) -> int:
#         return self._max_index + 1


# @dataclass(slots=True, init=False)
# class LazySparseArrayProperties(ArrayProperties[T]):
#     _items: dict[int, T | JSUndefinedType]
#     _sorted_keys: list[int]
#     _max_index: int

#     def __init__(self, items: Iterable[tuple[int, T | JSUndefinedType]]) -> None:
#         max_index = -1
#         _items = SortedDict[int, T | JSUndefinedType]()
#         for i, v in items:
#             if not (0 <= i < MAX_ARRAY_LENGTH):
#                 raise IndexError(i)
#             max_index = max(max_index, i)
#             _items[i] = v
#         self._items = _items
#         self._max_index = max_index

#     @overload
#     def __getitem__(self, i: int, /) -> T | JSUndefinedType: ...

#     @overload
#     def __getitem__(self, i: slice, /) -> MutableSequence[T | JSUndefinedType]: ...

#     def __getitem__(
#         self, i: int | slice, /
#     ) -> T | JSUndefinedType | MutableSequence[T | JSUndefinedType]:
#         if isinstance(i, slice):
#             raise NotImplementedError

#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i
#         return self._items.get(i, JSUndefined)

#     @overload
#     def __setitem__(self, i: int, value: T | JSUndefinedType, /) -> None: ...

#     @overload
#     def __setitem__(
#         self, i: slice, value: Iterable[T | JSUndefinedType], /
#     ) -> None: ...

#     def __setitem__(
#         self,
#         i: int | slice,
#         value: T | JSUndefinedType | Iterable[T | JSUndefinedType],
#         /,
#     ) -> None:
#         if isinstance(i, slice):
#             raise NotImplementedError
#         if i >= MAX_ARRAY_LENGTH:
#             raise IndexError(i)
#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i

#         if i > self._max_index:
#             self._max_index = i
#         self._items[i] = cast(T, value)

#     @overload
#     def __delitem__(self, i: int, /) -> None: ...

#     @overload
#     def __delitem__(self, i: slice, /) -> None: ...

#     def __delitem__(self, i: int | slice, /) -> None:
#         if isinstance(i, slice):
#             raise NotImplementedError
#         if i >= MAX_ARRAY_LENGTH:
#             raise IndexError(i)
#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i

#         if len(self) <= i < MAX_ARRAY_LENGTH:
#             return
#         del self._items[i]
#         if i == self._max_index:
#             self._max_index = -1 if len(self._items) == 0 else self._items_keys[-1]

#     def insert(self, i: int, o: T | JSUndefinedType) -> None:
#         if i >= MAX_ARRAY_LENGTH:
#             raise IndexError(i)
#         if i < 0:
#             _i = len(self) - i
#             if _i < 0:
#                 raise IndexError(i)
#             i = _i

#         if i >= self._max_index:
#             self._items[i] = o
#             self._max_index = max(i, self._max_index)
#             return

#         # shift all keys >= i
#         # TODO: how do we find the closest index to a key? Or get a slice of all
#         #   things >= a key?
#         # TODO: maybe implement w/ bisect, I feel like this'll be simpler
#         #   Plus we can have 0 deps. :)
#         # for ii in self._items_keys[i:]
#         raise NotImplementedError
#         self._items.insert(i, o)

#     def append(self, value: T | JSUndefinedType) -> None:
#         self._items.append(value)

#     def __len__(self) -> int:
#         return self._max_index + 1


class JSObject(MutableMapping[KT, T], ABC):
    """A Python model of JavaScript plain objects, limited to the behaviour that
    can be transferred with V8 serialization (which is essentially the behaviour
    of [`structuredClone()`]).

    [`structuredClone()`]: https://developer.mozilla.org/en-US/docs/Web/API/structuredClone

    The behaviour implemented aims to match that describe by the [ECMA-262] spec.
    [ECMA-262]: https://tc39.es/ecma262/#sec-object-type

    JSObject is also an ABC can other types can register as virtual subtypes of
    in order to serialize themselves as JavaScript Objects.
    """

    # array_properties: ArrayProperties

    # TODO: should we provide a specialised map that acts like JavaScript
    #   objects? e.g. allows for number or string keys that are synonyms. Plus
    #   insertion ordering.
    pass
