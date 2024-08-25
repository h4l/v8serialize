from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, ByteString, cast

if TYPE_CHECKING:
    from v8serialize.constants import SerializationTag


@dataclass(init=False)
class V8CodecError(BaseException):  # FIXME: should inherit Exception
    if not TYPE_CHECKING:
        message: str  # needed to have dataclass include message in the repr, etc

    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)

    @property
    def message(self) -> str:
        return cast(str, self.args[0])

    def __str__(self) -> str:
        field_values = asdict(self)
        message = field_values.pop("message")
        values_fmt = ", ".join(f"{f}={v!r}" for (f, v) in field_values.items())

        return f"{message}{": " if values_fmt else ""}{values_fmt}"


# TODO: str/repr needs customising to abbreviate the data field
@dataclass(init=False)
class DecodeV8CodecError(V8CodecError, ValueError):
    position: int
    data: ByteString

    def __init__(
        self, message: str, *args: object, position: int, data: ByteString
    ) -> None:
        super().__init__(message, *args)
        self.position = position
        self.data = data


@dataclass(init=False)
class UnmappedTagDecodeV8CodecError(DecodeV8CodecError):
    """Raised when attempting to deserialize a tag that no TagMapper is able to
    handle (by reading the tag's data from the stream and representing the data
    as a Python object)."""

    if not TYPE_CHECKING:
        tag: SerializationTag

    def __init__(
        self,
        message: str,
        *args: object,
        tag: SerializationTag,
        position: int,
        data: ByteString,
    ) -> None:
        super().__init__(message, tag, *args, position=position, data=data)

    @property
    def tag(self) -> SerializationTag:
        return cast("SerializationTag", self.args[1])


@dataclass(slots=True, init=False)
class NormalizedKeyError(KeyError):
    """A key was not found, but the searched-for key was a normalized version of
    the provided key."""

    normalized_key: object
    raw_key: object

    def __init__(self, normalized_key: object, raw_key: object) -> None:
        self.normalized_key = normalized_key
        self.raw_key = raw_key
        super(NormalizedKeyError, self).__init__(
            f"{self.normalized_key!r} (normalized from {self.raw_key!r})"
        )


class JSRegExpV8CodecError(V8CodecError):
    pass
