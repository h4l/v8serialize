from dataclasses import FrozenInstanceError

import pytest

from v8serialize.constants import ArrayBufferViewTag
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    JSArrayBuffer,
    JSInt8Array,
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
