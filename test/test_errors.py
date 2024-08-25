from dataclasses import dataclass

from v8serialize.constants import SerializationTag
from v8serialize.errors import (
    NormalizedKeyError,
    UnmappedTagDecodeV8CodecError,
    V8CodecError,
)


@dataclass(init=False)
class ExampleV8CodecError(V8CodecError):
    level: int
    limit: float

    def __init__(self, message: str, *, level: int, limit: float) -> None:
        super().__init__(message)
        self.level = level
        self.limit = limit


def test_v8codecerror_str_with_fields() -> None:
    assert (
        str(ExampleV8CodecError("Level too high", level=3, limit=2.123))
        == "Level too high: level=3, limit=2.123"
    )


def test_v8codecerror_str_without_fields() -> None:
    assert str(V8CodecError("Something went wrong")) == "Something went wrong"


def test_NormalizedKeyError() -> None:
    nke = NormalizedKeyError(0, "0")

    assert nke.normalized_key == 0
    assert nke.raw_key == "0"
    assert repr(nke) == "NormalizedKeyError(normalized_key=0, raw_key='0')"
    # str being the repr of a str is kind of weird, but this is what all errors do
    assert str(nke) == repr("0 (normalized from '0')")


def test_UnmappedTagDecodeV8CodecError() -> None:
    err = UnmappedTagDecodeV8CodecError(
        "Msg", tag=SerializationTag.kArrayBuffer, position=2, data=b"foo"
    )

    assert (
        str(err)
        == "Msg: position=2, data=b'foo', tag=<SerializationTag.kArrayBuffer: 66>"
    )
