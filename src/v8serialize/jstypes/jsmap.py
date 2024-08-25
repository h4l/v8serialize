from __future__ import annotations

from abc import ABCMeta
from collections.abc import MutableMapping
from dataclasses import dataclass
from operator import itemgetter
from typing import TYPE_CHECKING, Iterable, Iterator, Mapping, Never, cast, overload

from v8serialize.jstypes import _repr
from v8serialize.jstypes._equality import JSSameValueZero, same_value_zero

if TYPE_CHECKING:
    from typing_extensions import TypeVar

    from _typeshed import SupportsKeysAndGetItem

    KT = TypeVar("KT", default=object)
    VT = TypeVar("VT", default=object)
else:
    from typing import TypeVar

    KT = TypeVar("KT")
    VT = TypeVar("VT")


@dataclass(slots=True, init=False)
class JSMap(MutableMapping[KT, VT], metaclass=ABCMeta):
    """A Mapping that uses object identity for key equality.

    This replicates the behaviour of JavaScript's Map type, which considers keys
    equal by the [same-value-zero] rules (very close to `Object.is()` / `===`).

    [same-value-zero]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/\
Equality_comparisons_and_sameness#same-value-zero_equality

    `JSMap` is able to use non-hashable objects as keys, but has the behaviour
    that maps containing distinct instances of seemingly equal values are not
    equal:

    >>> a, b = tuple([0]), tuple([0])
    >>> assert a == b
    >>> assert a is not b
    >>> JSMap({ a: 0 }) == JSMap({ b: 0 })
    False
    >>> dict({ a: 0 }) == dict({ b: 0 })
    True
    """

    __dict: dict[JSSameValueZero, tuple[KT, VT]]

    # Types from _typeshed builtins.pyi for dict
    @overload
    def __init__(self, /) -> None: ...

    @overload
    def __init__(
        self: JSMap[str, VT], /, **kwargs: VT
    ) -> None: ...  # pyright: ignore[reportInvalidTypeVarUse]  #11780

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
        if self is other:
            return True
        if isinstance(other, JSMap):
            return self.__dict == other.__dict
        if isinstance(other, Mapping):
            return self.__dict == JSMap(other.items()).__dict
        return False

    def __hash__(self) -> Never:
        raise TypeError("unhashable type: 'JSMap'")

    def __repr__(self) -> str:
        return _repr.js_repr(self)
