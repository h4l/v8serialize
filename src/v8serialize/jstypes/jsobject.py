from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Iterator, MutableMapping, TypeVar

from v8serialize.jstypes.jsarrayproperties import ArrayProperties

KT = TypeVar("KT", bound=int | str)
VT = TypeVar("VT")


MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4
MAX_DENSE_ARRAY_HOLE_RATIO = 1 / 4


@dataclass(slots=True)
class JSObject(MutableMapping[KT, VT], ABC):
    """A Python model of JavaScript plain objects, limited to the behaviour that
    can be transferred with V8 serialization (which is essentially the behaviour
    of [`structuredClone()`]).

    [`structuredClone()`]: https://developer.mozilla.org/en-US/docs/Web/API/structuredClone

    The behaviour implemented aims to match that describe by the [ECMA-262] spec.
    [ECMA-262]: https://tc39.es/ecma262/#sec-object-type

    JSObject is also an ABC can other types can register as virtual subtypes of
    in order to serialize themselves as JavaScript Objects.
    """

    array_properties: ArrayProperties[VT]
    name_properties: dict[str, VT]

    def __init__(self) -> None:
        pass

    # __getitem__, __setitem__, __delitem__, __iter__, __len__

    def __getitem__(self, key: KT, /) -> VT:
        raise NotImplementedError

    def __setitem__(self, key: KT, value: VT, /) -> None:
        raise NotImplementedError

    def __delitem__(self, key: KT, /) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __iter__(self) -> Iterator[KT]:
        raise NotImplementedError

    # TODO: should we provide a specialised map that acts like JavaScript
    #   objects? e.g. allows for number or string keys that are synonyms. Plus
    #   insertion ordering.
    pass
