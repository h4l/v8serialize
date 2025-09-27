from __future__ import annotations

from abc import ABCMeta
from collections.abc import Iterable, Iterator, MutableSet
from dataclasses import dataclass
from typing import TYPE_CHECKING, AbstractSet, overload

from v8serialize._recursive_eq import recursive_eq
from v8serialize.jstypes import _repr
from v8serialize.jstypes._equality import JSSameValueZero, same_value_zero

if TYPE_CHECKING:
    from typing_extensions import Self, TypeVar

    T = TypeVar("T", default=object)
else:
    from typing import TypeVar

    T = TypeVar("T")

U = TypeVar("U")


@recursive_eq
@dataclass(slots=True)
class JSSet(MutableSet[T], metaclass=ABCMeta):
    """
    A Python equivalent of [JavaScript's Set][Set].

    `JSSet` is a [Python set] that uses object identity rather than `==` for
    member equality, and allows members which are not [hashable].

    `JSSet` replicates the behaviour of [JavaScript's Set][Set] type, which
    considers members equal by the [same-value-zero] rules (very close to
    `Object.is()` / `===`).

    [Python set]: https://docs.python.org/3/library/stdtypes.html#types-set
    [Set]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/\
Global_Objects/Set
    [same-value-zero]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/\
Equality_comparisons_and_sameness#same-value-zero_equality
    [hashable]: https://docs.python.org/3/glossary.html#term-hashable
    [`jstypes.same_value_zero`]: `v8serialize.jstypes.same_value_zero`

    Parameters
    ----------
    iterable
        Items to initialize the `JSSet` with. Can be empty or not specified.

    Notes
    -----
    `JSSet` must be initialized using an iterable or regular list instead of a
    `set` if any keys are non-hashable or are equal using `==`.

    See Also
    --------
    [`jstypes.same_value_zero`] : A key function that provides same-value-zero equality.

    Examples
    --------
    Equality between JSSet instances works as if you compared a list of both
    set's elements. When comparing JSSet to a normal Python `set`, equality
    works as if the JSSet was a regular set — order does not matter and the
    number of elements must be equal. Same-value-zero is only used for internal
    membership checks, not for external equality.

    Equality examples:

    >>> a, b = bytearray(), bytearray()  # non-hashable
    >>> assert a == b
    >>> assert a is not b

    Equality between two JSSets behaves like the list of members (JSSets
    remember insertion order):

    >>> JSSet([a, b]) == JSSet([a, b])
    True
    >>> JSSet([a, b]) == JSSet([b, a])
    True
    >>> JSSet([a, a]) == JSSet([b, b])
    True

    These behave like:

    >>> list(JSSet([a, b])) == [b, a]
    True

    Equality between a JSSet and a normal `set` behaves as if the JSSet was a
    normal set. The sets must have the same number of members.

    Note that if there are non-hashable members, the sets can't be equal, as
    normal sets cannot contain non-hashable members.

    >>> # hashable, distinct instances
    >>> x, y, z = tuple([0]), tuple([0]), tuple([0])
    >>> assert x == y and y == z
    >>> assert x is not y and y is not z

    >>> jss_dup, jss_no_dup, s = JSSet([x, y]), JSSet([x]), set([y, z])
    >>> jss_dup, jss_no_dup, s
    (JSSet([(0,), (0,)]), JSSet([(0,)]), {(0,)})

    >>> jss_no_dup == s
    True
    >>> jss_dup == s  # different number of members
    False

    Equivalent to

    >>> set([x]) == set([y, z])
    True
    """

    __members: dict[JSSameValueZero, T]

    @overload
    def __init__(self, /) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[T], /) -> None: ...

    def __init__(self, iterable: Iterable[T] | None = None, /) -> None:
        self.__members = {}
        if iterable is not None:
            self |= iterable

    def add(self, value: T) -> None:
        self.__members[same_value_zero(value)] = value

    def discard(self, value: T) -> None:
        key = same_value_zero(value)
        if key in self.__members:
            del self.__members[key]

    def __contains__(self, value: object, /) -> bool:
        return same_value_zero(value) in self.__members

    def __eq__(self, other: object) -> bool:
        # As with JSMap, JSSet are equal to other JSSet if they contain elements
        # in the same order that are pair-wise equal to each other.
        # See JSMap.__eq__ for more on this approach.
        if self is other:
            return True
        if isinstance(other, JSSet):
            if len(self) != len(other):
                return False
            # Two JSSets are equal if they contain equal members in the same order
            return all(
                x == y
                for x, y in zip(self.__members.values(), other.__members.values())
            )
        if isinstance(other, AbstractSet):
            if len(self) != len(other):
                return False
            # Other set types are equal if they're equal to a set containing our
            # members (if our members are hashable).
            try:
                self_as_set = set(self.__members.values())
            except Exception:
                # We have an unhashable member. Fall back to comparing the other
                # items in order, in the same way as if it were a JSSet
                return all(x == y for x, y in zip(self.__members.values(), other))
            return self_as_set == other
        return NotImplemented

    def __iter__(self) -> Iterator[T]:
        return iter(self.__members.values())

    def __len__(self) -> int:
        return len(self.__members)

    def __repr__(self) -> str:
        return _repr.js_repr(self)

    # Overrides for optimisation purposes
    def clear(self) -> None:
        self.__members.clear()

    def __ior__(self, it: Iterable[T]) -> Self:  # type: ignore[override,misc]
        self.__members.update((same_value_zero(x), x) for x in it)
        return self

    if TYPE_CHECKING:
        # Base types require `it` arguments to be sets, but any iterable is OK
        def __iand__(self, it: Iterable[object]) -> Self: ...
        def __ixor__(self, it: Iterable[T]) -> Self: ...  # type: ignore[override,misc]
        def __isub__(self, it: Iterable[object]) -> Self: ...

        def __and__(self, other: Iterable[object]) -> Self: ...
        def __or__(self, other: Iterable[U]) -> JSSet[U | T]: ...
        def __sub__(self, other: Iterable[object]) -> Self: ...
        def __xor__(self, other: Iterable[U]) -> JSSet[U | T]: ...
