from __future__ import annotations

from array import array
from base64 import b64decode
from typing import TYPE_CHECKING

import pytest

from v8serialize.constants import ArrayBufferViewTag
from v8serialize.decode import ReadableTagStream
from v8serialize.encode import WritableTagStream
from v8serialize.extensions import (
    NodeBufferFormat,
    NodeJsArrayBufferViewHostObjectHandler,
)
from v8serialize.jstypes.jsbuffers import (
    JSArrayBuffer,
    JSTypedArray,
    JSUint8Array,
    JSUint32Array,
)

if TYPE_CHECKING:
    from typing_extensions import Buffer


def test_NodeBufferFormat() -> None:
    assert NodeBufferFormat(0) is NodeBufferFormat.Int8Array

    assert not NodeBufferFormat.supports(ArrayBufferViewTag.kFloat16Array)
    assert NodeBufferFormat.supports(ArrayBufferViewTag.kDataView)
    assert NodeBufferFormat(ArrayBufferViewTag.kDataView) is NodeBufferFormat.DataView


@pytest.mark.parametrize(
    "serialized,node_type,py_type,data",
    [
        (
            "/w9cBgj/////Fc1bBw==",
            NodeBufferFormat.Uint32Array,
            JSUint32Array,
            array("I", [2**32 - 1, 123456789]),
        ),
        (
            "/w9cCgQBAgME",
            NodeBufferFormat.FastBuffer,
            JSUint8Array,
            array("B", [1, 2, 3, 4]),
        ),
    ],
)
def test_NodeJsArrayBufferViewHostObjectHandler_deserialize_host_object(
    serialized: str,
    node_type: NodeBufferFormat,
    py_type: type[JSTypedArray],
    data: Buffer,
) -> None:
    stream = ReadableTagStream(b64decode(serialized))

    assert stream.read_header() == 15
    assert NodeBufferFormat(stream.data[3]) is node_type
    view = stream.read_host_object(
        deserializer=NodeJsArrayBufferViewHostObjectHandler(), tag=True
    )
    assert stream.eof

    assert view == py_type(JSArrayBuffer(data))


@pytest.mark.parametrize(
    "node_type,py_type,data",
    [
        (
            NodeBufferFormat.Uint32Array,
            JSUint32Array,
            array("I", [2**32 - 1, 123456789]),
        ),
        (
            # Note that we write Uint8Arrays as Uint8Array, not FastBuffer. We
            # don't currently have type to map to FastBuffer.
            NodeBufferFormat.Uint8Array,
            JSUint8Array,
            array("B", [1, 2, 3, 4]),
        ),
    ],
)
def test_NodeJsArrayBufferViewHostObjectHandler_serialize_host_object(
    node_type: NodeBufferFormat,
    py_type: type[JSTypedArray],
    data: Buffer,
) -> None:
    value = py_type(JSArrayBuffer(data))

    stream = WritableTagStream()
    stream.write_header()
    stream.write_host_object(value, serializer=NodeJsArrayBufferViewHostObjectHandler())

    rts = ReadableTagStream(stream.data)
    rts.read_header()
    result = rts.read_host_object(
        tag=True, deserializer=NodeJsArrayBufferViewHostObjectHandler()
    )
    assert rts.eof
    assert NodeBufferFormat(rts.data[3]) == node_type
    assert result == value
