from __future__ import annotations

from enum import Enum, auto
from typing import (
    Any,
    Collection,
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
_KT = TypeVar("_KT")
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


class MappingProtocol(Collection[_KT], Protocol[_KT, _VT_co]):
    # TODO: We wish the key type could also be covariant, but that doesn't work,
    # see discussion in https://github.com/python/typing/pull/273.
    def __getitem__(self, key: _KT, /) -> _VT_co: ...

    # Mixin methods
    @overload
    def get(self, key: _KT, /) -> _VT_co | None: ...
    @overload
    def get(self, key: _KT, /, default: _VT_co | _T) -> _VT_co | _T: ...
    def items(self) -> ItemsView[_KT, _VT_co]: ...
    def keys(self) -> KeysView[_KT]: ...
    def values(self) -> ValuesView[_VT_co]: ...
    def __contains__(self, key: object, /) -> bool: ...
    def __eq__(self, other: object, /) -> bool: ...


class ElementsView(MappingProtocol[int, _VT_co], Protocol):
    """
    A read-only live view of the index elements in a SparseSequence with
    existant values.
    """

    @property
    def order(self) -> Order | None: ...


class SparseSequence(SequenceProtocol[_T_co | _HoleT_co], Protocol):
    """A Sequence that can have holes — indexes with no value present.

    Similar to an ordered dict with int keys, but the empty values have a type
    that need not be None — the `hole_value` property — with type `_HoleT_co`.

    Unlike a dict, the bounds are defined — __len__() is the length including
    holes. Indexing with __getitem__ returns the hole value instead of raising a
    KeyError as dict does. Accessing out-of-bound values raises an IndexError as
    other Sequences do.

    `elements()` provides a view of the non-hole values as a Mapping.
    """

    @property
    def hole_value(self) -> _HoleT_co:
        """Get the empty value used by the sequence to represent holes."""

    @property
    def elements_used(self) -> int:
        """The number of index positions that are not holes."""

    def element_indexes(self, *, order: Order | None = ...) -> Iterator[int]:
        """Iterate over the indexes in the sequence that are not holes."""

    def elements(self, *, order: Order | None = ...) -> ElementsView[_T_co]:
        """
        Get a read-only Mapping containing a live view of the index elements
        with existant values.
        """


class Order(Enum):
    UNORDERED = auto()
    ASCENDING = auto()
    DESCENDING = auto()


# A read-only live view of the index elements in a SparseSequence with existant values.


class SparseMutableSequence(
    MutableSequenceProtocol[_T_co | _HoleT_co],
    SparseSequence[_T_co, _HoleT_co],
    Protocol,
):
    """A writable extension of SparseSequence."""

    def resize(self, length: int) -> None:
        """
        Change the length of the array. Elements are dropped if the length is
        reduced, or gaps are created at the end if the length is increased.
        """
