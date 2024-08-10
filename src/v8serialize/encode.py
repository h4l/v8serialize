from __future__ import annotations

import struct
from collections import abc
from dataclasses import dataclass, field
from functools import partial
from typing import (
    AbstractSet,
    Iterable,
    Literal,
    Mapping,
    Never,
    Protocol,
    Sequence,
    overload,
)

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
        ctx: EncodeContext,
        *,
        identity: object | None = None,
    ) -> None:
        self.objects.record_reference(items if identity is None else identity)
        self.write_tag(SerializationTag.kBeginJSMap)
        count = 0
        for key, value in items:
            self.write_object(key, ctx=ctx)
            self.write_object(value, ctx=ctx)
            count += 2
        self.write_tag(SerializationTag.kEndJSMap)
        self.write_varint(count)

    def write_jsset(
        self,
        values: Iterable[object],
        ctx: EncodeContext,
        *,
        identity: object | None = None,
    ) -> None:
        self.objects.record_reference(values if identity is None else identity)
        self.write_tag(SerializationTag.kBeginJSSet)
        count = 0
        for value in values:
            self.write_object(value, ctx=ctx)
            count += 1
        self.write_tag(SerializationTag.kEndJSSet)
        self.write_varint(count)

    @overload
    def write_object_reference(
        self, *, obj: object, serialized_id: None = None
    ) -> None: ...

    @overload
    def write_object_reference(
        self,
        *,
        serialized_id: SerializedId,
        obj: None = None,
    ) -> None: ...

    def write_object_reference(
        self, *, obj: object | None = None, serialized_id: SerializedId | None = None
    ) -> None:
        if obj is not None:
            serialized_id = self.objects.get_serialized_id(obj)
        else:
            assert serialized_id is not None
            self.objects.get_object(serialized_id)  # throws if invalid

        self.write_tag(SerializationTag.kObjectReference)
        self.write_varint(serialized_id)

    # TODO: should this just be a method of EncodeContext, not here?
    def write_object(self, value: object, ctx: EncodeContext) -> None:
        ctx.serialize(value)


class EncodeContext(Protocol):
    """Maintains the state needed to write Python objects in V8 format."""

    object_mappers: Sequence[ObjectMapperObject | SerializeObjectFn]
    stream: WritableTagStream

    def serialize(self, value: object) -> None:
        """Serialize a single Python value to the stream.

        The object_mappers convert the Python value to JavaScript representation,
        and the stream writes out V8 serialization format tagged data.
        """


class SerializeNextFn(Protocol):
    def __call__(self, value: object, /) -> None: ...


class SerializeObjectFn(Protocol):
    def __call__(
        self, value: object, /, ctx: DefaultEncodeContext, next: SerializeNextFn
    ) -> None: ...


class ObjectMapperObject(Protocol):
    serialize: SerializeObjectFn


AnyObjectMapper = ObjectMapperObject | SerializeObjectFn


@dataclass(slots=True, init=False)
class DefaultEncodeContext(EncodeContext):
    object_mappers: Sequence[ObjectMapperObject | SerializeObjectFn]
    stream: WritableTagStream

    def __init__(
        self,
        object_mappers: Iterable[ObjectMapperObject | SerializeObjectFn] | None = None,
        *,
        stream: WritableTagStream | None = None,
    ) -> None:
        self.object_mappers = list(
            default_object_mappers if object_mappers is None else object_mappers
        )
        self.stream = WritableTagStream() if stream is None else stream

    def __serialize(self, value: object, *, i: int) -> None:
        if i < len(self.object_mappers):
            om = self.object_mappers[i]
            next = partial(self.__serialize, i=i + 1)
            if callable(om):
                return om(value, ctx=self, next=next)
            else:
                return om.serialize(value, ctx=self, next=next)
        self._report_unmapped_value(value)
        raise AssertionError("report_unmapped_value returned")

    def serialize(self, value: object) -> None:
        """Serialize a single Python value to the stream.

        The object_mappers convert the Python value to JavaScript representation,
        and the stream writes out V8 serialization format tagged data.
        """
        return self.__serialize(value, i=0)

    def _report_unmapped_value(self, value: object) -> Never:
        raise UnmappedValueEncodeV8CodecError(
            "No object mapper was able to write the value", value=value
        )


@dataclass(slots=True)
class ObjectMapper(ObjectMapperObject):
    """Defines the conversion of Python types into the V8 serialization format.

    ObjectMappers are responsible for making suitable calls to a WritableTagStream
    to represent Python objects with the various encoded representations supported
    by the V8 serialization format.

    The stream delegates back to the mapper when writing hierarchical objects,
    like arrays, to let the mapper drive the encoded representation of each
    sub-object.
    """

    @singledispatchmethod
    def serialize(  # type: ignore[override]
        self, value: object, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        next(value)

    # Must use explicit type in register() as singledispatchmethod is not using
    # the first positional argument's type annotation because it fails to read
    # them in order (seems like a bug).
    # TODO: replace @singledispatchmethod with a purpose-specific solution.

    @serialize.register(int)
    def serialize_int(
        self, value: int, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        if value in INT32_RANGE:
            ctx.stream.write_int32(value)
        else:
            ctx.stream.write_bigint(value)

    @serialize.register(str)
    def serialize_str(
        self, value: str, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_string_utf8(value)

    @serialize.register(float)
    def serialize_float(
        self, value: float, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_double(value)

    @serialize.register(abc.Mapping)
    def serialize_mapping(
        self,
        value: Mapping[object, object],
        /,
        ctx: EncodeContext,
        next: SerializeNextFn,
    ) -> None:
        ctx.stream.write_jsmap(value.items(), ctx=ctx, identity=value)

    @serialize.register(abc.Set)
    def serialize_set(
        self, value: AbstractSet[object], /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_jsset(value, ctx=ctx)


def serialize_object_references(
    value: object, /, ctx: EncodeContext, next: SerializeNextFn
) -> None:
    """A SerializeObjectFn that writes references to previously-seen objects.

    Objects that have already been written to the stream are written as
    references to the original instance, which avoids duplication of data and
    preserves object identity after de-serializing.
    """
    if value in ctx.stream.objects:
        ctx.stream.write_object_reference(obj=value)
    else:
        next(value)


default_object_mappers: tuple[AnyObjectMapper, ...] = (
    serialize_object_references,
    ObjectMapper(),
)


@dataclass(init=False)
class Encoder:
    """Encode Python values in the V8 serialization format.

    Encoder is a high-level interface wraps an ObjectMapper andWritableTagStream
    to decide how to represent Python types, and write out the V8 tag data
    respectively.
    """

    object_mappers: Sequence[AnyObjectMapper]

    def __init__(self, object_mappers: Iterable[AnyObjectMapper] | None = None) -> None:
        self.object_mappers = (
            default_object_mappers if object_mappers is None else tuple(object_mappers)
        )

    def encode(self, value: object) -> bytearray:
        ctx = DefaultEncodeContext(
            stream=WritableTagStream(), object_mappers=self.object_mappers
        )
        ctx.stream.write_header()
        ctx.serialize(value)
        return ctx.stream.data


def dumps(
    value: object, *, object_mappers: Iterable[AnyObjectMapper] | None = None
) -> bytes:
    """Encode a Python value in the V8 serialization format."""
    encoder = Encoder(object_mappers=object_mappers)
    return bytes(encoder.encode(value))
