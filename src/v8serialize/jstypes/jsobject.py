from __future__ import annotations

from abc import ABC
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass
from itertools import chain
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, overload

from v8serialize._errors import NormalizedKeyError
from v8serialize._recursive_eq import recursive_eq
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
    from _typeshed import SupportsKeysAndGetItem
    from typing_extensions import TypeVar

    T = TypeVar("T", default=object)  # TODO: does default help in practice?


# TODO: measure & adjust these
MIN_SPARSE_ARRAY_SIZE = 16
MIN_DENSE_ARRAY_USED_RATIO = 1 / 4


@recursive_eq
@dataclass(init=False, slots=True, eq=False)
class JSObject(MutableMapping["str | int", "T"], ABC):
    """
    A Python equivalent of [JavaScript plain objects][JavaScript Object].

    `JSObject` is a [Python Mapping], whose keys can be strings or numbers.
    JavaScript Objects treat integer keys and integer strings as equivalent, and
    `JSObject` does too. In fact, [JavaScript Arrays][JavaScript Array] and
    Objects are almost entirely the same, and [`JSArray`] is also the same as
    `JSObject`, except for its constructor arguments. The [`JSArray`]
    description provides details of integer indexing behaviour which also
    applies to `JSObject`.

    `JSObject` implements just the JavaScript Object behaviour that can be
    transferred with V8 serialization (which is essentially the behaviour of
    [`structuredClone()`]). This is similar to JSON objects — object prototypes,
    methods, get/set properties and symbol properties cannot be transferred.
    Unlike JSON, objects can contain cycles and all the other JavaScript types
    supported by the V8 Serialization format, such as JavaScript's `RegExp` and
    `Date` ([`JSRegExp`] and [](`datetime.datetime`)).

    JSObject is also an ABC can other types can register as virtual subtypes of
    in order to serialize themselves as JavaScript Objects (by default, Python
    Mappings are serialized as JavaScript Maps).

    Parameters
    ----------
    properties
        The items to populate the object with, either as a mapping to copy, or
        an iterable of `(key, value)` pairs.
    kwarg_properties
        Additional key-values to populate the object with. These override any
        items from `properties` with the same key.

    Notes
    -----
    The behaviour `JSObject` implements aims to match that described by the
    [ECMA-262] spec, so that details are not lost in translation when
    serializing between Python and JavaScript.

    [`structuredClone()`]: \
https://developer.mozilla.org/en-US/docs/Web/API/structuredClone
    [ECMA-262]: https://tc39.es/ecma262/#sec-object-type
    [Python Mapping]: https://docs.python.org/3/glossary.html#term-mapping
    [JavaScript Object]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/Object
    [JavaScript Array]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/Array
    [`JSArray`]: `v8serialize.jstypes.JSArray`
    [`JSRegExp`]: `v8serialize.jstypes.JSRegExp`

    Examples
    --------
    >>> o = JSObject(name='Bob', likes_hats=False)
    >>> o['name']
    'Bob'
    >>> o['518'] = 'Teapot'
    >>> o['404'] = 'Not Found'

    Properties are kept in order of creation, but array indexes (e.g. strings
    that are non-negative integers) always come first, in numeric order.

    >>> o
    JSObject({404: 'Not Found', 518: 'Teapot'}, name='Bob', likes_hats=False)
    >>> dict(o)
    {404: 'Not Found', 518: 'Teapot', 'name': 'Bob', 'likes_hats': False}
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

    def __eq__(self, other: object) -> bool:
        # The equality semantics for JSObject and JSArray is that JSObject is
        # only equal to other JSObject (not to other JSArray or other Mapping).
        # JSArray is only equal to other JSArray, not to JSObject or other
        # Mappings or Sequences.
        #
        # My reasoning is that both Object and Array are somewhere between
        # Sequence and Mapping, and although both behave almost identically,
        # they have different conceptual purposes, so it doesn't make sense for
        # an Object to equal an Array. To some extent it could make sense for an
        # Object to equal other Mappings, and for Array to equal other
        # Sequences, but allowing this opens up a bit of a can of worms in that
        # Map and Object are clearly different in JavaScript, and a Sequence is
        # not really a substitute for a JSArray, as a JSArray itself does not
        # implement Sequence.
        if other is self:
            return True
        if not isinstance(other, JSObject):
            return NotImplemented
        # JSArray instances are not equal to JSObject instances
        if type(self) is not type(other):
            # Opt out of choosing rather than False so that subclasses could do
            # their own check if they want.
            return NotImplemented
        if len(self) != len(other):
            return False
        return (self.array, self._properties) == (other.array, other._properties)

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
