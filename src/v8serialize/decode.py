from __future__ import annotations

from dataclasses import dataclass, field
from typing import ByteString, Never, cast

from v8serialize.constants import SerializationTag, kLatestVersion


class V8CodecError(ValueError):
    pass


@dataclass(init=False)
class DecodeV8CodecError(V8CodecError):
    message: str
    position: int
    data: ByteString

    def __init__(
        self, message: str, *args: object, position: int, data: ByteString
    ) -> None:
        super().__init__(message, *args)
        self.position = position
        self.data = data

    @property  # type: ignore[no-redef]
    def message(self) -> str:
        return cast(str, self.args[0])


def _decode_zigzag(n: int) -> int:
    """Convert ZigZag encoded unsigned int to signed.

    ZigZag encoding maps signed ints to unsigned: -2 = 3, -1 = 1, 0 = 0, 1 = 2.
    """
    if n % 2:
        return -((n + 1) // 2)
    return n // 2


@dataclass(slots=True)
class ReadableTagStream:
    data: ByteString
    pos: int = field(default=0)

    def ensure_capacity(self, count: int) -> None:
        if self.pos + count > len(self.data):
            available = max(0, len(self.data) - self.pos)
            self.throw(
                f"Data truncated: Expected {count} bytes at position {self.pos} but "
                f"{available} available"
            )

    def throw(self, message: str) -> Never:
        raise DecodeV8CodecError(message, data=self.data, position=self.pos)

    def read_tag(self, tag: SerializationTag | None = None) -> SerializationTag:
        self.ensure_capacity(1)
        value = self.data[self.pos]
        if value in SerializationTag:
            if tag is None:
                self.pos += 1
                return SerializationTag(value)
            else:
                if value == tag:
                    self.pos += 1
                    return tag

            expected = f"Expected tag {tag}"
            actual = f"{self.data[self.pos]} ({SerializationTag(self.data[self.pos])}"
        else:
            expected = "Expected a tag"
            actual = f"{self.data[self.pos]} (not a valid tag)"

        self.throw(f"{expected} at position {self.pos} but found {actual}")

    def read_uint8(self) -> int:
        self.ensure_capacity(1)
        value = self.data[self.pos]
        self.pos += 1
        return value

    def read_varint(self) -> int:
        data = self.data
        pos = self.pos
        varint = 0
        offset = 0
        for pos in range(pos, len(self.data)):  # noqa: B020
            encoded = data[pos]
            uint7 = encoded & 0b1111111
            varint += uint7 << offset
            # The most-significant bit is set except on the final byte
            if encoded == uint7:
                self.pos = pos + 1
                return varint
            offset += 7
        count = pos - self.pos
        self.pos = pos
        self.throw(
            f"Data truncated: end of stream while reading varint after reading "
            f"{count} bytes"
        )

    def read_zigzag(self) -> int:
        uint = self.read_varint()
        return _decode_zigzag(uint)


def loads(data: ByteString) -> None:
    """De-serialize JavaScript values encoded in V8 serialization format."""
    rts = ReadableTagStream(data)

    rts.read_tag(SerializationTag.kVersion)
    version = rts.read_uint8()
    if version > kLatestVersion:
        rts.throw(f"Unsupported version {version}")
