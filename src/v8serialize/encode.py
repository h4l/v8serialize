from __future__ import annotations

import struct
from collections import abc
from dataclasses import dataclass, field
from typing import AbstractSet, Iterable, Literal, Mapping, Never, Protocol, overload

from v8serialize.constants import INT32_RANGE, SerializationTag, kLatestVersion
from v8serialize.decorators import singledispatchmethod
from v8serialize.errors import V8CodecError
from v8serialize.references import SerializedId, SerializedObjectLog


@dataclass(init=False)
class EncodeV8CodecError(V8CodecError, ValueError):
    pass


@dataclass(init=False)
class UnmappedValueEncodeV8CodecError(EncodeV8CodecError, ValueError):
    """Raised when attempting to serialize an object that the ObjectMapper does
    not know how to represent as V8 serialization tags.
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


def _encode_zigzag(number: int) -> int:
    return abs(number * 2) - (number < 0)


@dataclass(slots=True)
class WritableTagStream:
    """Write individual tagged data items in the V8 serialization format.

    This is a low-level interface to incrementally generate a V8 serialization
    byte stream. The Encoder in conjunction with ObjectMapper provides the
    high-level interface to serialize data in V8 format.
    """

    data: bytearray = field(default_factory=bytearray)
    objects: SerializedObjectLog = field(default_factory=SerializedObjectLog)

    @property
    def pos(self) -> int:
        return len(self.data)

    def write_tag(self, tag: SerializationTag | None) -> None:
        if tag is not None:
            self.data.append(tag)

    def write_varint(self, n: int) -> None:
        if n < 0:
            raise ValueError(f"varint must be non-negative: {n}")
        while True:
            uint7 = n & 0b1111111
            n >>= 7
            if n == 0:
                self.data.append(uint7)
                return
            self.data.append(uint7 | 0b10000000)

    def write_zigzag(self, n: int) -> None:
        self.write_varint(_encode_zigzag(n))

    def write_header(self) -> None:
        """Write the V8 serialization stream header."""
        self.write_tag(SerializationTag.kVersion)
        self.write_varint(kLatestVersion)

    def write_double(
        self,
        value: float,
        *,
        tag: Literal[SerializationTag.kDouble] | None = SerializationTag.kDouble,
    ) -> None:
        self.write_tag(tag)
        self.data.extend(struct.pack("<d", value))

    def write_string_onebyte(
        self,
        value: str,
        *,
        tag: (
            Literal[SerializationTag.kOneByteString] | None
        ) = SerializationTag.kOneByteString,
    ) -> None:
        """Encode a OneByte string, which is latin1-encoded text."""
        try:
            encoded = value.encode("latin1")
        except UnicodeEncodeError as e:
            raise ValueError(
                "Attempted to encode non-latin1 string in OneByte representation"
            ) from e
        self.write_tag(tag)
        self.write_varint(len(encoded))
        self.data.extend(encoded)

    def write_string_twobyte(
        self,
        value: str,
        *,
        tag: (
            Literal[SerializationTag.kTwoByteString] | None
        ) = SerializationTag.kTwoByteString,
    ) -> None:
        encoded = value.encode("utf-16-le")
        tag_pos = self.pos
        self.write_tag(tag)
        self.write_varint(len(encoded))
        # V8 implementation states that existing code expects TwoByteString to
        # be aligned (to even bytes).
        if tag is not None and self.pos & 1:
            self.data.insert(tag_pos, SerializationTag.kPadding)
        self.data.extend(encoded)

    def write_string_utf8(
        self,
        value: str,
        *,
        tag: (
            Literal[SerializationTag.kUtf8String] | None
        ) = SerializationTag.kUtf8String,
    ) -> None:
        """Encode a Utf8String, which is UTF-8-encoded text.

        **Note: We never encode Utf8String at runtime, but we use it to test the
        decoder. The V8 implementation only decodes Utf8String.**
        """
        encoded = value.encode("utf-8")
        self.write_tag(tag)
        self.write_varint(len(encoded))
        self.data.extend(encoded)

    def write_bigint(
        self,
        value: int,
        *,
        tag: Literal[SerializationTag.kBigInt] | None = SerializationTag.kBigInt,
    ) -> None:
        byte_length = (value.bit_length() + 8) // 8  # round up
        if byte_length.bit_length() > 30:
            raise ValueError(
                f"Python int is too large to represent as JavaScript BigInt: "
                f"30 bits are available to represent the byte length, but this "
                f"int needs {byte_length.bit_length()}"
            )
        bitfield = (byte_length << 1) | (value < 0)
        digits = abs(value).to_bytes(length=byte_length, byteorder="little")
        self.write_tag(tag)
        self.write_varint(bitfield)
        self.data.extend(digits)

    def write_int32(
        self,
        value: int,
        tag: Literal[SerializationTag.kInt32] | None = SerializationTag.kInt32,
    ) -> None:
        if value not in INT32_RANGE:
            raise ValueError(
                f"Python int is too large to represent as Int32: value must be "
                f"in {INT32_RANGE}"
            )
        self.write_tag(tag)
        self.write_zigzag(value)

    def write_jsmap(
        self,
        items: Iterable[tuple[object, object]],
        object_mapper: ObjectMapperSerialize,
        *,
        identity: object | None = None,
    ) -> None:
        self.objects.record_reference(items if identity is None else identity)
        self.write_tag(SerializationTag.kBeginJSMap)
        count = 0
        for key, value in items:
            self.write_object(key, object_mapper)
            self.write_object(value, object_mapper)
            count += 2
        self.write_tag(SerializationTag.kEndJSMap)
        self.write_varint(count)

    def write_jsset(
        self,
        values: Iterable[object],
        object_mapper: ObjectMapperSerialize,
        *,
        identity: object | None = None,
    ) -> None:
        self.objects.record_reference(values if identity is None else identity)
        self.write_tag(SerializationTag.kBeginJSSet)
        count = 0
        for value in values:
            self.write_object(value, object_mapper)
            count += 1
        self.write_tag(SerializationTag.kEndJSSet)
        self.write_varint(count)

    def write_object(self, value: object, object_mapper: ObjectMapperSerialize) -> None:
        object_mapper.serialize(value, self)


class ObjectMapperSerialize(Protocol):
    def serialize(self, value: object, stream: WritableTagStream) -> None: ...


@dataclass(slots=True)
class ObjectMapper(ObjectMapperSerialize):
    """Defines the conversion of Python types into the V8 serialization format.

    ObjectMappers are responsible for making suitable calls to a WritableTagStream
    to represent Python objects with the various encoded representations supported
    by the V8 serialization format.

    The stream delegates back to the mapper when writing hierarchical objects,
    like arrays, to let the mapper drive the encoded representation of each
    sub-object.
    """

    def report_unmapped_value(self, value: object) -> Never:
        raise UnmappedValueEncodeV8CodecError(
            "No serialize method was able to write a value", value=value
        )

    @singledispatchmethod
    def serialize(self, value: object, stream: WritableTagStream) -> None:
        self.report_unmapped_value(value)
        raise AssertionError("report_unmapped_value returned")

    @serialize.register
    def _(self, value: int, stream: WritableTagStream) -> None:
        if value in INT32_RANGE:
            stream.write_int32(value)
        else:
            stream.write_bigint(value)

    @serialize.register
    def _(self, value: str, stream: WritableTagStream) -> None:
        stream.write_string_utf8(value)

    @serialize.register
    def _(self, value: float, stream: WritableTagStream) -> None:
        stream.write_double(value)

    @serialize.register(abc.Mapping)
    def serialize_mapping(
        self, value: Mapping[object, object], stream: WritableTagStream
    ) -> None:
        stream.write_jsmap(value.items(), object_mapper=self, identity=value)

    @serialize.register(abc.Set)
    def serialize_set(
        self, value: AbstractSet[object], stream: WritableTagStream
    ) -> None:
        stream.write_jsset(value, object_mapper=self)


@dataclass(init=False)
class Encoder:
    """Encode Python values in the V8 serialization format.

    Encoder is a high-level interface wraps an ObjectMapper andWritableTagStream
    to decide how to represent Python types, and write out the V8 tag data
    respectively.
    """

    object_mapper: ObjectMapper

    def __init__(self, object_mapper: ObjectMapper | None = None) -> None:
        self.object_mapper = object_mapper or ObjectMapper()

    def encode(self, value: object) -> bytearray:
        stream = WritableTagStream()
        stream.write_header()
        stream.write_object(value, self.object_mapper)
        return stream.data


def dumps(value: object, *, object_mapper: ObjectMapper | None = None) -> bytes:
    """Encode a Python value in the V8 serialization format."""
    encoder = Encoder(object_mapper=object_mapper)
    return bytes(encoder.encode(value))
