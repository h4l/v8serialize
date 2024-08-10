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


class ArrayProperties(MutableSequence[T | JSUndefinedType], Generic[T]):
    pass


class SparseArrayRequired(IndexError):
    pass


MAX_ARRAY_LENGTH: Final = 2**32 - 1


@dataclass(slots=True, init=False)
class DenseArrayProperties(ArrayProperties[T]):
    _items: list[T | JSUndefinedType]

    def __init__(self, items: Iterable[T]) -> None:
        self._items = list(items)

    @overload
    def __getitem__(self, i: int, /) -> T | JSUndefinedType: ...

    @overload
    def __getitem__(self, i: slice, /) -> MutableSequence[T | JSUndefinedType]: ...

    def __getitem__(
        self, i: int | slice, /
    ) -> T | JSUndefinedType | MutableSequence[T | JSUndefinedType]:
        if isinstance(i, slice):
            raise NotImplementedError
        return self._items[i]

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
        if len(self) <= i < MAX_ARRAY_LENGTH:
            raise SparseArrayRequired
        self._items[i] = cast(T, value)

    @overload
    def __delitem__(self, i: int, /) -> None: ...

    @overload
    def __delitem__(self, i: slice, /) -> None: ...

    def __delitem__(self, i: int | slice, /) -> None:
        if isinstance(i, slice):
            raise NotImplementedError
        if len(self) <= i < MAX_ARRAY_LENGTH:
            return
        del self._items[i]

    def insert(self, i: int, o: T | JSUndefinedType) -> None:
        # Python lists can insert after the last index which appends. So
        # inserting at len(self) is the same as appending, which keeps us dense.
        if len(self) < i < MAX_ARRAY_LENGTH:
            raise SparseArrayRequired
        self._items.insert(i, o)

    def append(self, value: T | JSUndefinedType) -> None:
        self._items.append(value)

    def __len__(self) -> int:
        return len(self._items)


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
