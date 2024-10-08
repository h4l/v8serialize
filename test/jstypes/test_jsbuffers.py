from __future__ import annotations

import math
import re
import struct
import sys
from array import array
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING

import pytest
from typing_extensions import Literal

from v8serialize._pycompat.re import RegexFlag
from v8serialize.constants import ArrayBufferViewTag
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    BackportJSFloat16Array,
    BaseJSArrayBuffer,
    BoundsJSArrayBufferError,
    ByteLengthJSArrayBufferError,
    DataFormat,
    DataType,
    ItemSizeJSArrayBufferError,
    JSArrayBuffer,
    JSArrayBufferTransfer,
    JSArrayBufferView,
    JSDataView,
    JSFloat64Array,
    JSInt8Array,
    JSInt32Array,
    JSSharedArrayBuffer,
    JSUint8Array,
    JSUint16Array,
    JSUint32Array,
)

if TYPE_CHECKING:
    from typing_extensions import Buffer


def test_DataType() -> None:
    assert DataType.UnsignedInt.struct_formats == "BHILQ"
    assert DataType.UnsignedInt.python_type is int
    assert DataType.SignedInt.struct_formats == "bhilq"
    assert DataType.SignedInt.python_type is int
    assert DataType.Float.struct_formats == "efd"
    assert DataType.Float.python_type is float
    assert DataType.Bytes.struct_formats == "c"
    assert DataType.Bytes.python_type is bytes


def test_DataFormat() -> None:
    uint64 = DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=8).format
    assert struct.calcsize(uint64) == 8
    assert struct.unpack(uint64, b"\xff" * 8)[0] == 2**64 - 1

    int32 = DataFormat.resolve(data_type=DataType.SignedInt, byte_length=4).format
    assert struct.calcsize(int32) == 4
    assert struct.unpack(int32, b"\xff" * 4)[0] == -1

    float16 = DataFormat.resolve(data_type=DataType.Float, byte_length=2).format
    assert struct.calcsize(float16) == 2
    assert math.isnan(struct.unpack(float16, b"\xff" * 2)[0])

    bytesfmt = DataFormat.resolve(data_type=DataType.Bytes, byte_length=1).format
    assert struct.calcsize(bytesfmt) == 1
    assert struct.unpack(bytesfmt, b"\xff")[0] == b"\xff"

    with pytest.raises(
        ValueError, match=r"DataType UnsignedInt has no struct_format of byte_length 3"
    ):
        DataFormat.resolve(data_type=DataType.UnsignedInt, byte_length=3)


def test_ArrayBufferViewStructFormat() -> None:
    assert ArrayBufferViewStructFormat.Int16Array.view_type.data_format.format == "h"
    assert ArrayBufferViewStructFormat.Int16Array.view_type.data_format.byte_length == 2

    sf = ArrayBufferViewStructFormat(ArrayBufferViewTag.kBigUint64Array)
    assert sf.view_tag is ArrayBufferViewTag.kBigUint64Array
    assert sf.view_type.data_format.byte_length == 8

    hash(ArrayBufferViewStructFormat.Int8Array)

    with pytest.raises(FrozenInstanceError):
        ArrayBufferViewStructFormat.Int8Array.view_type = (
            ArrayBufferViewStructFormat.Uint8Array.view_type
        )


def test_int8array() -> None:
    buffer = JSArrayBuffer(bytearray(16))
    view = JSInt8Array(buffer)

    assert view.element_type is int
    assert view.view_tag is ArrayBufferViewTag.kInt8Array

    with view.get_buffer() as buf:
        buf[0] = 127
        buf[1] = -128

    assert buffer.data[0] == 127
    assert buffer.data[1] == 128


def test_dataview() -> None:
    buffer = bytearray(128)
    view = JSDataView(buffer)

    assert view.view_tag is ArrayBufferViewTag.kDataView
    assert view.data_format.data_type == DataType.Bytes

    with view.get_buffer() as buf:
        buf.set_float64(8, math.pi)
        assert buf.get_float64(8) == math.pi


def test_JSArrayBuffer_init__readonly() -> None:
    with pytest.raises(ValueError, match="cannot be both resizable and readonly"):
        JSArrayBuffer(b"", resizable=True, readonly=True)

    with pytest.raises(
        ValueError,
        match="data must be a bytearray when copy_data is False and resizable is True",
    ):
        JSArrayBuffer(b"", resizable=True, copy_data=False)

    ba = bytearray([1, 2])
    buf = JSArrayBuffer(ba, copy_data=False, readonly=True)
    assert buf.data.readonly
    assert buf.data.tolist() == [1, 2]

    buf = JSArrayBuffer(memoryview(ba), copy_data=False, readonly=True)
    assert buf.data.readonly
    assert buf.data.tolist() == [1, 2]

    buf = JSArrayBuffer(2, copy_data=False, readonly=True)
    assert buf.data.readonly
    assert buf.data.tolist() == [0, 0]


def test_JSArrayBuffer_init__copy_data() -> None:
    # default is to copy — immutable data is mutable in the copy
    for copy_data in [True, None]:
        buf = JSArrayBuffer(bytes([1, 2]), resizable=True, copy_data=copy_data)
        buf.resize(1)
        assert len(buf.data) == 1
        buf.data[0] = 10
        assert buf.data.tolist() == [10]

    # When readonly, the copy is not writable
    src = bytearray([1, 2])
    buf = JSArrayBuffer(src, readonly=True, copy_data=True)
    assert buf.data.readonly
    src[0] = 3
    assert buf.data.tolist() == [1, 2]  # change not seen because src was copied

    # readonly data stays readonly
    buf = JSArrayBuffer(bytes([1, 2]), copy_data=False)
    assert buf.data.readonly
    assert buf.data.tolist() == [1, 2]

    # writable data is modified in-place
    for s in [bytearray([1, 2]), memoryview(bytearray([1, 2]))]:
        s = bytearray([1, 2])
        buf = JSArrayBuffer(s, copy_data=False)
        assert not buf.data.readonly
        buf.data[0] = 3
        assert buf.data.tolist() == [3, 2]


def test_JSArrayBuffer_init__resizable() -> None:
    # default is not resizable
    buf = JSArrayBuffer(bytes([1, 2]))
    assert not buf.resizable

    # resize() throws when not resizable
    for size in [1, 2, 3]:
        with pytest.raises(
            ByteLengthJSArrayBufferError, match="This JSArrayBuffer is not resizable"
        ) as exc_info:
            buf.resize(size)
        assert exc_info.value.byte_length == size
        assert exc_info.value.max_byte_length == 2

    # providing max_byte_length enables resizing
    buf = JSArrayBuffer(bytes([1, 2]), max_byte_length=3)
    assert buf.resizable

    # resize throws when size out of bounds
    for size in [-1, 4]:
        with pytest.raises(
            ByteLengthJSArrayBufferError,
            match="byte_length must be >= 0 and <= max_byte_length",
        ) as exc_info:
            buf.resize(size)
        assert exc_info.value.byte_length == size
        assert exc_info.value.max_byte_length == 3

    # resizing in the allowed range changes the buffer length
    buf.resize(0)
    assert buf.data.tolist() == []
    buf.resize(2)
    assert buf.data.tolist() == [0, 0]  # resizing to 0 truncated the data
    buf.resize(3)
    assert buf.data.tolist() == [0, 0, 0]


def test_JSArrayBuffer_init__caller_can_close_memoryview() -> None:
    data = memoryview(bytes([1, 2]))
    buf = JSArrayBuffer(data, copy_data=False)
    data.release()

    with pytest.raises(ValueError):
        data.tolist()

    assert buf.data.tolist() == [1, 2]


@pytest.mark.parametrize(
    "view,expected_repr",
    [
        (JSArrayBuffer(b""), "JSArrayBuffer(b'')"),
        (
            JSArrayBuffer(b"", max_byte_length=4),
            "JSArrayBuffer(b'', max_byte_length=4)",
        ),
        (JSArrayBuffer(b"", readonly=True), "JSArrayBuffer(b'', readonly=True)"),
        (
            JSArrayBuffer(memoryview(b"abcd")[:2], readonly=True),
            "JSArrayBuffer(b'ab', readonly=True)",
        ),
        (
            JSArrayBuffer(memoryview(bytearray(b"abcd"))[:2], copy_data=False),
            "JSArrayBuffer(memoryview(bytearray(b'ab')))",
        ),
    ],
)
def test_JSArrayBuffer__repr(view: JSArrayBuffer, expected_repr: str) -> None:
    match_wildcard(expected_repr, repr(view), assert_match=True)


@pytest.mark.parametrize(
    "ab_type", [JSArrayBuffer, JSSharedArrayBuffer, JSArrayBufferTransfer]
)
def test_subtype_registration(ab_type: type) -> None:
    # Serialization of ArrayBuffer types relies on them being subclasses of
    # BaseJSArrayBuffer
    assert issubclass(ab_type, BaseJSArrayBuffer)


@pytest.mark.parametrize(
    "buffer,view_ro_arg,view_ro",
    [
        (JSArrayBuffer(b"", readonly=True), True, True),
        (JSArrayBuffer(b"", readonly=True), None, True),
        (JSArrayBuffer(b"", readonly=False), None, False),
        (JSArrayBuffer(b"", readonly=False), True, True),
    ],
)
def test_JSArrayBufferView__init__readonly(
    buffer: Buffer, view_ro_arg: Literal[True] | None, view_ro: bool
) -> None:
    view = JSUint8Array(buffer, readonly=view_ro_arg)
    with view.get_buffer() as buf:
        assert buf.readonly is view_ro


def test_JSArrayBufferView__init__readonly_cannot_be_false() -> None:
    with pytest.raises(ValueError, match=r"readonly must be True or None"):
        JSUint8Array(JSArrayBuffer(b""), readonly=False)  # type: ignore[arg-type]


def test_JSArrayBufferView__init__byte_length_is_detected_when_not_resizable() -> None:
    fixed = JSUint16Array(JSArrayBuffer(b"aabbccdd"))
    assert not fixed.is_length_tracking
    assert fixed.item_length is None
    assert fixed.byte_length == 8

    fixed_exact = JSUint16Array(JSArrayBuffer(b"aabbccdd"), item_length=3)
    assert not fixed_exact.is_length_tracking
    assert fixed_exact.item_length == 3
    assert fixed_exact.byte_length == 6

    resizable = JSUint8Array(JSArrayBuffer(b"aabbccdd", resizable=True))
    assert resizable.backing_buffer.resizable
    assert resizable.is_length_tracking
    assert resizable.item_length is None
    assert resizable.byte_length == 8


def test_JSArrayBufferView__from_bytes() -> None:
    with pytest.raises(
        ItemSizeJSArrayBufferError,
        match=r"byte_offset must be a multiple of the itemsize",
    ) as err1:
        JSUint32Array.from_bytes(b"1234", byte_offset=3)
    assert err1.value.itemsize == 4
    assert err1.value.byte_offset == 3
    assert err1.value.byte_length is None

    with pytest.raises(
        ItemSizeJSArrayBufferError,
        match=r"byte_length must be a multiple of the itemsize",
    ) as err1:
        JSUint32Array.from_bytes(b"1234", byte_length=5)
    assert err1.value.itemsize == 4
    assert err1.value.byte_offset == 0
    assert err1.value.byte_length == 5

    with pytest.raises(
        BoundsJSArrayBufferError,
        match=r"backing_buffer byte length must be a multiple of the itemsize "
        r"when the view does not have an explicit byte_length",
    ) as err2:
        JSUint32Array.from_bytes(b"12345")
    assert err2.value.byte_offset == 0
    assert err2.value.byte_length is None
    assert err2.value.buffer_byte_length == 5

    with pytest.raises(
        BoundsJSArrayBufferError,
        match=r"byte_offset is not within the bounds of the backing_buffer",
    ) as err2:
        JSUint32Array.from_bytes(b"1234", byte_offset=8)
    assert err2.value.byte_offset == 8
    assert err2.value.byte_length is None
    assert err2.value.buffer_byte_length == 4

    with pytest.raises(
        BoundsJSArrayBufferError,
        match=r"byte_offset is not within the bounds of the backing_buffer",
    ) as err2:
        JSUint32Array.from_bytes(b"1234", byte_offset=4, byte_length=4)
    assert err2.value.byte_offset == 4
    assert err2.value.byte_length == 4
    assert err2.value.buffer_byte_length == 4

    view = JSUint32Array.from_bytes(b"1234")
    assert view.byte_offset == 0
    assert view.byte_length == 4

    view = JSUint32Array.from_bytes(b"1234", byte_offset=4)
    assert view.byte_offset == 4
    assert view.byte_length == 0

    view = JSUint32Array.from_bytes(b"1234" * 3, byte_offset=4, byte_length=8)
    assert view.byte_offset == 4
    assert view.byte_length == 8


def test_JSArrayBufferView__eq__length_tracking_resizable() -> None:
    view1 = JSUint8Array.from_bytes(b"1234")
    assert not (view1.is_length_tracking or view1.is_backing_buffer_resizable)

    resizable_buf = JSArrayBuffer(b"1234", max_byte_length=8)
    assert resizable_buf.resizable

    view2 = JSUint8Array.from_bytes(resizable_buf)
    assert view2.is_length_tracking and view2.is_backing_buffer_resizable

    view2 = JSUint8Array.from_bytes(resizable_buf, byte_length=4)
    assert not view2.is_length_tracking and view2.is_backing_buffer_resizable


def test_JSArrayBufferView__eq__follows_data() -> None:
    # Views are equal if their buffers contain the same data, regardless of the
    # backing buffer size. This follows the behaviour of memoryview().
    view1 = JSUint8Array(
        JSArrayBuffer(array(JSUint8Array.data_format.format, [1, 2, 3, 4])),
        item_length=2,
    )
    view2 = JSInt32Array(
        JSArrayBuffer(array(JSInt32Array.data_format.format, [0, 1, 2, 3])),
        item_offset=1,
        item_length=2,
    )
    with (
        view1.get_buffer() as data1,
        view2.get_buffer() as data2,
    ):
        assert data1.tolist() == data2.tolist()
        assert data1.tobytes() != data2.tobytes()

    assert view1 == view2


def test_JSArrayBufferView__hash() -> None:
    view_ro = JSUint8Array(
        JSArrayBuffer(
            array(JSUint8Array.data_format.format, [1, 2, 3, 4]), readonly=True
        ),
        item_length=2,
    )
    view_rw = JSUint8Array(
        JSArrayBuffer(
            array(JSUint8Array.data_format.format, [1, 2, 3, 4]), readonly=False
        ),
        item_length=2,
    )

    with view_ro.get_buffer() as buf:
        assert buf.readonly
    with view_rw.get_buffer() as buf:
        assert not buf.readonly

    assert isinstance(hash(view_ro), int)
    with pytest.raises((TypeError, ValueError)):
        hash(view_rw)


@pytest.mark.parametrize(
    "view,expected_repr",
    [
        (JSUint8Array(b""), "JSUint8Array(b'')"),
        (JSUint32Array(memoryview(b"")), "JSUint32Array(<memory at ...>)"),
        (
            JSDataView(JSArrayBuffer(b"abcd")),
            "JSDataView(JSArrayBuffer(b'abcd'))",
        ),
    ],
)
def test_JSArrayBufferView__repr(view: JSArrayBufferView, expected_repr: str) -> None:
    match_wildcard(expected_repr, repr(view), assert_match=True)


def match_wildcard(
    pattern: str,
    subject: str,
    wildcard: str = "...",
    wildcard_pattern: str = ".+",
    full_match: bool = True,
    flags: RegexFlag = RegexFlag.NOFLAG,
    assert_match: bool = False,
) -> re.Match[str] | None:
    regex = wildcard_pattern.join(re.escape(p) for p in pattern.split(wildcard))
    if full_match:
        regex = f"^{regex}$"
    result = re.search(regex, subject, flags=flags)

    if result or not assert_match:
        return result

    if wildcard not in pattern:
        assert pattern == subject
    raise AssertionError(
        f"wildcard match failed: re.search({regex!r}, {subject!r}, flags={flags!r}) "
        "is None"
    )


def test_BackportJSFloat16Array__get_buffer() -> None:
    data = bytearray(8)
    for i in range(4):
        struct.pack_into("e", data, i * 2, i)

    f16 = BackportJSFloat16Array(data)
    with f16.get_buffer() as buf:
        assert buf.tolist() == list(range(4))

        for i in range(4):
            buf[i] = i * 2 + 10

    with f16.get_buffer() as buf:
        assert buf.tolist() == [10, 12, 14, 16]

    # writes don't occur if the context block throws
    with pytest.raises(RuntimeError, match="oops"):
        with f16.get_buffer() as buf:
            buf[0] = 0
            raise RuntimeError("oops")

    with f16.get_buffer() as buf:
        assert buf[0] == 10

    # writes don't occur if the context block releases the view itself
    with f16.get_buffer() as buf:
        buf[0] = 0
        buf.release()

    with f16.get_buffer() as buf:
        assert buf[0] == 10

    # view __eq__ other float views
    f64 = JSFloat64Array(b"".join(struct.pack("d", i) for i in [10, 12, 14, 16]))
    assert f16 == f64

    # view is readonly when buffer is readonly
    with BackportJSFloat16Array(bytes(data)).get_buffer() as buf:
        assert buf.readonly

    # view is hashable when buffer is readonly
    hash(BackportJSFloat16Array(bytes(data)))


@pytest.mark.skipif(
    sys.version_info <= (3, 12),
    reason="Python 3.12+ supports half-floats in memoryview",
)
def test_BackportJSFloat16Array__not_used_in_3_12_plus() -> None:
    from v8serialize.jstypes.jsbuffers import BackportJSFloat16Array, JSFloat16Array

    assert JSFloat16Array is not BackportJSFloat16Array
    assert issubclass(BackportJSFloat16Array, JSFloat16Array)
