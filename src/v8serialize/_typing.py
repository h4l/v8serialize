from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableSequence, Sequence
from enum import Enum, auto
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar, runtime_checkable

_T_co = TypeVar("_T_co", covariant=True)
_VT_co = TypeVar("_VT_co", covariant=True)
_HoleT_co = TypeVar("_HoleT_co", covariant=True)

if not TYPE_CHECKING:
    # The runtime Protocol classes need to use the right number of type args,
    # but they're not type checked so their names don't matter.
    _Dummy = TypeVar("_Dummy")
    _Dummy2 = TypeVar("_Dummy2")


# The type definitions here all have TYPE_CHECKING and runtime versions. This is
# because of the fact that Sequence and MutableSequence are ABC classes, and
# it's not allowed to have a derived class inherit both an ABC and Protocol.
# We need to define our own specialised extension protocols of Sequence and
# MutableSequence, and we want other classes to be able to extend our protocols
# without also inheriting the ABC implementations of Sequence. e.g. so that you
# can extend the list class plus our protocol and manually add our methods,
# while using list's Sequence implementation.

# The general rule here is that the TYPE_CHECKING version should inherit the
# actual typing.XXX type we want, e.g. Mapping. The runtime version should only
# inherit Protocol, plus perhaps any of our similarly-defined protocols it
# needs.
#
# The runtime version needs to use @runtime_checkable plus stub method
# definitions, so that isinstance checks know which callable properties to look
# for. Also use typing.XXX.register() on the runtime version so that it becomes
# a virtual subclass of the intended type, so that
# isinstance(typing.XXX, runtime_instance) works at runtime.

if TYPE_CHECKING:

    class ElementsView(Mapping[int, _VT_co]):
        """A live view of the indexes holding values in a SparseSequence.

        The ElementsView provides access to a SparseSequence's values as a
        Mapping, without any missing values. The iteration order may or may not
        be defined, according to the `order` property.
        """

        @property
        def order(self) -> Order:
            """The iteration order of the elements.

            Corresponds to the `order` kwarg of `SparseSequence`'s `elements()` and
            `element_indexes()`.
            """

else:

    @runtime_checkable
    class ElementsView(Protocol[_Dummy]):
        # test/test_protocol_dataclass_interaction.py
        order = ...

    Mapping.register(ElementsView)

if not TYPE_CHECKING:

    @runtime_checkable
    class SparseSequence(Protocol[_Dummy, _Dummy2]):
        # test/test_protocol_dataclass_interaction.py
        hole_value = ...
        elements_used = ...
        element_indexes = ...
        elements = ...

    Sequence.register(SparseSequence)

else:

    class SparseSequence(Sequence["_T_co | _HoleT_co"], Generic[_T_co, _HoleT_co]):
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

        def element_indexes(self, *, order: Order = ...) -> Iterator[int]:
            """Iterate over the indexes in the sequence that are not holes.

            `order` is `Order.ASCENDING` if not specified. `Order.UNORDERED` allows
            the implementation to use whichever order is most efficient.
            """

        def elements(self, *, order: Order = ...) -> ElementsView[_T_co]:
            """Get a live view of the index elements with existant values.

            `order` is `Order.ASCENDING` if not specified. `Order.UNORDERED` allows
            the implementation to use whichever order is most efficient.

            This is analogous to the `items()` method of `Mapping`s.
            """


class Order(Enum):
    UNORDERED = auto()
    ASCENDING = auto()
    DESCENDING = auto()


if not TYPE_CHECKING:

    @runtime_checkable
    class SparseMutableSequence(SparseSequence[_Dummy, _Dummy2], Protocol):
        # test/test_protocol_dataclass_interaction.py
        resize = ...

    MutableSequence.register(SparseMutableSequence)

else:

    class SparseMutableSequence(
        MutableSequence["_T_co | _HoleT_co"], SparseSequence[_T_co, _HoleT_co]
    ):
        """
        A writable extension of [`SparseSequence`].

        [`SparseSequence`]: `v8serialize.SparseSequence`
        """

        def resize(self, length: int) -> None:
            """
            Change the length of the array.

            Elements are dropped if the length is reduced, or gaps are created
            at the end if the length is increased.
            """
