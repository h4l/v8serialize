from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, cast

from v8serialize._pycompat.typing import ReadableBinary

if TYPE_CHECKING:
    from v8serialize.constants import SerializationFeature, SerializationTag


@dataclass(init=False)
class V8SerializeError(Exception):
    """The base class that all v8serialize errors are subclasses of."""

    if not TYPE_CHECKING:
        message: str  # needed to have dataclass include message in the repr, etc

    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)

    @property
    def message(self) -> str:
        return cast(str, self.args[0])

    def __str__(self) -> str:
        field_values = [
            (f.name, getattr(self, f.name)) for f in fields(self) if f.name != "message"
        ]
        values_fmt = ", ".join(f"{f}={v!r}" for (f, v) in field_values)

        if values_fmt:
            return f"{self.message}: {values_fmt}"
        return self.message


# TODO: str/repr needs customising to abbreviate the data field
@dataclass(init=False)
class DecodeV8SerializeError(V8SerializeError, ValueError):
    position: int
    data: ReadableBinary

    def __init__(
        self, message: str, *args: object, position: int, data: ReadableBinary
    ) -> None:
        super().__init__(message, *args)
        self.position = position
        self.data = data


@dataclass(init=False)
class UnhandledTagDecodeV8SerializeError(DecodeV8SerializeError):
    """
    No `TagReader` is able to handle a `SerializationTag`.

    Raised when attempting to deserialize a tag that no `TagReader` is able to
    handle (by reading the tag's data from the stream and representing the data
    as a Python object).
    """

    if not TYPE_CHECKING:
        tag: SerializationTag

    def __init__(
        self,
        message: str,
        *args: object,
        tag: SerializationTag,
        position: int,
        data: ReadableBinary,
    ) -> None:
        super().__init__(message, tag, *args, position=position, data=data)

    @property
    def tag(self) -> SerializationTag:
        return cast("SerializationTag", self.args[1])


@dataclass(init=False, slots=True)
class NormalizedKeyError(KeyError):
    """A JSObject does not contain a property for the requested key.

    JSObjects store and look up integer keys differently from non-integer keys,
    so the actual key used in the lookup may not be the same as the same as the
    original, raw key. The `normalized_key` and `raw_key` properties hold both
    versions of the key.
    """

    normalized_key: object
    raw_key: object

    def __init__(self, normalized_key: object, raw_key: object) -> None:
        self.normalized_key = normalized_key
        self.raw_key = raw_key
        super(NormalizedKeyError, self).__init__(
            f"{self.normalized_key!r} (normalized from {self.raw_key!r})"
        )


class JSRegExpV8SerializeError(V8SerializeError):
    pass


@dataclass(init=False)
class EncodeV8SerializeError(V8SerializeError, ValueError):
    pass


@dataclass(init=False)
class UnhandledValueEncodeV8SerializeError(EncodeV8SerializeError, ValueError):
    """
    No [encode step] is able to represent a Python value in the V8 Serialization format.

    Raised when attempting to serialize an object that the none of the
    configured encode steps know how to represent as V8 serialization tags.

    [encode step]: `v8serialize.encode.EncodeStep`
    """

    value: object

    def __init__(
        self,
        message: str,
        *args: object,
        value: object,
    ) -> None:
        super().__init__(message, value, *args)

    @property  # type: ignore[no-redef]
    def value(self) -> object:
        return self.args[1]


@dataclass(init=False)
class FeatureNotEnabledEncodeV8SerializeError(EncodeV8SerializeError):
    """
    The SerializationFeature required to write a value is not enabled.

    Raised when a WritableTagStream is commanded to write data that requires a
    `SerializationFeature` that is not enabled.
    """

    feature_required: SerializationFeature

    def __init__(self, message: str, *, feature_required: SerializationFeature) -> None:
        super(FeatureNotEnabledEncodeV8SerializeError, self).__init__(message)
        self.feature_required = feature_required
