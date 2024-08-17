from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from itertools import chain
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    overload,
)

from v8serialize.errors import NormalizedKeyError
from v8serialize.jstypes import _repr
from v8serialize.jstypes._normalise_property_key import normalise_property_key
from v8serialize.jstypes.jsarrayproperties import (
    ArrayProperties,
    DenseArrayProperties,
    JSHole,
    SparseArrayProperties,
)

if TYPE_CHECKING:
    # We use TypeVar's default param which isn't in stdlib yet.
    from typing_extensions import TypeVar

    from _typeshed import SupportsKeysAndGetItem

    T = TypeVar("T", default=object)  # TODO: does default help in practice?


# TODO: measure & adjust these
MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4


@dataclass(slots=True, init=False)
class JSObject(MutableMapping[str | int, "T"], ABC):
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

    array: ArrayProperties[T]
    """Properties with integer names."""
    properties: Mapping[str, T]
    """Properties with string names."""
    _properties: dict[str, T]
    """Properties with string names."""

    @overload
    def __init__(self, /, **kwargs: T) -> None: ...

    @overload
    def __init__(
        self, properties: SupportsKeysAndGetItem[str | int, T], /, **kwargs: T
    ) -> None: ...

    @overload
    def __init__(
        self, properties: Iterable[tuple[str | int, T]], /, **kwargs: T
    ) -> None: ...

    def __init__(
        self,
        properties: (
            SupportsKeysAndGetItem[str | int, T] | Iterable[tuple[str | int, T]]
        ) = (),
        /,
        **kwarg_properties: T,
    ) -> None:
        self.array = DenseArrayProperties()
        self._properties = {}
        # Read-only view of _properties. It's not safe provide direct access to
        # the dict in our API as we need to ensure array index properties go to
        # the array. Writing properties would bypass this.
        self.properties = MappingProxyType(self._properties)

        self.update(properties)
        if kwarg_properties:
            self.update(kwarg_properties)

    def __getitem__(self, key: str | int, /) -> T:
        k = normalise_property_key(key)
        if type(k) is str:
            properties = self._properties
            if k in properties:
                return properties[k]
            raise NormalizedKeyError(k, raw_key=key)
        else:
            assert isinstance(k, int)
            array_properties = self.array
            if 0 <= k < len(array_properties):
                value = array_properties[k]
                if value is not JSHole:
                    return value
            raise NormalizedKeyError(k, raw_key=key)

    def __setitem__(self, key: str | int | float, value: T, /) -> None:
        k = normalise_property_key(key)
        if type(k) is str:
            if value is JSHole:
                self._properties.pop(k, None)
            else:
                self._properties[k] = value
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

    def __delitem__(self, key: str | int, /) -> None:
        k = normalise_property_key(key)
        if type(k) is str:
            if k in self._properties:
                del self._properties[k]
                return
            raise NormalizedKeyError(k, raw_key=key)
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
            raise NormalizedKeyError(k, raw_key=key)

    def __len__(self) -> int:
        return self.array.elements_used + len(self._properties)

    def __iter__(self) -> Iterator[str | int]:
        return chain(self.array.element_indexes(), self._properties)

    def __repr__(self) -> str:
        return _repr.js_repr(self)

    if TYPE_CHECKING:
        # Our Mapping key type is str | int. MyPy doesn't allow calling methods
        # accepting XXX[str | int, T] with XXX[str, T]. (I think because key
        # type of MutableMapping is invariant). This is clearly fine in
        # practice, so we overload the update method to allow this.

        # Also, we specialise __setitem__ to accept float, as well as str | int
        # which other methods return. We also want to support this for update()
        # and setdefault(). They are implemented in MutableMapping in terms
        # of __setitem__(). So we just need to override the types to allow
        # passing float.

        @overload  # type: ignore[override]
        def update(self, m: SupportsKeysAndGetItem[str, T], /, **kwargs: T) -> None: ...

        @overload
        def update(self, m: SupportsKeysAndGetItem[int, T], /, **kwargs: T) -> None: ...

        @overload
        def update(
            self, m: SupportsKeysAndGetItem[float, T], /, **kwargs: T
        ) -> None: ...

        @overload
        def update(
            self, m: SupportsKeysAndGetItem[str | int, T], /, **kwargs: T
        ) -> None: ...

        @overload
        def update(
            self, m: SupportsKeysAndGetItem[str | int | float, T], /, **kwargs: T
        ) -> None: ...

        @overload
        def update(self, m: Iterable[tuple[str, T]], /, **kwargs: T) -> None: ...

        @overload
        def update(self, m: Iterable[tuple[int, T]], /, **kwargs: T) -> None: ...

        @overload
        def update(self, m: Iterable[tuple[float, T]], /, **kwargs: T) -> None: ...

        @overload
        def update(self, m: Iterable[tuple[str | int, T]], /, **kwargs: T) -> None: ...

        @overload
        def update(
            self, m: Iterable[tuple[str | int | float, T]], /, **kwargs: T
        ) -> None: ...

        @overload
        def update(self, **kwargs: T) -> None: ...

        def update(self, *args: Any, **kwargs: T) -> None: ...  # type: ignore[misc]

        @overload
        def setdefault(
            self, key: str | int | float, default: None = None, /
        ) -> T | None: ...

        @overload
        def setdefault(self, key: str | int | float, default: T, /) -> T: ...

        def setdefault(self, key: Any, default: Any = None, /) -> Any: ...
