from __future__ import annotations

import codecs
import operator
import struct
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    ByteString,
    Callable,
    Generator,
    Iterable,
    Mapping,
    MutableMapping,
    MutableSet,
    Never,
    Protocol,
    cast,
)

from v8serialize.constants import INT32_RANGE, SerializationTag, kLatestVersion
from v8serialize.errors import V8CodecError
from v8serialize.references import SerializedId, SerializedObjectLog

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem, SupportsRead


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
    objects: SerializedObjectLog = field(default_factory=SerializedObjectLog)

    @property
    def eof(self) -> bool:
        return self.pos == len(self.data)

    def ensure_capacity(self, count: int) -> None:
        if self.pos + count > len(self.data):
            available = max(0, len(self.data) - self.pos)
            self.throw(
                f"Data truncated: Expected {count} bytes at position {self.pos} but "
                f"{available} available"
            )

    def throw(self, message: str, *, cause: BaseException | None = None) -> Never:
        raise DecodeV8CodecError(message, data=self.data, position=self.pos) from cause

    def read_tag(
        self, tag: SerializationTag | None = None, consume: bool = True
    ) -> SerializationTag:
        """Read the tag at the current position.

        Padding tags are read and ignored until a non-padding tag is found. If
        `consume` is False, the current `self.pos` remains on the tag after
        returning rather than moving to the next byte. (Padding is always
        consumed regardless.)
        """
        self.ensure_capacity(1)
        value = self.data[self.pos]
        # Some tags (e.g. TwoByteString) are preceded by padding for alignment
        if value == SerializationTag.kPadding:
            self.pos += 1
            self.read_padding()
            value = self.data[self.pos]
        if value in SerializationTag:
            if tag is None:
                self.pos += consume
                return SerializationTag(value)
            else:
                if value == tag:
                    self.pos += consume
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

    def read_bytes(self, count: int) -> ByteString:
        self.ensure_capacity(count)
        self.pos += count
        return self.data[self.pos - count : self.pos]

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

    def read_double(self) -> float:
        self.read_tag(tag=SerializationTag.kDouble)
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
        value = codecs.decode(self.read_bytes(length), "latin1")
        return value

    def read_string_twobyte(self) -> str:
        """Decode a TwoByteString, which is UTF-16-encoded text."""
        self.read_tag(SerializationTag.kTwoByteString)
        length = self.read_varint()
        try:
            value = codecs.decode(self.read_bytes(length), "utf-16-le")
        except UnicodeDecodeError as e:
            self.pos -= length
            self.throw("TwoByteString is not valid UTF-16 data", cause=e)
        return value

    def read_string_utf8(self) -> str:
        """Decode a Utf8String, which is UTF8-encoded text."""
        self.read_tag(tag=SerializationTag.kUtf8String)
        length = self.read_varint()
        try:
            value = codecs.decode(self.read_bytes(length), "utf-8")
        except UnicodeDecodeError as e:
            self.pos -= length
            self.throw("Utf8String is not valid UTF-8 data", cause=e)
        return value

    def read_bigint(self) -> int:
        self.read_tag(tag=SerializationTag.kBigInt)
        bitfield = self.read_varint()
        is_negative = bitfield & 1
        byte_count = (bitfield >> 1) & 0b111111111111111111111111111111
        value = int.from_bytes(self.read_bytes(byte_count), byteorder="little")
        if is_negative:
            return -value
        return value

    def read_int32(self) -> int:
        self.read_tag(tag=SerializationTag.kInt32)
        value = self.read_zigzag()
        if value in INT32_RANGE:
            return value
        self.throw(f"Serialized value is out of {INT32_RANGE} for Int32: {value}")

    def read_jsmap(
        self, tag_mapper: TagMapper, *, identity: object
    ) -> Generator[tuple[object, object], None, int]:
        self.read_tag(SerializationTag.kBeginJSMap)
        self.objects.record_reference(identity)
        actual_count = 0

        while self.read_tag(consume=False) != SerializationTag.kEndJSMap:
            yield self.read_object(tag_mapper), self.read_object(tag_mapper)
            actual_count += 2
        self.pos += 1  # advance over EndJSMap
        expected_count = self.read_varint()

        if expected_count != actual_count:
            self.throw(
                f"Expected count does not match actual count after reading "
                f"JSMap: expected={expected_count}, actual={actual_count}"
            )
        return actual_count

    def read_jsset(
        self, tag_mapper: TagMapper, *, identity: object
    ) -> Generator[object, None, int]:
        self.read_tag(SerializationTag.kBeginJSSet)
        self.objects.record_reference(identity)
        actual_count = 0

        while self.read_tag(consume=False) != SerializationTag.kEndJSSet:
            yield self.read_object(tag_mapper)
            actual_count += 1
        self.pos += 1  # advance over EndJSSet

        expected_count = self.read_varint()
        if expected_count != actual_count:
            self.throw(
                f"Expected count does not match actual count after reading "
                f"JSSet: expected={expected_count}, actual={actual_count}"
            )
        return actual_count

    def read_object(self, tag_mapper: TagMapper) -> object:
        tag = self.read_tag(consume=False)
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

    def read_stream__tag_reader(
        tag_mapper: TagMapper, tag: SerializationTag, stream: ReadableTagStream
    ) -> object:
        return read_fn(stream)

    read_stream__tag_reader.__name__ = (
        f"{read_stream__tag_reader.__name__}#{rts_fn.__name__}"
    )
    read_stream__tag_reader.__qualname__ = (
        f"{read_stream__tag_reader.__qualname__}#{rts_fn.__name__}"
    )

    return read_stream__tag_reader


JSMapType = Callable[[], MutableMapping[object, object]]
JSSetType = Callable[[], MutableSet[object]]


@dataclass(slots=True, init=False)
class TagMapper:
    """Defines the conversion of V8 serialization tagged data to Python values."""

    tag_readers: Mapping[SerializationTag, TagReader]
    default_tag_mapper: TagMapper | None
    jsmap_type: JSMapType
    jsset_type: JSSetType

    def __init__(
        self,
        tag_readers: (
            SupportsKeysAndGetItem[SerializationTag, TagReader]
            | Iterable[tuple[SerializationTag, TagReader]]
            | None
        ) = None,
        default_tag_mapper: TagMapper | None = None,
        jsmap_type: JSMapType | None = None,
        jsset_type: JSSetType | None = None,
    ) -> None:
        self.default_tag_mapper = default_tag_mapper
        self.jsmap_type = jsmap_type or dict
        self.jsset_type = jsset_type or set

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
            (SerializationTag.kInt32, ReadableTagStream.read_int32),
        ]
        primitive_tag_readers = {t: read_stream(read_fn) for (t, read_fn) in primitives}

        # TODO: revisit how we register these, should we use a decorator, like
        #       with @singledispatchmethod? (Can't use that directly a it
        #       doesn't dispatch on values or Literal annotations.)
        default_tag_readers: dict[SerializationTag, TagReader] = {
            SerializationTag.kBeginJSMap: TagMapper.deserialize_jsmap,
            SerializationTag.kBeginJSSet: TagMapper.deserialize_jsset,
        }

        return {**primitive_tag_readers, **default_tag_readers, **(tag_readers or {})}

    def deserialize(self, tag: SerializationTag, stream: ReadableTagStream) -> object:
        read_tag = self.tag_readers.get(tag)
        if not read_tag:
            # FIXME: more specific error
            stream.throw(f"No reader is implemented for tag {tag.name}")
        return read_tag(self, tag, stream)

    def deserialize_jsmap(
        self, tag: SerializationTag, stream: ReadableTagStream
    ) -> Mapping[object, object]:
        assert tag == SerializationTag.kBeginJSMap
        # TODO: this model of references makes it impossible to handle immutable
        # collections. We'd need forward references to do that.
        map = self.jsmap_type()
        map.update(stream.read_jsmap(self, identity=map))
        return map

    def deserialize_jsset(
        self, tag: SerializationTag, stream: ReadableTagStream
    ) -> AbstractSet[object]:
        assert tag == SerializationTag.kBeginJSSet
        set = self.jsset_type()
        # MutableSet doesn't provide update()
        for element in stream.read_jsset(self, identity=set):
            set.add(element)
        return set


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
