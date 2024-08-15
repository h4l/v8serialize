from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from itertools import chain
from typing import Iterator, MutableMapping, TypeVar

from v8serialize.jstypes._normalise_property_key import normalise_property_key
from v8serialize.jstypes.jsarrayproperties import (
    ArrayProperties,
    DenseArrayProperties,
    JSHole,
    SparseArrayProperties,
)

KT = TypeVar("KT", bound=int | str)
VT = TypeVar("VT")


# TODO: measure & adjust these
MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4


@dataclass(slots=True)
class JSObject(MutableMapping[KT, VT], ABC):
    """A Python model of JavaScript plain objects, limited to the behaviour that
    can be transferred with V8 serialization (which is essentially the behaviour
    of [`structuredClone()`]).

    [`structuredClone()`]: \
https://developer.mozilla.org/en-US/docs/Web/API/structuredClone

    The behaviour implemented aims to match that describe by the [ECMA-262] spec.
    [ECMA-262]: https://tc39.es/ecma262/#sec-object-type

    JSObject is also an ABC can other types can register as virtual subtypes of
    in order to serialize themselves as JavaScript Objects.
    """

    array: ArrayProperties[VT]
    """Properties with integer names."""
    properties: dict[str, VT]
    """Properties with string names."""

    def __init__(self) -> None:
        self.array = DenseArrayProperties()
        self.properties = {}

    def __getitem__(self, key: KT, /) -> VT:
        k = normalise_property_key(key)
        if type(k) is str:
            properties = self.properties
            if k in properties:
                return properties[k]
            raise KeyError(key)  # preserve the non-normalised key
        else:
            assert isinstance(k, int)
            array_properties = self.array
            if 0 <= k < len(array_properties):
                value = array_properties[k]
                if JSHole.isnot(value):
                    return value
            raise KeyError(key)  # preserve the non-normalised key

    def __setitem__(self, key: KT, value: VT, /) -> None:
        k = normalise_property_key(key)
        if type(k) is str:
            self.properties[k] = value
        else:
            assert isinstance(k, int)
            self._ensure_array_capacity(k)
            self.array[k] = value

    def _ensure_array_capacity(self, index: int) -> None:
        array = self.array
        length = len(array)
        if index < length:
            return
        new_length = index + 1

        # Swap the array properties implementation from dense to sparse to avoid
        # wasting space for long but mostly empty arrays.
        if new_length >= MIN_SPARSE_ARRAY_SIZE and isinstance(
            array, DenseArrayProperties
        ):
            new_used_ratio = (array.elements_used + 1) / new_length
            if new_used_ratio < MIN_DENSE_ARRAY_USED_RATIO:
                # Switch to sparse array to avoid wasting space representing holes
                self.array = SparseArrayProperties(
                    entries=array.elements().items(), length=new_length
                )
                return
        array.resize(new_length)

    def __delitem__(self, key: KT, /) -> None:
        k = normalise_property_key(key)
        if type(k) is str:
            if k in self.properties:
                del self.properties[k]
                return
            raise KeyError(key)  # preserve the non-normalised key
        else:
            assert isinstance(k, int)
            array = self.array
            # We model a dict and del behaviour for dict is quite different to
            # list. We throw KeyError if the key is not set to a value in the
            # array. We remove the key by assigning JSHole (del on the array
            # shifts everything back by 1).
            if k < len(array):
                if self.array[k] is not JSHole:
                    self.array[k] = JSHole
                    return
            raise KeyError(key)  # preserve the non-normalised key

    def __len__(self) -> int:
        return self.array.elements_used + len(self.properties)

    def __iter__(self) -> Iterator[KT]:
        it: Iterator[int | str] = chain(self.array.element_indexes(), self.properties)
        return it  # type: ignore[return-value]
