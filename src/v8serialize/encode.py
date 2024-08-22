from __future__ import annotations

import re
import struct
from collections import abc
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import lru_cache, partial
from types import NoneType, TracebackType
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Any,
    AnyStr,
    Iterable,
    Literal,
    Mapping,
    Never,
    Protocol,
    Sequence,
    TypeAlias,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)

from v8serialize._values import (
    AnyArrayBuffer,
    AnyArrayBufferTransfer,
    AnyArrayBufferView,
    AnySharedArrayBuffer,
)
from v8serialize.constants import (
    FLOAT64_SAFE_INT_RANGE,
    INT32_RANGE,
    JS_CONSTANT_TAGS,
    JS_OBJECT_KEY_TAGS,
    MAX_ARRAY_LENGTH,
    MAX_ARRAY_LENGTH_REPR,
    UINT32_RANGE,
    ArrayBufferViewFlags,
    ConstantTags,
    SerializationTag,
    TagConstraint,
    kLatestVersion,
)
from v8serialize.decorators import singledispatchmethod
from v8serialize.errors import V8CodecError
from v8serialize.jstypes import JSObject
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsarrayproperties import JSHoleEnum, JSHoleType
from v8serialize.jstypes.jsbuffers import (
    BaseJSArrayBuffer,
    JSArrayBuffer,
    JSArrayBufferTransfer,
    JSArrayBufferView,
    JSSharedArrayBuffer,
)
from v8serialize.jstypes.jsprimitiveobject import JSPrimitiveObject
from v8serialize.jstypes.jsregexp import JSRegExp
from v8serialize.jstypes.jsundefined import JSUndefinedEnum, JSUndefinedType
from v8serialize.references import SerializedId, SerializedObjectLog

if TYPE_CHECKING:
    from functools import _lru_cache_wrapper

T = TypeVar("T")
T_con = TypeVar("T_con", contravariant=True)


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
class TagConstraintRemover(AbstractContextManager[None, None]):
    """Context manager that removes the current tag constraint on a
    WritableTagStream.
    """

    stream: WritableTagStream

    def __enter__(self) -> None:
        pass

    def __exit__(
        self,
        exc_cls: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
        /,
    ) -> None:
        self.stream.allowed_tags = None


@dataclass(slots=True, frozen=True)
class SerializedObjectReference:
    serialized_tag: SerializationTag
    serialized_id: SerializedId


@dataclass(slots=True)
class WritableTagStream:
    """Write individual tagged data items in the V8 serialization format.

    This is a low-level interface to incrementally generate a V8 serialization
    byte stream. The Encoder in conjunction with ObjectMapper provides the
    high-level interface to serialize data in V8 format.
    """

    data: bytearray = field(default_factory=bytearray)
    objects: SerializedObjectLog = field(default_factory=SerializedObjectLog)

    allowed_tags: TagConstraint | None = field(init=False, default=None)
    """When set, only tags allowed by the constraint may be written.

    For example, when writing JavaScript Object keys, constraint is
    `v8serialize.constants.JS_OBJECT_KEY_CONSTRAINT`, which only allows strings and
    numbers other than bigint.
    """
    __tag_constraint_remover: TagConstraintRemover = field(
        compare=False,
        repr=False,
        init=False,
    )

    def __post_init__(self) -> None:
        self.__tag_constraint_remover = TagConstraintRemover(self)

    def constrain_tags(self, allowed_tags: TagConstraint) -> TagConstraintRemover:
        """Set `allowed_tags` to prevent tags being written which are not valid
        in a given context.

        Returns a context manager that removes the constraint it exits. Note
        that constraints do not stack — an existing set of allowed_tags is
        replaced.
        """
        self.allowed_tags = allowed_tags
        return self.__tag_constraint_remover

    @property
    def pos(self) -> int:
        return len(self.data)

    def write_tag(self, tag: SerializationTag | None) -> None:
        if tag is not None:
            if self.allowed_tags is not None and tag not in self.allowed_tags:
                raise EncodeV8CodecError(
                    f"Attempted to write tag {tag.name} in a context where "
                    f"allowed tags are {self.allowed_tags}"
                )
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

    def write_constant(self, constant: ConstantTags) -> None:
        with self.constrain_tags(JS_CONSTANT_TAGS):
            self.write_tag(constant)

    def write_header(self) -> None:
        """Write the V8 serialization stream header."""
        self.write_tag(SerializationTag.kVersion)
        self.write_varint(kLatestVersion)

    def write_double(
        self,
        value: float | int,
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

    def write_uint32(
        self,
        value: int,
    ) -> None:
        if value not in UINT32_RANGE:
            raise ValueError(
                f"Python int is too large to represent as Uint32: value must be "
                f"in {UINT32_RANGE}"
            )
        self.write_tag(SerializationTag.kUint32)
        self.write_varint(value)

    def write_js_primitive_object(
        self, obj: JSPrimitiveObject, *, identity: object | None = None
    ) -> None:
        self.objects.record_reference(obj if identity is None else identity)
        tag = obj.tag
        value = obj.value
        self.write_tag(tag)
        if tag is SerializationTag.kStringObject:
            assert isinstance(value, str)
            self.write_string_utf8(value, tag=None)
        elif (
            tag is SerializationTag.kTrueObject or tag is SerializationTag.kFalseObject
        ):
            # no data — nothing to do
            assert value is True or value is False
        elif tag is SerializationTag.kBigIntObject:
            assert isinstance(value, (int, float)) and value.is_integer()
            self.write_bigint(int(value), tag=None)
        elif tag is SerializationTag.kNumberObject:
            assert isinstance(value, (float, int))
            self.write_double(value, tag=None)
        else:
            raise AssertionError(f"Unexpected tag: {tag}")

    def write_js_regexp(
        self, regexp: JSRegExp, *, identity: object | None = None
    ) -> None:
        self.write_tag(SerializationTag.kRegExp)
        # We can write any of the string formats here, but just UTF-8 seems fine
        self.write_string_utf8(regexp.source)
        self.write_varint(regexp.flags.canonical)

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

    def write_js_object(
        self,
        items: Iterable[tuple[object, object]],
        ctx: EncodeContext,
        *,
        identity: object | None = None,
    ) -> None:
        self.objects.record_reference(items if identity is None else identity)
        self.write_tag(SerializationTag.kBeginJSObject)
        self._write_js_object_properties(items, ctx)

    def _write_js_object_properties(
        self,
        items: Iterable[tuple[object, object]],
        ctx: EncodeContext,
        *,
        end_tag: SerializationTag = SerializationTag.kEndJSObject,
    ) -> None:
        count = 0
        for key, value in items:
            with self.constrain_tags(JS_OBJECT_KEY_TAGS):
                self.write_object(key, ctx=ctx)
            self.write_object(value, ctx=ctx)
            count += 1
        self.write_tag(end_tag)
        self.write_varint(count)

    @overload
    def write_js_array_dense(
        self,
        array: Sequence[object],
        ctx: EncodeContext,
        *,
        properties: Iterable[tuple[Any, Any]],  # FIXME: [object, object]
        identity: object,
    ) -> None: ...

    @overload
    def write_js_array_dense(
        self,
        array: Sequence[object],
        ctx: EncodeContext,
        *,
        properties: None = ...,
        identity: object | None = ...,
    ) -> None: ...

    def write_js_array_dense(
        self,
        array: Sequence[object],
        ctx: EncodeContext,
        *,
        properties: Iterable[tuple[Any, Any]] | None = None,
        identity: object | None = None,
    ) -> None:
        if identity is None:
            if properties is not None:
                raise ValueError(
                    "identity is ambiguous: identity must be set when both "
                    "array and properties are provided"
                )
            identity = array
        self.objects.record_reference(identity)
        self.write_tag(SerializationTag.kBeginDenseJSArray)
        array_length = len(array)
        self.write_varint(array_length)
        array_el_count = 0

        for el in array:
            self.write_object(el, ctx)
            array_el_count += 1
        assert array_el_count == array_length

        properties_count = 0
        for key, value in [] if properties is None else properties:
            with self.constrain_tags(JS_OBJECT_KEY_TAGS):
                self.write_object(key, ctx=ctx)
            self.write_object(value, ctx=ctx)
            properties_count += 1
        self.write_tag(SerializationTag.kEndDenseJSArray)
        self.write_varint(properties_count)
        self.write_varint(array_el_count)

    def write_js_array_sparse(
        self,
        items: Iterable[tuple[object, object]],
        ctx: EncodeContext,
        *,
        length: int,
        identity: object | None = None,
    ) -> None:
        if not (0 <= length <= MAX_ARRAY_LENGTH):
            raise ValueError(
                f"length must be >= 0 and <= ${MAX_ARRAY_LENGTH_REPR}: {length=}"
            )
        self.objects.record_reference(items if identity is None else identity)
        self.write_tag(SerializationTag.kBeginSparseJSArray)
        self.write_varint(length)
        self._write_js_object_properties(
            items, ctx, end_tag=SerializationTag.kEndSparseJSArray
        )
        self.write_varint(length)

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

    def write_js_array_buffer(
        self,
        buffer: AnyArrayBuffer | AnySharedArrayBuffer | AnyArrayBufferTransfer,
        *,
        identity: object | None = None,
    ) -> None:
        if isinstance(buffer, AnyArrayBuffer):
            if buffer.resizable:
                self._write_js_array_buffer_resizable(buffer, identity=identity)
            else:
                self._write_js_array_buffer(buffer, identity=identity)
        elif isinstance(buffer, AnySharedArrayBuffer):
            self._write_js_array_buffer_shared(buffer, identity=identity)
        elif isinstance(buffer, AnyArrayBufferTransfer):
            self._write_js_array_buffer_transfer(buffer, identity=identity)
        else:
            raise AssertionError(f"Unknown array buffer data: {buffer}")

    def _write_js_array_buffer(
        self, buffer: AnyArrayBuffer, *, identity: object | None = None
    ) -> None:
        assert not buffer.resizable
        self.objects.record_reference(buffer if identity is None else identity)
        self.write_tag(SerializationTag.kArrayBuffer)
        with memoryview(buffer.data) as buffer_data:
            self.write_varint(len(buffer_data))
            self.data.extend(buffer_data)

    def _write_js_array_buffer_resizable(
        self, buffer: AnyArrayBuffer, *, identity: object | None = None
    ) -> None:
        assert buffer.resizable
        with memoryview(buffer.data) as buffer_data:
            if buffer.max_byte_length < len(buffer_data):
                raise ValueError(
                    f"max_byte_length must be >= len(data): "
                    f"{buffer.max_byte_length=}, {len(buffer_data)=}"
                )
            self.objects.record_reference(buffer if identity is None else identity)
            self.write_tag(SerializationTag.kResizableArrayBuffer)
            # TODO: validate uint32
            self.write_varint(len(buffer_data))
            self.write_varint(buffer.max_byte_length)
            self.data.extend(buffer_data)

    def _write_js_array_buffer_shared(
        self, buffer: AnySharedArrayBuffer, *, identity: object | None = None
    ) -> None:
        if buffer.buffer_id < 0:
            raise ValueError(f"buffer_id cannot be negative: {buffer.buffer_id=}")
        self.objects.record_reference(buffer if identity is None else identity)
        self.write_tag(SerializationTag.kSharedArrayBuffer)
        self.write_varint(buffer.buffer_id)

    def _write_js_array_buffer_transfer(
        self, buffer: AnyArrayBufferTransfer, *, identity: object | None = None
    ) -> None:
        if buffer.transfer_id < 0:
            raise ValueError(f"transfer_id cannot be negative: {buffer.transfer_id=}")
        self.objects.record_reference(buffer if identity is None else identity)
        self.write_tag(SerializationTag.kArrayBufferTransfer)
        self.write_varint(buffer.transfer_id)

    def write_js_array_buffer_view(
        self, buffer_view: AnyArrayBufferView, *, identity: object | None = None
    ) -> None:
        self.objects.record_reference(buffer_view if identity is None else identity)
        self.write_tag(SerializationTag.kArrayBufferView)
        self.write_varint(buffer_view.view_tag.value)
        self.write_varint(buffer_view.byte_offset)
        # 0 / None when flags.IsBufferResizable
        self.write_varint(buffer_view.byte_length or 0)

        flags = ArrayBufferViewFlags(0)
        if isinstance(buffer_view, JSArrayBuffer) and buffer_view.resizable:
            flags |= ArrayBufferViewFlags.IsBufferResizable
        if buffer_view.byte_length is None:
            flags |= ArrayBufferViewFlags.IsLengthTracking

        self.write_varint(flags)

    def write_host_object(
        self, value: T, *, serializer: HostObjectSerializer[T]
    ) -> None:
        self.write_tag(SerializationTag.kHostObject)
        if isinstance(serializer, HostObjectSerializerObj):
            serializer.serialize_host_object(value=value, stream=self)
        else:
            serializer(value=value, stream=self)

    # TODO: should this just be a method of EncodeContext, not here?
    def write_object(self, value: object, ctx: EncodeContext) -> None:
        ctx.serialize(value)


class HostObjectSerializerFn(Protocol[T_con]):
    def __call__(self, *, stream: WritableTagStream, value: T_con) -> None: ...


@runtime_checkable
class HostObjectSerializerObj(Protocol[T_con]):
    @property
    def serialize_host_object(self) -> HostObjectSerializerFn[T_con]: ...


HostObjectSerializer: TypeAlias = (
    HostObjectSerializerObj[T_con] | HostObjectSerializerFn[T_con]
)


class EncodeContext(Protocol):
    """Maintains the state needed to write Python objects in V8 format."""

    object_mappers: Sequence[ObjectMapperObject | SerializeObjectFn]
    stream: WritableTagStream

    def serialize(self, value: object) -> None:
        """Serialize a single Python value to the stream.

        The object_mappers convert the Python value to JavaScript representation,
        and the stream writes out V8 serialization format tagged data.
        """

    def deduplicate(self, value: T) -> T:
        """Look up and return a previously seen value equal to this value.

        If value is not hashable or not found, it's returned as-is.
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
    _memoized: _lru_cache_wrapper[Any]

    def __init__(
        self,
        object_mappers: Iterable[ObjectMapperObject | SerializeObjectFn] | None = None,
        *,
        stream: WritableTagStream | None = None,
        deduplicate_max_size: int | None = None,
    ) -> None:
        self.object_mappers = list(
            default_object_mappers if object_mappers is None else object_mappers
        )
        self.stream = WritableTagStream() if stream is None else stream

        self._memoized = lru_cache(maxsize=deduplicate_max_size, typed=True)(
            lambda x: x
        )

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

    def deduplicate(self, value: T) -> T:
        if getattr(value, "__hash__", None) is not None:
            return self._memoized(value)  # type: ignore[no-any-return]
        return value


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
        if value in UINT32_RANGE:
            ctx.stream.write_uint32(value)
        elif value in INT32_RANGE:
            ctx.stream.write_int32(value)
        elif value in FLOAT64_SAFE_INT_RANGE:
            ctx.stream.write_double(value)
        else:
            # Can't use bigints for object keys, so write large ints as strings
            if ctx.stream.allowed_tags is JS_OBJECT_KEY_TAGS:
                ctx.stream.write_object(str(value), ctx=ctx)
            else:
                ctx.stream.write_bigint(value)

    @serialize.register(JSHoleEnum)
    def serialize_hole(
        self, value: JSHoleType, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_constant(SerializationTag.kTheHole)

    @serialize.register(JSUndefinedEnum)
    def serialize_undefined(
        self, value: JSUndefinedType, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_constant(SerializationTag.kUndefined)

    @serialize.register(bool)
    def serialize_bool(
        self, value: bool, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_constant(
            SerializationTag.kTrue if value else SerializationTag.kFalse
        )

    @serialize.register(cast(Any, NoneType))  # None confuses the register() type
    def serialize_none(
        self, value: None, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_constant(SerializationTag.kNull)

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

    @serialize.register(JSPrimitiveObject)
    def serialize_js_primitive_object(
        self, value: JSPrimitiveObject, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_js_primitive_object(value)

    @serialize.register(JSRegExp)
    def serialize_js_regexp(
        self, value: JSRegExp, /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_js_regexp(value)

    @serialize.register(re.Pattern)
    def serialize_python_regexp(
        self, value: re.Pattern[AnyStr], /, ctx: EncodeContext, next: SerializeNextFn
    ) -> None:
        ctx.stream.write_js_regexp(JSRegExp.from_python_pattern(value))

    @serialize.register(JSObject)
    def serialize_js_object(
        self,
        value: JSObject[object],
        /,
        ctx: EncodeContext,
        next: SerializeNextFn,
    ) -> None:
        ctx.stream.write_js_object(value.items(), ctx=ctx, identity=value)

    @serialize.register(JSArray)
    def serialize_js_array(
        self,
        value: JSArray[object],
        /,
        ctx: EncodeContext,
        next: SerializeNextFn,
    ) -> None:
        # Dense hole tags take 1 byte for the hole tag
        elements_used, length = value.array.elements_used, len(value.array)
        dense_hole_bytes = length - elements_used
        # Sparse key indexes take 1 + 1-2 bytes for indexes up to 2**14 - 1
        # (key type tag + 1-2 bytes varint). 1 + 3 up to 2**21 - 1.
        sparse_key_bytes = elements_used * (3 if length < 2**14 else 4)
        sparse_is_smaller = sparse_key_bytes < dense_hole_bytes

        if sparse_is_smaller:
            ctx.stream.write_js_array_sparse(
                value.items(), ctx=ctx, length=length, identity=value
            )
        else:
            ctx.stream.write_js_array_dense(
                value.array,
                ctx=ctx,
                properties=value.properties.items(),
                identity=value,
            )

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

    @serialize.register(BaseJSArrayBuffer)
    def serialize_js_array_buffer(
        self,
        value: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer,
        /,
        ctx: EncodeContext,
        next: SerializeNextFn,
    ) -> None:
        ctx.stream.write_js_array_buffer(value)

    @serialize.register(bytes)
    @serialize.register(bytearray)
    @serialize.register(memoryview)
    def serialize_buffer(
        self,
        value: bytes | bytearray,
        /,
        ctx: EncodeContext,
        next: SerializeNextFn,
    ) -> None:
        with memoryview(value) as data:
            ctx.stream.write_js_array_buffer(
                buffer=JSArrayBuffer(data), identity=ctx.deduplicate(value)
            )

    @serialize.register(JSArrayBufferView)
    def serialize_buffer_view(
        self,
        value: JSArrayBufferView,
        /,
        ctx: EncodeContext,
        next: SerializeNextFn,
    ) -> None:
        ctx.serialize(value.backing_buffer)
        ctx.stream.write_js_array_buffer_view(value)


def serialize_object_references(
    value: object, /, ctx: EncodeContext, next: SerializeNextFn
) -> None:
    """A SerializeObjectFn that writes references to previously-seen objects.

    Objects that have already been written to the stream are written as
    references to the original instance, which avoids duplication of data and
    preserves object identity after de-serializing.
    """
    value = ctx.deduplicate(value)
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
