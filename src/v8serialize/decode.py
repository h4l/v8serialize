from __future__ import annotations

import codecs
import operator
import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ByteString, Iterable, Mapping, Never, Protocol, cast

from v8serialize.constants import SerializationTag, kLatestVersion
from v8serialize.decorators import tag
from v8serialize.errors import V8CodecError

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem, SupportsRead


@dataclass(init=False)
class DecodeV8CodecError(V8CodecError, ValueError):
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

    def throw(self, message: str, *, cause: BaseException | None = None) -> Never:
        raise DecodeV8CodecError(message, data=self.data, position=self.pos) from cause

    def read_tag(self, tag: SerializationTag | None = None) -> SerializationTag:
        self.ensure_capacity(1)
        value = self.data[self.pos]
        # Some tags (e.g. TwoByteString) are preceded by padding for alignment
        if value == SerializationTag.kPadding:
            self.pos += 1
            self.read_padding()
            value = self.data[self.pos]
        if value in SerializationTag:
            if tag is None:
                self.pos += 1
                return SerializationTag(value)
            else:
                if value == tag:
                    self.pos += 1
                    return tag

            expected = f"Expected tag {tag.name}"
            actual = (
                f"{self.data[self.pos]} ({SerializationTag(self.data[self.pos]).name})"
            )
        else:
            expected = "Expected a tag"
            actual = f"{self.data[self.pos]} (not a valid tag)"

        self.throw(f"{expected} at position {self.pos} but found {actual}")

    def read_padding(self) -> None:
        while True:
            self.ensure_capacity(1)
            if self.data[self.pos] != SerializationTag.kPadding:
                return
            self.pos += 1

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

    def read_header(self) -> int:
        """Read the V8 serialization stream header and verify it's a supported version.

        @return the header's version number.
        """
        self.read_tag(SerializationTag.kVersion)
        version = self.read_varint()
        if version > kLatestVersion:
            self.throw(f"Unsupported version {version}")
        return version

    @tag(SerializationTag.kDouble)
    def read_double(self) -> float:
        self.ensure_capacity(8)
        value = cast(float, struct.unpack_from("<d", self.data, self.pos)[0])
        self.pos += 8
        return value

    def read_string_onebyte(self) -> str:
        """Decode a OneByteString, which is latin1-encoded text."""
        self.read_tag(tag=SerializationTag.kOneByteString)
        length = self.read_varint()
        self.ensure_capacity(length)
        # Decoding latin1 can't fail/throw — just 1 byte/char.
        # We use codecs.decode because not all ByteString types have a decode method.
        value = codecs.decode(self.data[self.pos : self.pos + length], "latin1")
        self.pos += length
        return value

    def read_string_twobyte(self) -> str:
        """Decode a TwoByteString, which is UTF-16-encoded text."""
        self.read_tag(SerializationTag.kTwoByteString)
        length = self.read_varint()
        self.ensure_capacity(length)
        try:
            value = codecs.decode(self.data[self.pos : self.pos + length], "utf-16-le")
        except UnicodeDecodeError as e:
            self.throw("TwoByteString is not valid UTF-16 data", cause=e)
        self.pos += length
        return value

    def read_string_utf8(self) -> str:
        """Decode a Utf8String, which is UTF8-encoded text."""
        self.read_tag(tag=SerializationTag.kUtf8String)
        length = self.read_varint()
        self.ensure_capacity(length)
        try:
            value = codecs.decode(self.data[self.pos : self.pos + length], "utf-8")
        except UnicodeDecodeError as e:
            self.throw("Utf8String is not valid UTF-8 data", cause=e)
        self.pos += length
        return value

    def read_bigint(self) -> int:
        bitfield = self.read_varint()
        is_negative = bitfield & 1
        byte_count = (bitfield >> 1) & 0b111111111111111111111111111111
        self.ensure_capacity(byte_count)
        value = int.from_bytes(
            self.data[self.pos : self.pos + byte_count], byteorder="little"
        )
        if is_negative:
            return -value
        return value

    def read_object(self, tag_mapper: TagMapper) -> object:
        tag = self.read_tag()
        return tag_mapper.deserialize(tag, self)


class TagReader(Protocol):
    def __call__(
        self,
        tag_mapper: TagMapper,
        tag: SerializationTag,
        stream: ReadableTagStream,
        /,
    ) -> object: ...


class ReadableTagStreamReadFunction(Protocol):
    def __call__(self, cls: ReadableTagStream, /) -> object: ...

    @property
    def __name__(self) -> str: ...


def read_stream(rts_fn: ReadableTagStreamReadFunction) -> TagReader:
    """Create a TagReader that calls a primitive read_xxx function on the stream."""

    read_fn = operator.methodcaller(rts_fn.__name__)

    def tag_reader(
        tag_mapper: TagMapper, tag: SerializationTag, stream: ReadableTagStream
    ) -> object:
        return read_fn(stream)

    return tag_reader


@dataclass(slots=True, init=False)
class TagMapper:
    """Defines the conversion of V8 serialization tagged data to Python values."""

    tag_readers: Mapping[SerializationTag, TagReader]
    default_tag_mapper: TagMapper | None

    def __init__(
        self,
        tag_readers: (
            SupportsKeysAndGetItem[SerializationTag, TagReader]
            | Iterable[tuple[SerializationTag, TagReader]]
            | None
        ) = None,
        default_tag_mapper: TagMapper | None = None,
    ) -> None:
        self.default_tag_mapper = default_tag_mapper

        if tag_readers is not None:
            tag_readers = dict(tag_readers)

        self.tag_readers = self.register_tag_readers(tag_readers)
        assert self.tag_readers

    def register_tag_readers(
        self, tag_readers: dict[SerializationTag, TagReader] | None
    ) -> dict[SerializationTag, TagReader]:

        primitives: list[tuple[SerializationTag, ReadableTagStreamReadFunction]] = [
            (SerializationTag.kDouble, ReadableTagStream.read_double),
            (SerializationTag.kOneByteString, ReadableTagStream.read_string_onebyte),
            (SerializationTag.kTwoByteString, ReadableTagStream.read_string_twobyte),
            (SerializationTag.kUtf8String, ReadableTagStream.read_string_utf8),
            (SerializationTag.kBigInt, ReadableTagStream.read_bigint),
        ]
        primitive_tag_readers = {t: read_stream(read_fn) for (t, read_fn) in primitives}

        return {**primitive_tag_readers, **(tag_readers or {})}

    def deserialize(self, tag: SerializationTag, stream: ReadableTagStream) -> object:
        read_tag = self.tag_readers.get(tag)
        if not read_tag:
            # FIXME: more specific error
            stream.throw(f"No reader is implemented for tag {tag.name}")
        return read_tag(self, tag, stream)


@dataclass(init=False)
class Decoder:
    tag_mapper: TagMapper

    def __init__(self, tag_mapper: TagMapper | None) -> None:
        self.tag_mapper = tag_mapper or TagMapper()

    def decode(self, fp: SupportsRead[bytes]) -> object:
        return self.decodes(fp.read())

    def decodes(self, data: ByteString) -> object:
        stream = ReadableTagStream(data)
        stream.read_header()
        return stream.read_object(self.tag_mapper)


def loads(data: ByteString, *, tag_mapper: TagMapper | None = None) -> object:
    """Deserialize a JavaScript value encoded in V8 serialization format."""
    return Decoder(tag_mapper=tag_mapper).decodes(data)
