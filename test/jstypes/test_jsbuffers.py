import math
from dataclasses import FrozenInstanceError

import pytest

from v8serialize.constants import ArrayBufferViewTag
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    BaseJSArrayBuffer,
    ByteLengthJSArrayBufferError,
    JSArrayBuffer,
    JSArrayBufferTransfer,
    JSDataView,
    JSInt8Array,
    JSSharedArrayBuffer,
)


def test_ArrayBufferViewStructFormat() -> None:
    assert ArrayBufferViewStructFormat.Int16Array.struct_format == "h"
    assert ArrayBufferViewStructFormat.Int16Array.itemsize == 2

    sf = ArrayBufferViewStructFormat(ArrayBufferViewTag.kBigUint64Array)
    assert sf.view_tag is ArrayBufferViewTag.kBigUint64Array
    assert sf.itemsize == 8

    hash(ArrayBufferViewStructFormat.Int8Array)

    with pytest.raises(FrozenInstanceError):
        ArrayBufferViewStructFormat.Int8Array.struct_format = "c"


def test_int8array() -> None:
    buffer = JSArrayBuffer(bytearray(16))
    view = JSInt8Array(buffer)

    assert view.element_type == int
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
    assert view.view_format is ArrayBufferViewStructFormat.DataView

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
    "ab_type", [JSArrayBuffer, JSSharedArrayBuffer, JSArrayBufferTransfer]
)
def test_subtype_registration(ab_type: type) -> None:
    # Serialization of ArrayBuffer types relies on them being subclasses of
    # BaseJSArrayBuffer
    assert issubclass(ab_type, BaseJSArrayBuffer)
