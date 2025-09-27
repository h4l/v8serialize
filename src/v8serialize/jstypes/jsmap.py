from __future__ import annotations

from abc import ABCMeta
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass
from operator import itemgetter
from typing import TYPE_CHECKING, cast, overload

from v8serialize._recursive_eq import recursive_eq
from v8serialize.jstypes import _repr
from v8serialize.jstypes._equality import JSSameValueZero, same_value_zero

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem
    from typing_extensions import TypeGuard, TypeVar

    KT = TypeVar("KT", default=object)
    VT = TypeVar("VT", default=object)
else:
    from typing import TypeVar

    KT = TypeVar("KT")
    VT = TypeVar("VT")
U = TypeVar("U")


@recursive_eq
@dataclass(init=False, slots=True)
class JSMap(MutableMapping[KT, VT], metaclass=ABCMeta):
    """A Python equivalent of [JavaScript's Map][Map].

    `JSMap` is a [Mapping] that uses object identity rather than `==` for key
    equality, and allows keys which are not [hashable].

    `JSMap` replicates the behaviour of [JavaScript's Map][Map] type, which
    considers keys equal by the [same-value-zero] rules (very close to
    `Object.is()` / `===`).

    [Mapping]: https://docs.python.org/3/glossary.html#term-mapping
    [Map]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/Map
    [same-value-zero]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/\
Equality_comparisons_and_sameness#same-value-zero_equality
    [hashable]: https://docs.python.org/3/glossary.html#term-hashable
    [`jstypes.same_value_zero`]: `v8serialize.jstypes.same_value_zero`

    Parameters
    ----------
    init
        Another Mapping to copy items from, or a series of `(key, value)` pairs.
    kwargs
        Keyword arguments become items, and override items from `init` if
        names occur in both.

    Notes
    -----
    `JSMap` must be initialized using an iterable of item pairs instead of a
    `dict` if any keys are non-hashable or are equal using `==`.

    See Also
    --------
    [`jstypes.same_value_zero`] : A key function that provides same-value-zero equality.


    Examples
    --------
    JSMap is like a Python dict, but as in JavaScript, any object can be a JSMap
    key — keys don't need to be hashable.

    >>> from v8serialize.jstypes import JSObject
    >>> bob, alice = JSObject(name="Bob"), JSObject(name="Alice")
    >>> m = JSMap([(bob, 1), (alice, 2)])
    >>> m
    JSMap([(JSObject(name='Bob'), 1), (JSObject(name='Alice'), 2)])
    >>> m[alice]
    2

    Equality between JSMap instances works as if you compared a list of both
    map's items. When comparing JSMap to normal Python `dict`, equality works as
    if the JSMap was a normal dict — order does not matter and the number of
    items must be equal. Same-value-zero is only used for internally matching
    keys, not for external equality.

    Equality examples:

    >>> a, b = bytearray(), bytearray()  # non-hashable but supports ==
    >>> assert a == b
    >>> assert a is not b

    Because a and b are equal, lists containing them in different orders are
    equal:
    >>> [a, b] == [b, a]
    True

    Equality between two JSMaps behaves like the list of items (JSMaps remember
    insertion order):

    >>> JSMap([(a, 0), (b, 0)]) == JSMap([(a, 0), (b, 0)])
    True
    >>> JSMap([(a, 0), (b, 0)]) == JSMap([(b, 0), (a, 0)])
    True
    >>> JSMap([(a, 0), (a, 0)]) == JSMap([(b, 0), (b, 0)])
    True

    These behave like:

    >>> list(JSMap([(a, 0), (b, 0)]).items()) == [(b, 0), (a, 0)]
    True

    Equality between a JSMap and a normal `dict` behaves as if the JSMap was a
    normal dict. The maps must have the same number of items.

    >>> # hashable, distinct instances
    >>> x, y, z = tuple([0]), tuple([0]), tuple([0])
    >>> assert x == y and y == z
    >>> assert x is not y and y is not z

    >>> jsm_dup, jsm_no_dup = JSMap([(x, 0), (y, 0)]), JSMap([(x, 0)])
    >>> m = dict([(y, 0), (z, 0)])
    >>> jsm_dup, jsm_no_dup, m
    (JSMap([((0,), 0), ((0,), 0)]), JSMap({(0,): 0}), {(0,): 0})

    >>> jsm_no_dup == m
    True
    >>> jsm_dup == m  # different number of members
    False

    Equivalent to

    >>> dict([(x, 0)]) == dict([(y, 0), (z, 0)])
    True
    """

    __dict: dict[JSSameValueZero, tuple[KT, VT]]

    # Types from _typeshed builtins.pyi for dict
    @overload
    def __init__(self, /) -> None: ...

    @overload
    def __init__(self: JSMap[str, VT], /, **kwargs: VT) -> None: ...  # pyright: ignore[reportInvalidTypeVarUse]  #11780

    @overload
    def __init__(self, map: SupportsKeysAndGetItem[KT, VT], /) -> None: ...

    @overload
    def __init__(
        self: JSMap[str, VT],  # pyright: ignore[reportInvalidTypeVarUse]  #11780
        map: SupportsKeysAndGetItem[str, VT],
        /,
        **kwargs: VT,
    ) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[tuple[KT, VT]], /) -> None: ...

    @overload
    def __init__(
        self: JSMap[str, VT],  # pyright: ignore[reportInvalidTypeVarUse]  #11780
        iterable: Iterable[tuple[str, VT]],
        /,
        **kwargs: VT,
    ) -> None: ...

    # Next two overloads are for dict(string.split(sep) for string in iterable)
    # Cannot be Iterable[Sequence[_T]] or otherwise dict(["foo", "bar", "baz"])
    # is not an error
    @overload
    def __init__(self: JSMap[str, str], iterable: Iterable[list[str]], /) -> None: ...

    @overload
    def __init__(
        self: JSMap[bytes, bytes], iterable: Iterable[list[bytes]], /
    ) -> None: ...

    def __init__(  # type: ignore[misc]  # mypy doesn't like all the overloads
        self,
        init: SupportsKeysAndGetItem[KT, VT] | Iterable[tuple[KT, VT]] | None = None,
        **kwargs: VT,
    ) -> None:
        self.__dict = {}
        if init is not None:
            self.update(init)
        if kwargs:
            self.update(cast(dict[KT, VT], kwargs))

    def __setitem__(self, key: KT, value: VT, /) -> None:
        self.__dict[same_value_zero(key)] = key, value

    def __delitem__(self, key: KT, /) -> None:
        del self.__dict[same_value_zero(key)]

    def __getitem__(self, key: KT, /) -> VT:
        return self.__dict[same_value_zero(key)][1]

    def __iter__(self) -> Iterator[KT]:
        return map(itemgetter(0), self.__dict.values())

    def __len__(self) -> int:
        return len(self.__dict)

    def __eq__(self, other: object) -> bool:
        # Not sure if this idea of equality is helpful or cursed... The idea is
        # to preserve JavaScript Map items verbatim (not omit equal items when
        # deserializing), but use a notion of equality familiar to Python users
        # for the overall JSMap objects.
        #
        # It seems logical that if two JSMaps contain equal items in the same
        # order, they can be considered equal, even if the items are different
        # instances. i.e. we can use a different concept of equality for key
        # uniqueness and overall equality. This seems to make more intuitive
        # sense from a Python user POV, as objects which look equal by repr()
        # are equal by ==.
        if self is other:
            return True
        if isinstance(other, JSMap):
            if len(self) != len(other):
                return False
            # Two JSMaps are equal if they contain equal items in the same order
            return all(
                x == y for x, y in zip(self.__dict.values(), other.__dict.values())
            )
        if isinstance(other, Mapping):
            if len(self) != len(other):
                return False
            # Other general mapping types are equal if they're equal to a dict
            # containing our entries (only if we have hashable entries)
            try:
                self_as_dict = dict(self.__dict.values())
            except Exception:
                # We contain an unhashable key. Fall back to comparing the other
                # items in order, in the same way as if it were a JSMap
                return all(x == y for x, y in zip(self.__dict.values(), other.items()))
            return self_as_dict == other
        return NotImplemented

    def __repr__(self) -> str:
        return _repr.js_repr(self)

    # Overrides for optimisation purposes. Clear is very worthwhile, the others
    # are marginal and barely worth it...
    def clear(self) -> None:
        self.__dict.clear()

    @overload
    def update(self, m: SupportsKeysAndGetItem[KT, VT], /, **kwargs: VT) -> None: ...

    @overload
    def update(self, m: Iterable[tuple[KT, VT]], /, **kwargs: VT) -> None: ...

    @overload
    def update(self, /, **kwargs: VT) -> None: ...

    def update(
        self,
        other: SupportsKeysAndGetItem[KT, VT] | Iterable[tuple[KT, VT]] = (),
        /,
        **kwds: VT,
    ) -> None:
        if isinstance(other, Mapping):
            self.__dict.update((same_value_zero(k), (k, v)) for k, v in other.items())
        elif _supports_keys_and_get_item(other):
            self.__dict.update(
                (same_value_zero(k), (k, other[k])) for k in other.keys()
            )
        else:
            other = cast(Iterable[tuple[KT, VT]], other)
            self.__dict.update((same_value_zero(k), (k, v)) for k, v in other)

        if kwds:
            self.__dict.update((same_value_zero(k), (k, v)) for k, v in kwds.items())  # type: ignore[misc]

    @overload
    def get(self, key: KT, /) -> VT | None: ...

    @overload
    def get(self, key: KT, /, default: VT | U) -> VT | U: ...

    def get(self, key: KT, /, default: U | None = None) -> VT | U | None:
        return self.__dict.get(same_value_zero(key), (None, default))[1]


def _supports_keys_and_get_item(
    x: SupportsKeysAndGetItem[KT, VT] | Iterable[tuple[KT, VT]],
) -> TypeGuard[SupportsKeysAndGetItem[KT, VT]]:
    return hasattr(x, "keys")
