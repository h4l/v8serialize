from __future__ import annotations

import codecs
import operator
import struct
import sys
from collections.abc import (
    ByteString,
    Iterable,
    Mapping,
    MutableMapping,
    MutableSet,
    Sequence,
)
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from functools import partial
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Callable,
    Final,
    Generator,
    Generic,
    Literal,
    NamedTuple,
    Protocol,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)

from v8serialize._pycompat.dataclasses import slots_if310
from v8serialize._values import (
    AnyJSError,
    ArrayBufferConstructor,
    ArrayBufferTransferConstructor,
    ArrayBufferViewConstructor,
    BufferT,
    JSErrorBuilder,
    SharedArrayBufferConstructor,
    SharedArrayBufferId,
    TransferId,
    ViewT,
)
from v8serialize.constants import (
    INT32_RANGE,
    JS_ARRAY_BUFFER_TAGS,
    JS_CONSTANT_TAGS,
    JS_OBJECT_KEY_TAGS,
    JS_PRIMITIVE_OBJECT_TAGS,
    JS_STRING_TAGS,
    UINT32_RANGE,
    AnySerializationTag,
    ArrayBufferTags,
    ArrayBufferViewFlags,
    ArrayBufferViewTag,
    ConstantTags,
    JSErrorName,
    JSRegExpFlag,
    PrimitiveObjectTag,
    SerializationErrorTag,
    SerializationTag,
    TagConstraint,
    kLatestVersion,
)
from v8serialize.errors import (
    DecodeV8CodecError,
    UnmappedTagDecodeV8CodecError,
    V8CodecError,
)
from v8serialize.jstypes import JSHole, JSObject, JSUndefined
from v8serialize.jstypes._v8 import V8SharedObjectReference, V8SharedValueId
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsbuffers import (
    JSArrayBuffer,
    JSArrayBufferTransfer,
    JSDataView,
    JSSharedArrayBuffer,
    JSTypedArray,
    create_view,
)
from v8serialize.jstypes.jserror import JSError, JSErrorData
from v8serialize.jstypes.jsmap import JSMap
from v8serialize.jstypes.jsprimitiveobject import JSPrimitiveObject
from v8serialize.jstypes.jsregexp import JSRegExp
from v8serialize.jstypes.jsset import JSSet
from v8serialize.references import SerializedId, SerializedObjectLog

if TYPE_CHECKING:
    from typing_extensions import Never, TypeAlias

    from _typeshed import SupportsRead

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
TagT = TypeVar("TagT", bound=AnySerializationTag)

if TYPE_CHECKING:
    TagT_con = TypeVar(
        "TagT_con",
        bound=AnySerializationTag,
        contravariant=True,
        default=AnySerializationTag,
    )
else:
    TagT_con = TypeVar("TagT_con", bound=AnySerializationTag, contravariant=True)


def _decode_zigzag(n: int) -> int:
    """Convert ZigZag encoded unsigned int to signed.

    ZigZag encoding maps signed ints to unsigned: -2 = 3, -1 = 1, 0 = 0, 1 = 2.
    """
    if n % 2:
        return -((n + 1) // 2)
    return n // 2


class ArrayReadResult(NamedTuple):
    """The data being deserialized from a dense or sparse array."""

    length: int
    """The length of the array being deserialized.

    Dense arrays will contain this many items indexed from 0..length -1, plus 0
    or more additional object properties.

    Sparse arrays will contain any number of array items, plus 0 or more
    additional object properties.
    """
    items: Generator[tuple[int | float | str, object], None, int]
    """The array and object properties."""


# 3.9 and 3.10 can't combine NamedTuple with Generic at runtime
# https://bugs.python.org/issue43923
# Could make this a dataclass, but tuple unpacking with types is useful.
if TYPE_CHECKING or sys.version_info >= (3, 11):

    class ReferencedObject(NamedTuple, Generic[T]):
        serialized_id: SerializedId
        object: T

else:

    class ReferencedObject(NamedTuple):
        serialized_id: SerializedId
        object: object


@dataclass(**slots_if310())
class ReadableTagStream:
    data: ByteString
    pos: int = field(default=0)
    objects: SerializedObjectLog = field(default_factory=SerializedObjectLog)
    version: int = field(default=kLatestVersion)

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

    def peak_tag(self) -> SerializationTag | None:
        """Get the current position as a SerializationTag if it is one, or None
        (without advancing position)."""
        if self.eof:
            return None
        value = self.data[self.pos]
        if value in SerializationTag:
            return SerializationTag(value)
        return None

    @overload
    def read_tag(
        self, tag: None = None, *, consume: bool = True
    ) -> SerializationTag: ...

    @overload
    def read_tag(self, tag: TagT, *, consume: bool = True) -> TagT: ...

    @overload
    def read_tag(self, tag: TagConstraint[TagT], *, consume: bool = True) -> TagT: ...

    def read_tag(
        self,
        tag: SerializationTag | TagConstraint | None = None,
        *,
        consume: bool = True,
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
            value = SerializationTag(value)
            if tag is None:
                self.pos += consume
                return value
            elif not isinstance(tag, SerializationTag):
                if value in tag:
                    self.pos += consume
                    return value

                expected = f"Expected tag {tag.allowed_tag_names}"
            else:
                if value is tag:
                    self.pos += consume
                    return value
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

    def read_varint(self, max_bits: int | None = None) -> int:
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
            if max_bits and offset >= max_bits:
                self.throw(f"Varint is larger than {max_bits} bits")
        count = pos - self.pos
        self.pos = pos
        self.throw(
            f"Data truncated: end of stream while reading varint after reading "
            f"{count} bytes"
        )

    def read_zigzag(self, max_bits: int | None = None) -> int:
        uint = self.read_varint(max_bits=max_bits)
        return _decode_zigzag(uint)

    def read_header(self) -> int:
        """Read the V8 serialization stream header and verify it's a supported version.

        @return the header's version number.
        """
        self.read_tag(SerializationTag.kVersion)
        version = self.read_varint()
        # v13 was first released in 2017.
        if version > kLatestVersion or version < 13:
            self.throw(f"Unsupported version {version}")
        self.version = version
        return version

    def read_double(self, *, tag: bool = False) -> float:
        if tag:
            self.read_tag(tag=SerializationTag.kDouble)
        self.ensure_capacity(8)
        value = cast(float, struct.unpack_from("<d", self.data, self.pos)[0])
        self.pos += 8
        return value

    def read_string_onebyte(self, *, tag: bool = False) -> str:
        """Decode a OneByteString, which is latin1-encoded text."""
        if tag:
            self.read_tag(tag=SerializationTag.kOneByteString)
        length = self.read_varint()
        self.ensure_capacity(length)
        # Decoding latin1 can't fail/throw — just 1 byte/char.
        # We use codecs.decode because not all ByteString types have a decode method.
        value = codecs.decode(self.read_bytes(length), "latin1")
        return value

    def read_string_twobyte(self, *, tag: bool = False) -> str:
        """Decode a TwoByteString, which is UTF-16-encoded text."""
        if tag:
            self.read_tag(SerializationTag.kTwoByteString)
        length = self.read_varint()
        try:
            value = codecs.decode(self.read_bytes(length), "utf-16-le")
        except UnicodeDecodeError as e:
            self.pos -= length
            self.throw("TwoByteString is not valid UTF-16 data", cause=e)
        return value

    def read_string_utf8(self, *, tag: bool = False) -> str:
        """Decode a Utf8String, which is UTF8-encoded text."""
        if tag:
            self.read_tag(tag=SerializationTag.kUtf8String)
        length = self.read_varint()
        try:
            value = codecs.decode(self.read_bytes(length), "utf-8")
        except UnicodeDecodeError as e:
            self.pos -= length
            self.throw("Utf8String is not valid UTF-8 data", cause=e)
        return value

    def read_bigint(self, *, tag: bool = False) -> int:
        if tag:
            self.read_tag(tag=SerializationTag.kBigInt)
        bitfield = self.read_varint()
        is_negative = bitfield & 1
        byte_count = (bitfield >> 1) & 0b111111111111111111111111111111
        value = int.from_bytes(self.read_bytes(byte_count), byteorder="little")
        if is_negative:
            return -value
        return value

    def read_int32(self, *, tag: bool = False) -> int:
        if tag:
            self.read_tag(tag=SerializationTag.kInt32)
        value = self.read_zigzag(max_bits=32)
        if value in INT32_RANGE:
            return value
        self.throw(f"Serialized value is out of {INT32_RANGE} for Int32: {value}")

    def read_uint32(self, *, tag: bool = False) -> int:
        if tag:
            self.read_tag(tag=SerializationTag.kUint32)
        value = self.read_varint(max_bits=32)
        if value in UINT32_RANGE:
            return value
        self.throw(f"Serialized value is out of {UINT32_RANGE} for UInt32: {value}")

    def read_js_primitive_object(
        self, tag: PrimitiveObjectTag | None = None
    ) -> tuple[SerializedId, JSPrimitiveObject]:
        if tag and tag not in JS_PRIMITIVE_OBJECT_TAGS:
            raise ValueError("tag must be a primitive object tag")

        if tag is None:
            tag = self.read_tag(tag=JS_PRIMITIVE_OBJECT_TAGS if tag is None else tag)
        result: JSPrimitiveObject
        if tag is SerializationTag.kTrueObject:
            result = JSPrimitiveObject(True)
        elif tag is SerializationTag.kFalseObject:
            result = JSPrimitiveObject(False)
        elif tag is SerializationTag.kNumberObject:
            result = JSPrimitiveObject(self.read_double(tag=False))
        elif tag is SerializationTag.kBigIntObject:
            result = JSPrimitiveObject(
                self.read_bigint(tag=False), tag=SerializationTag.kBigIntObject
            )
        elif tag is SerializationTag.kStringObject:
            result = JSPrimitiveObject(self.read_string_utf8(tag=False))
        else:
            raise AssertionError(f"Unreachable: {tag}")
        return self.objects.record_reference(result), result

    def read_js_regexp(
        self, ctx: DecodeContext, *, tag: bool = False
    ) -> tuple[SerializedId, JSRegExp]:
        if tag:
            self.read_tag(tag=SerializationTag.kRegExp)
        source = ctx.decode_object(tag=self.read_tag(tag=JS_STRING_TAGS))
        assert isinstance(source, str)
        flags = JSRegExpFlag(self.read_varint())
        result = JSRegExp(source, flags)
        return self.objects.record_reference(result), result

    def read_error_tag(self) -> SerializationErrorTag:
        self.ensure_capacity(1)
        code = self.read_varint()
        if code in SerializationErrorTag:
            return SerializationErrorTag(code)
        self.throw(
            f"Expected an error tag but found {self.data[self.pos]} "
            f"(not a valid error tag)"
        )

    @overload
    def read_js_error(
        self, ctx: DecodeContext, *, error: JSErrorBuilder[T], tag: bool = False
    ) -> ReferencedObject[T]: ...

    @overload
    def read_js_error(
        self, ctx: DecodeContext, *, error: None = None, tag: bool = False
    ) -> ReferencedObject[AnyJSError]: ...

    def read_js_error(
        self,
        ctx: DecodeContext,
        *,
        error: JSErrorBuilder[T] | None = None,
        tag: bool = False,
    ) -> ReferencedObject[T] | ReferencedObject[AnyJSError]:
        # The current V8 serialization logic uses a fixed order for error
        # fields, so we take the same approach. In principle we could read them
        # in a loop for maximum compatibility with varying serialization
        # strategies. It seems likely that any other implementations will need
        # to retain compatibility with V8's fixed order, so this seems fine.
        error_data: AnyJSError = JSErrorData()
        if tag:
            self.read_tag(SerializationTag.kError)
        etag = self.read_error_tag()

        error_name = JSErrorName.for_error_tag(etag)
        if error_name is not JSErrorName.Error:
            etag = self.read_error_tag()
        error_data.name = error_name

        message: object = None
        if etag is SerializationErrorTag.Message:
            message = ctx.decode_object(tag=self.read_tag(tag=JS_STRING_TAGS))
            etag = self.read_error_tag()
        assert message is None or isinstance(message, str)
        error_data.message = message

        stack_seen = False
        stack: object = None
        if etag is SerializationErrorTag.Stack:
            stack_seen = True
            stack = ctx.decode_object(tag=self.read_tag(tag=JS_STRING_TAGS))
            etag = self.read_error_tag()
        assert stack is None or isinstance(stack, str)
        error_data.stack = stack

        error_obj, error_data = (
            (error_data, error_data) if error is None else error(error_data)
        )
        serialized_id = self.objects.record_reference(error_obj)

        cause: object = None
        if etag is SerializationErrorTag.Cause:
            cause = ctx.decode_object()
            etag = self.read_error_tag()
        error_data.cause = cause

        # A change in Nov 2023 made a change to the Error [de]serialization that
        # affects backwards comparability, but didn't change the format version
        # number: https://chromium-review.googlesource.com/c/v8/v8/+/5012806
        # Before this change, `stack` was written after `cause` (here), and
        # V8 read error properties in any order, by looping and reading
        # whichever field occurred next until End was seen.
        #
        # After this change, `stack` was written before the `cause`, (not here),
        # and V8 would only read error fields in the new order. As a result, V8
        # after this change could not read errors with stacks serialized by the
        # old implementation (although the format number was unchanged).
        #
        # In order to support both versions, we try to re-read the stack in this
        # position if we didn't previously read it.
        if not stack_seen and etag is SerializationErrorTag.Stack:
            stack = ctx.decode_object(tag=self.read_tag(tag=JS_STRING_TAGS))
            etag = self.read_error_tag()
            assert stack is None or isinstance(stack, str)
            error_data.stack = stack

        if etag is not SerializationErrorTag.End:
            self.throw(
                f"Expected End error tag after reading error fields but found "
                f"{etag.name}"
            )

        return cast(
            "ReferencedObject[T] | ReferencedObject[AnyJSError]",
            ReferencedObject(serialized_id, error_obj),
        )

    def read_js_date(
        self, *, tz: tzinfo | None = None, tag: bool = False
    ) -> ReferencedObject[datetime]:
        if tag:
            self.read_tag(SerializationTag.kDate)
        epoch_ms = self.read_double(tag=False)
        result = datetime.fromtimestamp(epoch_ms / 1000, tz=tz)
        return ReferencedObject(self.objects.record_reference(result), result)

    def read_jsmap(
        self, ctx: DecodeContext, *, identity: object, tag: bool = False
    ) -> Generator[tuple[object, object], None, int]:
        if tag:
            self.read_tag(SerializationTag.kBeginJSMap)
        self.objects.record_reference(identity)
        actual_count = 0

        while (next_tag := self.read_tag()) != SerializationTag.kEndJSMap:
            yield ctx.decode_object(tag=next_tag), ctx.decode_object()
            actual_count += 2
        expected_count = self.read_varint()

        if expected_count != actual_count:
            self.throw(
                f"Expected count does not match actual count after reading "
                f"JSMap: expected={expected_count}, actual={actual_count}"
            )
        return actual_count

    def read_jsset(
        self, ctx: DecodeContext, *, identity: object, tag: bool = False
    ) -> Generator[object, None, int]:
        if tag:
            self.read_tag(SerializationTag.kBeginJSSet)
        self.objects.record_reference(identity)
        actual_count = 0

        while (next_tag := self.read_tag()) != SerializationTag.kEndJSSet:
            yield ctx.decode_object(tag=next_tag)
            actual_count += 1

        expected_count = self.read_varint()
        if expected_count != actual_count:
            self.throw(
                f"Expected count does not match actual count after reading "
                f"JSSet: expected={expected_count}, actual={actual_count}"
            )
        return actual_count

    def read_js_object(
        self, ctx: DecodeContext, *, identity: object, tag: bool = False
    ) -> Generator[tuple[int | float | str, object], None, int]:
        if tag:
            self.read_tag(SerializationTag.kBeginJSObject)
        self.objects.record_reference(identity)

        actual_count = yield from self._read_js_object_properties(ctx)
        return actual_count

    def _read_js_object_properties(
        self,
        ctx: DecodeContext,
        *,
        end_tag: SerializationTag = SerializationTag.kEndJSObject,
        enclosing_name: str = "JSObject",
    ) -> Generator[tuple[int | float | str, object], None, int]:
        actual_count = 0
        while True:
            tag = self.read_tag()
            if tag in JS_OBJECT_KEY_TAGS:
                key = ctx.decode_object(tag=tag)
                if not isinstance(key, (int, float, str)):
                    # TODO: more specific error
                    raise TypeError(
                        f"{enclosing_name} key must deserialize to str, int or "
                        f"float: {key}"
                    )
                yield key, ctx.decode_object()
                actual_count += 1  # 1 per entry, unlike JSMap
            elif tag is end_tag:
                break
            else:
                self.throw(
                    f"{enclosing_name} has a key encoded with tag {tag.name} "
                    f"that is not a number or string tag. Valid "
                    f"{JS_OBJECT_KEY_TAGS}"
                )

        expected_count = self.read_varint()
        if expected_count != actual_count:
            self.throw(
                f"Expected properties count does not match actual count after reading "
                f"{enclosing_name}: expected={expected_count}, actual={actual_count}"
            )
        return actual_count

    def read_js_array_dense(
        self, ctx: DecodeContext, *, identity: object, tag: bool = False
    ) -> Generator[
        tuple[int | float | str, object], None, tuple[int, int]
    ]:  # TODO: return tuple of (length: int, items: Generator) ?
        if tag:
            self.read_tag(SerializationTag.kBeginDenseJSArray)
        self.objects.record_reference(identity)
        current_array_el_count = 0
        expected_array_el_count = self.read_varint()

        for i in range(expected_array_el_count):
            yield i, ctx.decode_object()
            current_array_el_count += 1

        actual_properties_count = yield from self._read_js_object_properties(
            ctx,
            end_tag=SerializationTag.kEndDenseJSArray,
            enclosing_name="DenseJSArray",
        )
        final_array_el_count = self.read_varint()

        if expected_array_el_count != final_array_el_count:
            self.throw(
                "Expected array length does not match the final length after "
                f"reading DenseJSArray: expected={expected_array_el_count}"
                f", final={final_array_el_count}"
            )
        return final_array_el_count, actual_properties_count

    def read_js_array_sparse(
        self, ctx: DecodeContext, *, identity: object, tag: bool = False
    ) -> ArrayReadResult:
        if tag:
            self.read_tag(SerializationTag.kBeginSparseJSArray)
        self.objects.record_reference(identity)
        expected_array_length = self.read_varint()

        def read_items() -> Generator[tuple[int | float | str, object], None, int]:
            actual_properties_count = yield from self._read_js_object_properties(
                ctx,
                end_tag=SerializationTag.kEndSparseJSArray,
                enclosing_name="SparseJSArray",
            )
            final_array_length = self.read_varint()
            if expected_array_length != final_array_length:
                self.throw(
                    "Expected array length does not match the final length "
                    f"after reading SparseJSArray: expected={expected_array_length}"
                    f", final={final_array_length}"
                )
            return actual_properties_count

        return ArrayReadResult(length=expected_array_length, items=read_items())

    def read_object_reference(
        self, *, tag: bool = False
    ) -> tuple[SerializedId, object]:
        if tag:
            self.read_tag(SerializationTag.kObjectReference)
        serialized_id = SerializedId(self.read_varint())

        try:
            return serialized_id, self.objects.get_object(serialized_id)
        except V8CodecError as e:
            self.throw(
                "ObjectReference contains serialized ID which has not been "
                "deserialized",
                cause=e,
            )

    def read_js_array_buffer(
        self,
        *,
        array_buffer: ArrayBufferConstructor[BufferT],
        shared_array_buffer: SharedArrayBufferConstructor[BufferT],
        array_buffer_transfer: ArrayBufferTransferConstructor[BufferT],
        tag: ArrayBufferTags | None = None,
    ) -> BufferT | ViewT:
        if tag is None:
            tag = self.read_tag(tag=JS_ARRAY_BUFFER_TAGS)
        elif tag not in JS_ARRAY_BUFFER_TAGS:
            raise ValueError("tag must be an array buffer tag")

        buffer: BufferT
        if tag is SerializationTag.kArrayBuffer:
            buffer = self._read_js_array_buffer(array_buffer=array_buffer)
        elif tag is SerializationTag.kResizableArrayBuffer:
            buffer = self._read_js_array_buffer_resizable(array_buffer=array_buffer)
        elif tag is SerializationTag.kSharedArrayBuffer:
            buffer = self._read_js_array_buffer_shared(
                shared_array_buffer=shared_array_buffer
            )
        elif tag is SerializationTag.kArrayBufferTransfer:
            buffer = self._read_js_array_buffer_transfer(
                array_buffer_transfer=array_buffer_transfer
            )
        else:
            raise AssertionError(f"Unreachable: {tag.name}")
        return buffer

    def _read_js_array_buffer(
        self, array_buffer: ArrayBufferConstructor[BufferT], tag: bool = False
    ) -> BufferT:
        if tag:
            self.read_tag(SerializationTag.kArrayBuffer)
        byte_length = self.read_uint32()
        if self.pos + byte_length > len(self.data):
            self.throw(
                f"ArrayBuffer byte length exceeds available data: {byte_length=}"
            )

        with memoryview(self.data)[
            self.pos : self.pos + byte_length
        ].toreadonly() as buffer_data:
            result = array_buffer(
                data=buffer_data, max_byte_length=None, resizable=False
            )
            self.objects.record_reference(result)
        self.pos += byte_length
        return result

    def _read_js_array_buffer_resizable(
        self, *, array_buffer: ArrayBufferConstructor[BufferT], tag: bool = False
    ) -> BufferT:
        if tag:
            self.read_tag(SerializationTag.kResizableArrayBuffer)
        byte_length = self.read_uint32()
        if self.pos + byte_length >= len(self.data):
            self.throw(
                f"ArrayBuffer byte length exceeds available data: {byte_length=}"
            )
        max_byte_length = self.read_uint32()
        if max_byte_length < byte_length:
            self.throw(
                f"ResizableArrayBuffer max byte length is less than current "
                f"byte length: {byte_length=}, {max_byte_length=}"
            )

        with memoryview(self.data)[
            self.pos : self.pos + byte_length
        ].toreadonly() as buffer_data:
            result = array_buffer(
                data=buffer_data, max_byte_length=max_byte_length, resizable=True
            )
            self.objects.record_reference(result)
        self.pos += byte_length
        return result

    def _read_js_array_buffer_shared(
        self,
        *,
        shared_array_buffer: SharedArrayBufferConstructor[BufferT],
        tag: bool = False,
    ) -> BufferT:
        if tag:
            self.read_tag(SerializationTag.kSharedArrayBuffer)
        index = self.read_uint32()
        return shared_array_buffer(buffer_id=SharedArrayBufferId(index))

    def _read_js_array_buffer_transfer(
        self,
        *,
        array_buffer_transfer: ArrayBufferTransferConstructor[BufferT],
        tag: bool = False,
    ) -> BufferT:
        if tag:
            self.read_tag(SerializationTag.kArrayBufferTransfer)
        transfer_id = self.read_uint32()
        return array_buffer_transfer(transfer_id=TransferId(transfer_id))

    def read_js_array_buffer_view(
        self,
        backing_buffer: BufferT,
        *,
        array_buffer_view: ArrayBufferViewConstructor[BufferT, ViewT],
        tag: bool = False,
    ) -> ViewT:
        if tag:
            self.read_tag(SerializationTag.kArrayBufferView)
        raw_view_tag = self.read_varint()
        if raw_view_tag not in ArrayBufferViewTag:
            self.throw(
                f"ArrayBufferView view type {hex(raw_view_tag)} is not a known type"
            )
        # TODO: should it be this method's responsibility to bounds-check the
        #   view? I'm leaning towards no, as we can't check the two reference
        #   buffer types anyway.
        byte_offset = self.read_uint32()
        byte_length = self.read_uint32()
        flags = ArrayBufferViewFlags(0)
        if self.version >= 14:  # flags field was added in v14
            flags = ArrayBufferViewFlags(self.read_varint())

        result = array_buffer_view(
            buffer=backing_buffer,
            format=ArrayBufferViewTag(raw_view_tag),
            byte_offset=byte_offset,
            byte_length=(
                None if ArrayBufferViewFlags.IsLengthTracking in flags else byte_length
            ),
        )
        self.objects.record_reference(result)
        return result

    def read_host_object(
        self, deserializer: HostObjectDeserializer[T], tag: bool = False
    ) -> T:
        if tag:
            self.read_tag(SerializationTag.kHostObject)
        if isinstance(deserializer, HostObjectDeserializerObj):
            return deserializer.deserialize_host_object(stream=self)
        return deserializer(stream=self)

    def read_v8_shared_object_reference(
        self, tag: bool = False
    ) -> ReferencedObject[V8SharedObjectReference]:
        if tag:
            self.read_tag(SerializationTag.kSharedObject)
        result = V8SharedObjectReference(V8SharedValueId(self.read_uint32(tag=False)))
        return ReferencedObject(self.objects.record_reference(result), result)


class HostObjectDeserializerFn(Protocol[T_co]):
    def __call__(self, *, stream: ReadableTagStream) -> T_co: ...


@runtime_checkable
class HostObjectDeserializerObj(Protocol[T_co]):
    @property
    def deserialize_host_object(self) -> HostObjectDeserializerFn[T_co]: ...


HostObjectDeserializer: TypeAlias = (
    "HostObjectDeserializerObj[T_co] | HostObjectDeserializerFn[T_co]"
)


class TagReader(Protocol[TagT_con]):
    def __call__(
        self,
        tag_mapper: TagMapper,
        tag: TagT_con,
        ctx: DecodeContext,
        /,
    ) -> object: ...


@dataclass(init=False, **slots_if310())
class TagReaderRegistry:
    index: Mapping[SerializationTag, TagReader[SerializationTag]]
    _index: dict[SerializationTag, TagReader[SerializationTag]]

    def __init__(self, entries: TagReaderRegistry | None = None) -> None:
        self._index = {}
        self.index = MappingProxyType(self._index)
        if entries:
            self.register_all(entries)

    # TODO: - could extract tags from tag_reader fn signature (messy pre 3.10
    #         though)
    #       - could pre-bind tag arg value with partial
    def register(
        self, tag: TagT | TagConstraint[TagT], tag_reader: TagReader[TagT]
    ) -> None:
        if isinstance(tag, TagConstraint):
            for t in sorted(tag.allowed_tags):
                self._index[cast(SerializationTag, t)] = cast(
                    TagReader[SerializationTag], tag_reader
                )
        else:
            self._index[cast(SerializationTag, tag)] = cast(
                TagReader[SerializationTag], tag_reader
            )

    def register_all(self, registry: TagReaderRegistry) -> None:
        self._index.update(registry.index)

    def match(self, tag: TagT) -> TagReader[TagT] | None:
        return self._index.get(tag)


class ReadableTagStreamReadFunction(Protocol):
    def __call__(self, cls: ReadableTagStream, /) -> object: ...

    @property
    def __name__(self) -> str: ...


def read_stream(rts_fn: ReadableTagStreamReadFunction) -> TagReader:
    """Create a TagReader that calls a primitive read_xxx function on the stream."""

    read_fn = operator.methodcaller(rts_fn.__name__)

    def read_stream__tag_reader(
        tag_mapper: TagMapper, tag: SerializationTag, ctx: DecodeContext
    ) -> object:
        return read_fn(ctx.stream)

    read_stream__tag_reader.__name__ = (
        f"{read_stream__tag_reader.__name__}#{rts_fn.__name__}"
    )
    read_stream__tag_reader.__qualname__ = (
        f"{read_stream__tag_reader.__qualname__}#{rts_fn.__name__}"
    )

    return read_stream__tag_reader


class DecodeContext(Protocol):
    if TYPE_CHECKING:

        @property
        def stream(self) -> ReadableTagStream: ...

    else:
        # test/test_protocol_dataclass_interaction.py
        stream = ...

    def decode_object(self, *, tag: SerializationTag | None = ...) -> object: ...


class DeserializeNextFn(Protocol):
    # TODO: should we allow passing tag? Is there ever a valid use case for
    #   changing the apparent tag? Seems lke the DecodeContext should control it
    def __call__(self, tag: SerializationTag, /) -> object: ...


class DeserializeTagFn(Protocol):
    def __call__(
        self, tag: SerializationTag, /, ctx: DecodeContext, next: DeserializeNextFn
    ) -> object: ...


class TagMapperObject(Protocol):
    deserialize: DeserializeTagFn


AnyTagMapper: TypeAlias = "TagMapperObject | DeserializeTagFn"


@dataclass(init=False, **slots_if310())
class DefaultDecodeContext(DecodeContext):
    tag_mappers: Sequence[AnyTagMapper]
    stream: ReadableTagStream

    @overload
    def __init__(
        self,
        *,
        data: None = None,
        stream: ReadableTagStream,
        tag_mappers: Iterable[AnyTagMapper] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        data: ByteString,
        stream: None = None,
        tag_mappers: Iterable[AnyTagMapper] | None = None,
    ) -> None: ...

    def __init__(
        self,
        *,
        data: ByteString | None = None,
        stream: ReadableTagStream | None = None,
        tag_mappers: Iterable[AnyTagMapper] | None = None,
    ) -> None:
        if stream is None:
            if data is None:
                raise ValueError("data or stream must be provided")
            stream = ReadableTagStream(data)
        elif data is not None:
            raise ValueError("data and stream cannot both be provided")

        self.stream = stream
        self.tag_mappers = list(
            default_tag_mappers if tag_mappers is None else tag_mappers
        )

    def __decode_object_with_mapper(self, tag: SerializationTag, *, i: int) -> object:
        if i < len(self.tag_mappers):
            tm = self.tag_mappers[i]
            next = partial(self.__decode_object_with_mapper, i=i + 1)
            if callable(tm):
                return tm(tag, ctx=self, next=next)
            else:
                return tm.deserialize(tag, ctx=self, next=next)
        self._report_unmapped_value(tag)
        raise AssertionError("report_unmapped_value returned")

    def decode_object(self, *, tag: SerializationTag | None = None) -> object:
        if tag is None:
            tag = self.stream.read_tag()
        return self.__decode_object_with_mapper(tag, i=0)

    def _report_unmapped_value(self, tag: SerializationTag) -> Never:
        raise UnmappedTagDecodeV8CodecError(
            f"No tag mapper was able to read the tag {tag.name}",
            tag=tag,
            position=self.stream.pos,
            data=self.stream.data,
        )


JSMapType = Callable[[], MutableMapping[object, object]]
JSSetType = Callable[[], MutableSet[object]]
JSObjectType = Callable[[], JSObject[object]]
JSArrayType = Callable[[], JSArray[object]]


@dataclass(init=False, **slots_if310())
class TagMapper(TagMapperObject):
    """Defines the conversion of V8 serialization tagged data to Python values."""

    tag_readers: TagReaderRegistry
    default_tag_mapper: TagMapper | None
    jsmap_type: JSMapType
    jsset_type: JSSetType
    js_object_type: JSObjectType
    js_array_type: JSArrayType
    js_constants: Mapping[ConstantTags, object]
    host_object_deserializer: HostObjectDeserializer[object] | None
    js_error_builder: JSErrorBuilder[object]
    default_timezone: tzinfo | None

    def __init__(
        self,
        tag_readers: TagReaderRegistry | None = None,
        default_tag_mapper: TagMapper | None = None,
        jsmap_type: JSMapType | None = None,
        jsset_type: JSSetType | None = None,
        js_object_type: JSObjectType | None = None,
        js_array_type: JSArrayType | None = None,
        js_constants: Mapping[ConstantTags, object] | None = None,
        host_object_deserializer: HostObjectDeserializer[object] | None = None,
        js_error_builder: JSErrorBuilder[object] | None = None,
        default_timezone: tzinfo | None = None,
    ) -> None:
        self.default_tag_mapper = default_tag_mapper
        self.jsmap_type = jsmap_type or JSMap
        self.jsset_type = jsset_type or JSSet
        self.js_object_type = js_object_type or JSObject
        self.js_array_type = js_array_type or JSArray
        self.host_object_deserializer = host_object_deserializer
        self.js_error_builder = js_error_builder or JSError.builder
        self.default_timezone = default_timezone

        _js_constants = dict(js_constants) if js_constants is not None else {}
        _js_constants.setdefault(SerializationTag.kTheHole, JSHole)
        _js_constants.setdefault(SerializationTag.kUndefined, JSUndefined)
        _js_constants.setdefault(SerializationTag.kNull, None)
        _js_constants.setdefault(SerializationTag.kTrue, True)
        _js_constants.setdefault(SerializationTag.kFalse, False)
        self.js_constants = _js_constants

        self.tag_readers = TagReaderRegistry(tag_readers)
        self.register_tag_readers(self.tag_readers)

    def register_tag_readers(self, tag_readers: TagReaderRegistry) -> None:
        # TODO: revisit how we register these, should we use a decorator, like
        #       with @singledispatchmethod? (Can't use that directly a it
        #       doesn't dispatch on values or Literal annotations.)

        r = tag_readers.register

        # fmt: off

        # primitives — just read the stream directly, no handling needed
        r(SerializationTag.kDouble, read_stream(ReadableTagStream.read_double))
        r(SerializationTag.kOneByteString, read_stream(ReadableTagStream.read_string_onebyte))  # noqa: B950
        r(SerializationTag.kTwoByteString, read_stream(ReadableTagStream.read_string_twobyte))  # noqa: B950
        r(SerializationTag.kUtf8String, read_stream(ReadableTagStream.read_string_utf8))
        r(SerializationTag.kBigInt, read_stream(ReadableTagStream.read_bigint))
        r(SerializationTag.kInt32, read_stream(ReadableTagStream.read_int32))
        r(SerializationTag.kUint32, read_stream(ReadableTagStream.read_uint32))

        # Tags which require tag-specific behaviour
        r(JS_CONSTANT_TAGS, TagMapper.deserialize_constant)
        r(SerializationTag.kRegExp, TagMapper.deserialize_js_regexp)
        r(SerializationTag.kBeginJSMap, TagMapper.deserialize_jsmap)
        r(SerializationTag.kBeginJSSet, TagMapper.deserialize_jsset)
        r(SerializationTag.kObjectReference, TagMapper.deserialize_object_reference)
        r(SerializationTag.kBeginJSObject, TagMapper.deserialize_js_object)
        r(SerializationTag.kBeginDenseJSArray, TagMapper.deserialize_js_array_dense)
        r(SerializationTag.kBeginSparseJSArray, TagMapper.deserialize_js_array_sparse)
        r(JS_ARRAY_BUFFER_TAGS, TagMapper.deserialize_js_array_buffer)
        r(SerializationTag.kArrayBufferView, TagMapper.deserialize_js_array_buffer_view)
        r(JS_PRIMITIVE_OBJECT_TAGS, TagMapper.deserialize_js_primitive_object)
        r(SerializationTag.kError, TagMapper.deserialize_js_error)
        r(SerializationTag.kDate, TagMapper.deserialize_js_date)
        r(SerializationTag.kSharedObject, TagMapper.deserialize_v8_shared_object_reference)  # noqa: B950
        r(SerializationTag.kWasmModuleTransfer, TagMapper.deserialize_unsupported_wasm)
        r(SerializationTag.kWasmMemoryTransfer, TagMapper.deserialize_unsupported_wasm)
        r(SerializationTag.kHostObject, TagMapper.deserialize_host_object)

        # fmt: on

    def deserialize(
        self, tag: SerializationTag, /, ctx: DecodeContext, next: DeserializeNextFn
    ) -> object:
        read_tag = self.tag_readers.match(tag)
        if not read_tag:
            return next(tag)
        return read_tag(self, tag, ctx)

    def deserialize_constant(self, tag: ConstantTags, ctx: DecodeContext) -> object:
        return self.js_constants[tag]

    def deserialize_jsmap(
        self, tag: Literal[SerializationTag.kBeginJSMap], ctx: DecodeContext
    ) -> Mapping[object, object]:
        assert tag == SerializationTag.kBeginJSMap
        # TODO: this model of references makes it impossible to handle immutable
        # collections. We'd need forward references to do that.
        map = self.jsmap_type()
        map.update(ctx.stream.read_jsmap(ctx, identity=map))
        return map

    def deserialize_jsset(
        self, tag: Literal[SerializationTag.kBeginJSSet], ctx: DecodeContext
    ) -> AbstractSet[object]:
        assert tag == SerializationTag.kBeginJSSet
        set = self.jsset_type()
        # MutableSet's types expect AbstractSet for RHS of |= but implementations
        # accept any iterable in practice.
        set |= ctx.stream.read_jsset(ctx, identity=set)  # type: ignore[arg-type]
        return set

    def deserialize_js_object(
        self, tag: Literal[SerializationTag.kBeginJSObject], ctx: DecodeContext
    ) -> JSObject[object]:
        assert tag == SerializationTag.kBeginJSObject
        obj = self.js_object_type()
        obj.update(ctx.stream.read_js_object(ctx, identity=obj))
        return obj

    def deserialize_js_array_dense(
        self,
        tag: Literal[SerializationTag.kBeginDenseJSArray],
        ctx: DecodeContext,
    ) -> JSArray[object]:
        assert tag == SerializationTag.kBeginDenseJSArray
        obj = self.js_array_type()
        obj.update(ctx.stream.read_js_array_dense(ctx, identity=obj))
        return obj

    def deserialize_js_array_sparse(
        self,
        tag: Literal[SerializationTag.kBeginSparseJSArray],
        ctx: DecodeContext,
    ) -> JSArray[object]:
        assert tag == SerializationTag.kBeginSparseJSArray
        obj = self.js_array_type()
        length, items = ctx.stream.read_js_array_sparse(ctx, identity=obj)
        if length > 0:
            # TODO: obj.array.resize() does not swap dense to sparse, so we
            #   can't use it to resize here. Maybe we should push the storage
            #   method choice into ArrayProperties so that it can manage the
            #   switch instead of JSObject/JSArray.
            obj[length - 1] = JSHole  # resize to length
        obj.update(items)
        return obj

    def deserialize_js_array_buffer_view(
        self, tag: Literal[SerializationTag.kArrayBufferView], ctx: DecodeContext
    ) -> Never:
        # The ArrayBuffer views must be serialized directly after an ArrayBuffer
        # or an object reference to an ArrayBuffer.
        ctx.stream.throw(
            f"Found an orphaned {tag.name} without a preceding ArrayBuffer"
        )

    def deserialize_js_array_buffer(
        self,
        tag: ArrayBufferTags,
        ctx: DecodeContext,
    ) -> (
        JSArrayBuffer
        | JSSharedArrayBuffer
        | JSArrayBufferTransfer
        | JSTypedArray
        | JSDataView
    ):
        buffer: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer = (
            ctx.stream.read_js_array_buffer(
                array_buffer=JSArrayBuffer,
                shared_array_buffer=JSSharedArrayBuffer,
                array_buffer_transfer=JSArrayBufferTransfer,
                tag=tag,
            )
        )

        # Buffers can be followed by a BufferView which wraps the buffer.
        # Warning: current value may not be a tag, e.g. at EOF or if the buffer
        # is the cause object of an Error (then it'll be an End error tag).
        if ctx.stream.peak_tag() is SerializationTag.kArrayBufferView:
            view: JSTypedArray | JSDataView = ctx.stream.read_js_array_buffer_view(
                backing_buffer=buffer, array_buffer_view=create_view, tag=True
            )
            return view
        return buffer

    def deserialize_host_object(
        self, tag: Literal[SerializationTag.kHostObject], ctx: DecodeContext
    ) -> object:
        if self.host_object_deserializer is None:
            ctx.stream.throw(
                "Stream contains HostObject data without deserializer available "
                "to handle it. TagMapper needs a host_object_deserializer set "
                "to read this serialized data."
            )
        return ctx.stream.read_host_object(self.host_object_deserializer)

    def deserialize_v8_shared_object_reference(
        self, tag: Literal[SerializationTag.kSharedObject], ctx: DecodeContext
    ) -> V8SharedObjectReference:
        return ctx.stream.read_v8_shared_object_reference().object

    def deserialize_object_reference(
        self, tag: Literal[SerializationTag.kObjectReference], ctx: DecodeContext
    ) -> object:
        assert tag == SerializationTag.kObjectReference
        serialized_id, obj = ctx.stream.read_object_reference()

        if isinstance(
            obj,
            (JSArrayBuffer, JSSharedArrayBuffer, JSArrayBufferTransfer),
        ):
            # Object references can be followed by a ArrayBufferView that
            # wraps the buffer referenced by the reference.
            # Warning: current value may not be a tag, e.g. at EOF or if the
            # buffer is the cause object of an Error (then it'll be an End error
            # tag).
            if ctx.stream.peak_tag() is SerializationTag.kArrayBufferView:
                return ctx.stream.read_js_array_buffer_view(
                    backing_buffer=obj, array_buffer_view=create_view, tag=True
                )

        return obj

    def deserialize_js_primitive_object(
        self, tag: PrimitiveObjectTag, ctx: DecodeContext
    ) -> object:
        serialized_id, obj = ctx.stream.read_js_primitive_object(tag)
        # Unwrap objects so they act like regular strings/numbers/bools.
        # (Alternatively, we could make the wrapper types subclasses of their
        # wrapped value type and keep the wrapper.)
        ctx.stream.objects.replace_reference(serialized_id, obj.value)
        return obj.value

    def deserialize_js_regexp(
        self, tag: Literal[SerializationTag.kRegExp], ctx: DecodeContext
    ) -> JSRegExp:
        _, regexp = ctx.stream.read_js_regexp(ctx)
        return regexp

    def deserialize_js_error(
        self, tag: Literal[SerializationTag.kError], ctx: DecodeContext
    ) -> object:
        _, js_error = ctx.stream.read_js_error(ctx, error=self.js_error_builder)
        return js_error

    def deserialize_unsupported_wasm(
        self,
        tag: Literal[
            SerializationTag.kWasmMemoryTransfer, SerializationTag.kWasmModuleTransfer
        ],
        ctx: DecodeContext,
    ) -> Never:
        ctx.stream.throw(
            f"Stream contains a {tag.name} which is not supported. V8's "
            "serialized WASM objects use shared ArrayBuffers/transfer IDs that "
            "are only accessible from within the V8 process that serializes them."
        )

    def deserialize_js_date(
        self, tag: Literal[SerializationTag.kDate], ctx: DecodeContext
    ) -> datetime:
        return ctx.stream.read_js_date(tz=self.default_timezone).object


default_tag_mappers: Final[Sequence[AnyTagMapper]] = [TagMapper()]


@dataclass(init=False)
class Decoder:
    tag_mappers: Sequence[AnyTagMapper]

    def __init__(self, tag_mappers: Iterable[AnyTagMapper] | None = None) -> None:
        self.tag_mappers = (
            default_tag_mappers if tag_mappers is None else tuple(tag_mappers)
        )

    def decode(self, fp: SupportsRead[bytes]) -> object:
        # TODO: could mmap when fp is a file
        return self.decodes(fp.read())

    def decodes(self, data: ByteString) -> object:
        ctx = DefaultDecodeContext(
            stream=ReadableTagStream(data), tag_mappers=self.tag_mappers
        )
        ctx.stream.read_header()
        return ctx.decode_object()


def loads(
    data: ByteString, *, tag_mappers: Iterable[AnyTagMapper] | None = None
) -> object:
    """Deserialize a JavaScript value encoded in V8 serialization format."""
    return Decoder(tag_mappers=tag_mappers).decodes(data)
