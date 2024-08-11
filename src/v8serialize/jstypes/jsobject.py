from abc import ABC
from collections import abc
from dataclasses import dataclass
from types import NotImplementedType
from typing import (
    TYPE_CHECKING,
    Final,
    Generic,
    Iterable,
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

KT = TypeVar("KT")
T = TypeVar("T")


# TODO: rename JSHole
class HoleType:
    """Representation of the explicit empty elements in V8's fixed arrays.

    See v8serialize.constants.SerializationTag.kTheHole. We don't use that constant
    directly, because that would prevent using it as a regular value. This is an
    internal type that API users should not use.
    """

    def __init__(self) -> None:
        if "HoleType" in globals():
            raise AssertionError("Cannot instantiate HoleType")


Hole: Final = HoleType()


class ArrayProperties(
    MutableSequence[T | JSUndefinedType], Sequence[T | JSUndefinedType], Generic[T]
):
    pass


@dataclass(slots=True)
class SparseArrayRequired(IndexError):
    elements_used: int
    length: int

    def __str__(self) -> str:
        return repr(self)


MAX_ARRAY_LENGTH: Final = 2**32 - 1
MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4
MAX_DENSE_ARRAY_HOLE_RATIO = 1 / 4

# TODO: should we be explicit about Holes? e.g. treat elements as explicitly T | HoleType
# Then in the JSObject we can hide this detail and return JSUndefined


@dataclass(slots=True, init=False)
class DenseArrayProperties(ArrayProperties[T]):
    _items: list[T | HoleType]
    _max_index: int
    _elements_used: int

    def __init__(self, items: Iterable[T]) -> None:
        self._items = list(items)
        self._max_index = len(self._items) - 1
        self._elements_used = len(self._items)

    def _ensure_capacity(self, elements_used: int, length: int) -> None:
        if (
            elements_used >= MIN_SPARSE_ARRAY_SIZE
            and elements_used / length < MIN_DENSE_ARRAY_USED_RATIO
        ):
            raise SparseArrayRequired(elements_used=elements_used, length=length)
        required_capacity = length - len(self._items)
        assert required_capacity > 0
        self._items.extend([Hole] * required_capacity)

    @property
    def _has_holes(self) -> bool:
        return self._elements_used < len(self._items)

    def _normalise_index(self, i: int) -> int:
        """Flip a negative index (offset from end) to non-negative and check bounds."""
        if i >= 0:
            if i >= MAX_ARRAY_LENGTH:
                raise IndexError(i)
            return i
        _i = len(self) - i
        if _i < 0:
            raise IndexError(i)
        return _i

    @overload
    def __getitem__(self, i: int, /) -> T | JSUndefinedType: ...

    @overload
    def __getitem__(self, i: slice, /) -> ArrayProperties[T]: ...

    def __getitem__(
        self, i: int | slice, /
    ) -> T | JSUndefinedType | ArrayProperties[T]:
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)
        if self._has_holes:
            value = self._items[i]
            return JSUndefined if value is Hole else value
        return self._items[i]

    @overload
    def __setitem__(self, i: int, value: T, /) -> None: ...

    @overload
    def __setitem__(self, i: slice, value: Iterable[T], /) -> None: ...

    def __setitem__(
        self,
        i: int | slice,
        value: T | Iterable[T],
        /,
    ) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)

        if i >= len(self._items):
            self._ensure_capacity(self._elements_used + 1, i + 1)

        if self._items[i] is Hole:
            self._elements_used += 1
        if i > self._max_index:
            self._max_index = i
        self._items[i] = value

    @overload
    def __delitem__(self, i: int, /) -> None: ...

    @overload
    def __delitem__(self, i: slice, /) -> None: ...

    def __delitem__(self, i: int | slice, /) -> None:
        """Delete the item at index i.

        This implements the normal Python list behaviour of shifting following
        elements back, not the JavaScript behaviour of leaving a hole.
        """
        if isinstance(i, slice):
            raise NotImplementedError
        i = self._normalise_index(i)
        if len(self) <= i:
            return

        if self._has_holes and i == self._max_index:
            self._items[i] = Hole
            # find the next lowest used element to be the next max_index
            for n in range(i - 1, -1, -1):
                if self._items[n] is not Hole:
                    self._max_index = n
                    break
            else:  # all elements were holes
                self._max_index = -1
            return
        del self._items[i]
        self._max_index -= 1

    def insert(self, i: int, o: T) -> None:
        """Insert a value before the values at index i.

        This implements the normal Python list behaviour of inserting indexes
        beyond end of the list immediately after the end. I.e. it doesn't create
        a gap at the end.
        """
        i = self._normalise_index(i)

        # Python arrays treat inserting beyond the end as inserting immediately
        # after the final element.

        i = min(i, self._max_index + 1)
        self._items.insert(i, o)
        self._max_index += 1

    def append(self, value: T) -> None:
        self.insert(len(self), value)

    def __len__(self) -> int:
        return self._max_index + 1


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


@dataclass(slots=True, init=False)
class LazySparseArrayProperties(ArrayProperties[T]):
    _items: dict[int, T | JSUndefinedType]
    _sorted_keys: list[int]
    _max_index: int

    def __init__(self, items: Iterable[tuple[int, T | JSUndefinedType]]) -> None:
        max_index = -1
        _items = SortedDict[int, T | JSUndefinedType]()
        for i, v in items:
            if not (0 <= i < MAX_ARRAY_LENGTH):
                raise IndexError(i)
            max_index = max(max_index, i)
            _items[i] = v
        self._items = _items
        self._max_index = max_index

    @overload
    def __getitem__(self, i: int, /) -> T | JSUndefinedType: ...

    @overload
    def __getitem__(self, i: slice, /) -> MutableSequence[T | JSUndefinedType]: ...

    def __getitem__(
        self, i: int | slice, /
    ) -> T | JSUndefinedType | MutableSequence[T | JSUndefinedType]:
        if isinstance(i, slice):
            raise NotImplementedError

        if i < 0:
            _i = len(self) - i
            if _i < 0:
                raise IndexError(i)
            i = _i
        return self._items.get(i, JSUndefined)

    @overload
    def __setitem__(self, i: int, value: T | JSUndefinedType, /) -> None: ...

    @overload
    def __setitem__(
        self, i: slice, value: Iterable[T | JSUndefinedType], /
    ) -> None: ...

    def __setitem__(
        self,
        i: int | slice,
        value: T | JSUndefinedType | Iterable[T | JSUndefinedType],
        /,
    ) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        if i >= MAX_ARRAY_LENGTH:
            raise IndexError(i)
        if i < 0:
            _i = len(self) - i
            if _i < 0:
                raise IndexError(i)
            i = _i

        if i > self._max_index:
            self._max_index = i
        self._items[i] = cast(T, value)

    @overload
    def __delitem__(self, i: int, /) -> None: ...

    @overload
    def __delitem__(self, i: slice, /) -> None: ...

    def __delitem__(self, i: int | slice, /) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        if i >= MAX_ARRAY_LENGTH:
            raise IndexError(i)
        if i < 0:
            _i = len(self) - i
            if _i < 0:
                raise IndexError(i)
            i = _i

        if len(self) <= i < MAX_ARRAY_LENGTH:
            return
        del self._items[i]
        if i == self._max_index:
            self._max_index = -1 if len(self._items) == 0 else self._items_keys[-1]

    def insert(self, i: int, o: T | JSUndefinedType) -> None:
        if i >= MAX_ARRAY_LENGTH:
            raise IndexError(i)
        if i < 0:
            _i = len(self) - i
            if _i < 0:
                raise IndexError(i)
            i = _i

        if i >= self._max_index:
            self._items[i] = o
            self._max_index = max(i, self._max_index)
            return

        # shift all keys >= i
        # TODO: how do we find the closest index to a key? Or get a slice of all
        #   things >= a key?
        # TODO: maybe implement w/ bisect, I feel like this'll be simpler
        #   Plus we can have 0 deps. :)
        # for ii in self._items_keys[i:]
        raise NotImplementedError
        self._items.insert(i, o)

    def append(self, value: T | JSUndefinedType) -> None:
        self._items.append(value)

    def __len__(self) -> int:
        return self._max_index + 1


class JSObject(MutableMapping[str | int, object], ABC):
    """A Python model of JavaScript plain objects, limited to the behaviour that
    can be transferred with V8 serialization (which is essentially the behaviour
    of [`structuredClone()`]).

    [`structuredClone()`]: https://developer.mozilla.org/en-US/docs/Web/API/structuredClone

    The behaviour implemented aims to match that describe by the [ECMA-262] spec.
    [ECMA-262]: https://tc39.es/ecma262/#sec-object-type

    JSObject is also an ABC can other types can register as virtual subtypes of
    in order to serialize themselves as JavaScript Objects.
    """

    array_properties: ArrayProperties

    # TODO: should we provide a specialised map that acts like JavaScript
    #   objects? e.g. allows for number or string keys that are synonyms. Plus
    #   insertion ordering.
    pass
