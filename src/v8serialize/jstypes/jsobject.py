from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from itertools import chain
from typing import (  # TypeVar,
    TYPE_CHECKING,
    Iterable,
    Iterator,
    MutableMapping,
    TypeGuard,
    Union,
    cast,
    overload,
)

from v8serialize.jstypes._normalise_property_key import normalise_property_key
from v8serialize.jstypes.jsarrayproperties import (
    ArrayProperties,
    DenseArrayProperties,
    JSHole,
    JSHoleType,
    SparseArrayProperties,
)

if TYPE_CHECKING:
    # We use TypeVar's default param which isn't in stdlib yet.
    from typing_extensions import TypeVar

    from _typeshed import SupportsKeysAndGetItem

    KT = TypeVar("KT", bound=int | str, default=int | str)
    VT = TypeVar("VT", default=object)
    T = TypeVar("T")

    IntProperties = (
        ArrayProperties[VT]
        | Iterable[VT | JSHoleType]
        | SupportsKeysAndGetItem[int, VT]
    )
    NameProperties = SupportsKeysAndGetItem[str, VT] | Iterable[tuple[str, VT]]
    IntNamePropertiesPair = tuple[IntProperties[VT] | None, NameProperties[VT] | None]

    MixedProperties = SupportsKeysAndGetItem[KT, VT] | Iterable[tuple[KT, VT]]


# TODO: measure & adjust these
MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4


def is_array_properties(o: object) -> TypeGuard[ArrayProperties[T]]:
    if not all(callable(getattr(o, a, None)) for a in ["element_indexes", "elements"]):
        return False
    return hasattr(o, "elements_used") and getattr(o, "hole_value", None) is JSHole


def supports_keys_and_get_item(
    o: IntProperties[VT],
) -> TypeGuard[SupportsKeysAndGetItem[int, VT]]:
    return all(callable(getattr(o, a, None)) for a in ["keys", "__getitem__"])


def is_int_name_properties_pair(
    o: MixedProperties[KT, VT] | IntNamePropertiesPair[VT] | None,
) -> TypeGuard[IntNamePropertiesPair[VT]]:
    return isinstance(o, tuple) and len(o) == 2


@dataclass(slots=True, init=False)
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

    def __init__(
        self,  # TODO: detect instances of JSObject
        properties: MixedProperties[KT, VT] | IntNamePropertiesPair[VT] | None = None,
        /,
        **kwarg_properties: VT,
    ) -> None:
        if properties is None:
            self.array = DenseArrayProperties()
            self.properties = {}
        elif is_int_name_properties_pair(properties):
            int_props, name_props = properties

            # Allow callers to provide their own array implementation
            if int_props is None:
                self.array = DenseArrayProperties()
            elif is_array_properties(int_props):
                self.array = int_props
            elif supports_keys_and_get_item(int_props):
                self.array = SparseArrayProperties(entries=int_props)
            else:
                self.array = DenseArrayProperties(
                    cast(Iterable[VT | JSHoleType], int_props)
                )

            self.properties = {}

            if name_props is not None:
                # MyPy thinks name_prop's key type str cannot be passed to
                # update which takes str | int keys. 🤷
                self.update(
                    cast(
                        SupportsKeysAndGetItem[KT, VT] | Iterable[tuple[KT, VT]],
                        name_props,
                    )
                )
        else:
            self.array = DenseArrayProperties()
            self.properties = {}
            self.update(cast(MixedProperties[KT, VT], properties))

        if kwarg_properties:
            self.update(cast(dict[KT, VT], kwarg_properties))

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
