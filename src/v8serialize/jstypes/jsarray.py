from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing_extensions import TypeGuard, overload

from v8serialize._pycompat.dataclasses import slots_if310
from v8serialize.jstypes import _repr
from v8serialize.jstypes.jsarrayproperties import JSHoleType
from v8serialize.jstypes.jsobject import JSObject

if TYPE_CHECKING:
    # We use TypeVar's default param which isn't in stdlib yet.
    from typing_extensions import TypeVar

    from _typeshed import SupportsKeysAndGetItem

    T = TypeVar("T", default=object)  # TODO: does default help in practice?


def _supports_keys_and_get_item(
    o: SupportsKeysAndGetItem[str | int, T] | Iterable[T | JSHoleType],
) -> TypeGuard[SupportsKeysAndGetItem[str | int, T]]:
    return all(callable(getattr(o, a, None)) for a in ["keys", "__getitem__"])


def _supports_iterable(
    o: SupportsKeysAndGetItem[str | int, T] | Iterable[T | JSHoleType],
) -> TypeGuard[Iterable[T | JSHoleType]]:
    return callable(getattr(o, "__iter__", None))


@dataclass(init=False, **slots_if310())
class JSArray(JSObject["T"]):
    """A JavaScript Array.

    The constructor accepts lists/iterables of values, like `list()` does.
    Otherwise it is functionally the same as JSObject.

    JavaScript Array values deserialized from V8 data are represented as
    JSArray rather than JSObject, which allows them to round-trip back as Array
    on the JavaScript side.

    Note in particular that JSArray itself is not a Python Sequence, because
    JavaScript Arrays can also have string property values. The `.array` property
    contains a Sequence of the integer-indexed values, which in typical cases
    will hold all the values as a Sequence. The `.properties` Mapping holds just
    the non-array string properties.
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
