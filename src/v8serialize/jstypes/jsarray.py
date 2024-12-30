from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, overload

from v8serialize.jstypes import _repr
from v8serialize.jstypes.jsarrayproperties import JSHoleType
from v8serialize.jstypes.jsobject import JSObject

if TYPE_CHECKING:
    # We use TypeVar's default param which isn't in stdlib yet.
    from _typeshed import SupportsKeysAndGetItem
    from typing_extensions import TypeGuard, TypeVar

    T = TypeVar("T", default=object)  # TODO: does default help in practice?


def _supports_keys_and_get_item(
    o: SupportsKeysAndGetItem[str | int, T] | Iterable[T | JSHoleType],
) -> TypeGuard[SupportsKeysAndGetItem[str | int, T]]:
    return all(callable(getattr(o, a, None)) for a in ["keys", "__getitem__"])


def _supports_iterable(
    o: SupportsKeysAndGetItem[str | int, T] | Iterable[T | JSHoleType],
) -> TypeGuard[Iterable[T | JSHoleType]]:
    return callable(getattr(o, "__iter__", None))


class JSArray(JSObject["T"]):
    """
    A Python equivalent of a [JavaScript Array].

    The constructor accepts lists/iterables of values, like `list()` does.
    Otherwise its functionally the same as [](`v8serialize.jstypes.JSObject`).

    JavaScript Array values deserialized from V8 data are represented as
    `JSArray` rather than `JSObject`, which allows them to round-trip back as
    Array on the JavaScript side.

    Note in particular that `JSArray` itself is not a [Python Sequence], because
    JavaScript Arrays can also have string property values. The `.array`
    property contains a sequence of the integer-indexed values, which — in the
    typical case where a `JSArray` has no string properties — will hold all the
    object's values. The `.properties` Mapping holds just the non-array string
    properties.

    JavaScript arrays have the special property of supporting sparse indexes —
    they can store values with large gaps between integer indexes without using
    space for unused indexes in between. `JSArray` (and thus `JSObject`) also
    have this behaviour. The `.array` property is [`SparseMutableSequence`],
    which extends the regular Sequence API with has extra methods and properties
    to support sparse arrays. (See the [examples](#examples) below.)

    [JavaScript Array]: https://developer.mozilla.org/en-US/docs/Web/\
JavaScript/Reference/Global_Objects/Array
    [Python Sequence]: https://docs.python.org/3/glossary.html#term-sequence
    [`SparseMutableSequence`]: `v8serialize.SparseMutableSequence`

    Parameters
    ----------
    properties
        Ordered values to populate the array with, or a mapping of key-values
        to initialise either or both int array indexes and string properties.
    kwarg_properties
        Additional key-values to populate either or both int array indexes and
        string properties. These override any items from `properties` with the
        same key.

    Examples
    --------
    >>> a = JSArray(['a', 'b'])
    >>> a
    JSArray(['a', 'b'])
    >>> a[0]
    'a'

    As in JavaScript, JSArray works exactly like a JSObject — arrays can also
    have non-integer properties:

    >>> a['foo'] = 'bar'
    >>> a
    JSArray(['a', 'b'], foo='bar')

    JavaScript Object and Array treat string properties that are integers the
    same as using integers directly. JSMap does the same:

    >>> a['2'] = 'c'
    >>> a
    JSArray(['a', 'b', 'c'], foo='bar')

    The `.array` property is a MutableSequence that contains only the
    integer-indexed array properties, whereas JSArray objects themselves are
    MutableMappings of all values:

    >>> from typing import MutableSequence, MutableMapping
    >>> isinstance(a.array, MutableSequence)
    True
    >>> list(a.array)
    ['a', 'b', 'c']
    >>> isinstance(a, MutableSequence)
    False
    >>> isinstance(a, MutableMapping)
    True
    >>> dict(a)
    {0: 'a', 1: 'b', 2: 'c', 'foo': 'bar'}

    JavaScript Arrays are _sparse_ — they can have large gaps between array
    entries without using space for all the empty indexes in between.
    `JSArray`'s `.array` property is a
    [special type of sequence][`SparseMutableSequence`] that models this
    behaviour:

    >>> from v8serialize import SparseMutableSequence
    >>> isinstance(a.array, SparseMutableSequence)
    True
    >>> a[6] = 'g'
    >>> a
    JSArray(['a', 'b', 'c', JSHole, JSHole, JSHole, 'g'], foo='bar')
    >>> len(a.array)
    7
    >>> a.array.elements_used
    4
    >>> list(a.array.element_indexes())
    [0, 1, 2, 6]

    `elements()` is a view of the array as a Mapping, containing keys for
    indexes that have values.

    >>> a.array.elements().get(6)
    'g'
    >>> a.array.elements().get(4, 'default')
    'default'
    >>> dict(a.array.elements())
    {0: 'a', 1: 'b', 2: 'c', 6: 'g'}

    To be consistent with normal sequences, `.array` raises `IndexError` for
    out-of-bounds index operations:

    >>> a.array[1234567] = '?'  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    IndexError: list index out of range

    The main `JSArray` object allows setting any index though.

    >>> a[1234567] = '?'
    >>> a
    JSArray({0: 'a', 1: 'b', 2: 'c', 6: 'g', 1234567: '?'}, foo='bar')
    """

    @overload
    def __init__(self, /, **kwargs: T) -> None: ...

    @overload
    def __init__(
        self, properties: SupportsKeysAndGetItem[str | int, T], /, **kwargs: T
    ) -> None: ...

    @overload
    def __init__(
        self,
        properties: Iterable[T | JSHoleType],
        /,
        **kwargs: T,
    ) -> None: ...

    def __init__(
        self,
        properties: (
            SupportsKeysAndGetItem[str | int, T] | Iterable[T | JSHoleType]
        ) = (),
        /,
        **kwarg_properties: T,
    ) -> None:
        super(JSArray, self).__init__()

        if _supports_keys_and_get_item(properties):
            self.update(properties)
        else:
            assert _supports_iterable(properties)
            self.array.extend(properties)
        self.update(kwarg_properties)

    def __repr__(self) -> str:
        return _repr.js_repr(self)
