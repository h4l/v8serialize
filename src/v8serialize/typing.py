from __future__ import annotations

from typing import (
    Any,
    Collection,
    Generic,
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    Protocol,
    Self,
    TypeVar,
    ValuesView,
    overload,
)

_T = TypeVar("_T")
_KT_co = TypeVar("_KT_co", covariant=True)
_T_co = TypeVar("_T_co", covariant=True)
_VT_co = TypeVar("_VT_co", covariant=True)
_HoleT_co = TypeVar("_HoleT_co", covariant=True)

# These definitions are based on:
# https://github.com/python/typeshed/blob/8a7f09e3511f3a1d0428/stdlib/typing.pyi


# Same as typing.Reversible — if we use that directly it results in an error at
# runtime: TypeError: Cannot create a consistent method resolution
class Reversible(Iterable[_T_co], Protocol[_T_co]):
    def __reversed__(self) -> Iterator[_T_co]: ...


class SequenceProtocol(
    Collection[_T_co],
    Reversible[_T_co],
    Protocol,
):
    """The same interface as typing.Sequence, but actually a Protocol, not an ABC."""

    @overload
    def __getitem__(self, index: int, /) -> _T_co: ...

    @overload
    def __getitem__(self, index: slice, /) -> Self: ...

    # Mixin methods
    def index(self, value: Any, start: int = 0, stop: int = ...) -> int: ...
    def count(self, value: Any) -> int: ...
    def __contains__(self, value: object) -> bool: ...
    def __iter__(self) -> Iterator[_T_co]: ...
    def __reversed__(self) -> Iterator[_T_co]: ...


class MutableSequenceProtocol(SequenceProtocol[_T], Protocol):
    """Same interface as typing.MutableSequence, but actually a Protocol, not an ABC."""

    def insert(self, index: int, value: _T) -> None: ...

    @overload
    def __getitem__(self, index: int) -> _T: ...
    @overload
    def __getitem__(self, index: slice) -> Self: ...

    @overload
    def __setitem__(self, index: int, value: _T) -> None: ...
    @overload
    def __setitem__(self, index: slice, value: Iterable[_T]) -> None: ...

    @overload
    def __delitem__(self, index: int) -> None: ...
    @overload
    def __delitem__(self, index: slice) -> None: ...

    # Mixin methods
    def append(self, value: _T) -> None: ...
    def clear(self) -> None: ...
    def extend(self, values: Iterable[_T]) -> None: ...
    def reverse(self) -> None: ...
    def pop(self, index: int = -1) -> _T: ...
    def remove(self, value: _T) -> None: ...
    def __iadd__(self, values: Iterable[_T]) -> Self: ...


class MappingViews(Generic[_KT_co, _VT_co], Protocol):
    """Just the items(), keys() and values() views from Mapping."""

    def items(self) -> ItemsView[_KT_co, _VT_co]: ...
    def keys(self) -> KeysView[_KT_co]: ...
    def values(self) -> ValuesView[_VT_co]: ...


class SparseSequence(
    MappingViews[int, _T_co],  # only contains existant, non-hole values
    SequenceProtocol[_T_co | _HoleT_co],  # contains both holes and values
    Protocol,
):
    """A Sequence that can have holes — indexes with no value present.

    Similar to an ordered dict with int keys, but the empty values have an
    explicit type `_HoleT_co`.

    Unlike a dict, the bounds are defined. Indexing with __getitem__ returns the
    hole value instead of raising a KeyError as dict does. Accessing
    out-of-bound values raises an IndexError as other Sequences do.

    Like a dict, it has items(), keys() and values() views, which contain just
    the existant values, not holes.
    """

    @property
    def length(self) -> int:
        """The number of elements in the array, either values or empty holes.

        The same as __len__, but exists so that the mutable version can use a
        length setter to grow/shrink the bounds.
        """

    @property
    def elements_used(self) -> int:
        """The number of index positions that are not holes."""


class SparseMutableSequence(
    MutableSequenceProtocol[_T_co | _HoleT_co],
    SparseSequence[_T_co, _HoleT_co],
    Protocol,
):
    """A writable extension of SparseSequence."""

    @property
    def length(self) -> int:
        """The number of elements in the array, either values or empty gaps."""
        return len(self)

    @length.setter
    def length(self, length: int) -> None:
        """Change the length of the array. Elements are dropped if the length is
        reduced, or gaps are created at the end if the length is increased."""
