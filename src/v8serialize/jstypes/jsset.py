from abc import ABCMeta
from dataclasses import dataclass
from typing import TYPE_CHECKING, AbstractSet, Iterable, Iterator, MutableSet, overload

from v8serialize.jstypes import _repr
from v8serialize.jstypes._equality import JSSameValueZero, same_value_zero

if TYPE_CHECKING:
    from typing_extensions import TypeVar

    T = TypeVar("T", default=object)
else:
    from typing import TypeVar

    T = TypeVar("T")


@dataclass(slots=True)
class JSSet(MutableSet[T], metaclass=ABCMeta):
    """A Set that uses object identity for member equality

    This replicates the behaviour of JavaScript's Set type, which considers
    members equal by `Object.is()` / `===`, not by value.
    """

    __members: dict[JSSameValueZero, T]

    @overload
    def __init__(self, /) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[T], /) -> None: ...

    def __init__(self, iterable: Iterable[T] | None = None, /) -> None:
        if iterable is None:
            self.__members = {}
        else:
            self.__members = dict((same_value_zero(x), x) for x in iterable)

    def add(self, value: T) -> None:
        self.__members[same_value_zero(value)] = value

    def discard(self, value: T) -> None:
        key = same_value_zero(value)
        if key in self.__members:
            del self.__members[key]

    def __contains__(self, value: object, /) -> bool:
        return same_value_zero(value) in self.__members

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if isinstance(other, JSSet):
            return self.__members == other.__members
        if isinstance(other, AbstractSet):
            return self.__members == JSSet(other).__members
        return False

    def __iter__(self) -> Iterator[T]:
        return iter(self.__members.values())

    def __len__(self) -> int:
        return len(self.__members)

    def __repr__(self) -> str:
        return _repr.js_repr(self)
