from __future__ import annotations

from abc import ABC
from typing import MutableMapping, TypeVar

KT = TypeVar("KT", bound=int | str)
T = TypeVar("T")


MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4
MAX_DENSE_ARRAY_HOLE_RATIO = 1 / 4


class JSObject(MutableMapping[KT, T], ABC):
    """A Python model of JavaScript plain objects, limited to the behaviour that
    can be transferred with V8 serialization (which is essentially the behaviour
    of [`structuredClone()`]).

    [`structuredClone()`]: https://developer.mozilla.org/en-US/docs/Web/API/structuredClone

    The behaviour implemented aims to match that describe by the [ECMA-262] spec.
    [ECMA-262]: https://tc39.es/ecma262/#sec-object-type

    JSObject is also an ABC can other types can register as virtual subtypes of
    in order to serialize themselves as JavaScript Objects.
    """

    # array_properties: ArrayProperties

    # TODO: should we provide a specialised map that acts like JavaScript
    #   objects? e.g. allows for number or string keys that are synonyms. Plus
    #   insertion ordering.
    pass
