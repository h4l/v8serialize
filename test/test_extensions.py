from __future__ import annotations

from array import array
from base64 import b64decode
from typing import TYPE_CHECKING, Sequence

import pytest

from v8serialize._errors import (
    FeatureNotEnabledEncodeV8SerializeError,
    UnhandledValueEncodeV8SerializeError,
)
from v8serialize.constants import ArrayBufferViewTag, SerializationFeature
from v8serialize.decode import ReadableTagStream
from v8serialize.encode import DefaultEncodeContext, WritableTagStream
from v8serialize.extensions import (
    NodeBufferFormat,
    NodeJsArrayBufferViewHostObjectHandler,
    serialize_js_array_buffer_views_as_nodejs_host_object,
)
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    JSArrayBuffer,
    JSFloat16Array,
    JSTypedArray,
    JSUint8Array,
    JSUint32Array,
)

if TYPE_CHECKING:
    from typing_extensions import Buffer


class TestNodeBufferFormat:
    def test_format_lookup_by_code(self) -> None:
        assert NodeBufferFormat(0) is NodeBufferFormat.Int8Array

    def test_supports(self) -> None:
        assert NodeBufferFormat.supports(ArrayBufferViewTag.kDataView)
        assert not NodeBufferFormat.supports(-1)  # type: ignore[arg-type]

    def test_all_v8_view_formats_have_corresponding_node_format(self) -> None:
        for format in ArrayBufferViewStructFormat:
            assert NodeBufferFormat(format.view_tag).view_format is format


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


@pytest.fixture
def float_values() -> Sequence[float]:
    return [-1.0, 2.0]


@pytest.fixture
def float16_array(float_values: Sequence[float]) -> JSFloat16Array:
    float16_array = JSFloat16Array(bytearray(len(float_values) * 2))

    with float16_array.get_buffer() as values:
        for i, v in enumerate(float_values):
            values[i] = v

    return float16_array


def test_NodeJsArrayBufferViewHostObjectHandler_requires_feature_to_serialize_Float16Array(  # noqa: E501
    float_values: Sequence[float], float16_array: JSFloat16Array
) -> None:
    nodejs_handler = NodeJsArrayBufferViewHostObjectHandler()
    wts_without_support = WritableTagStream(
        features=SerializationFeature.MaxCompatibility
    )
    assert SerializationFeature.Float16Array not in wts_without_support.features
    wts_with_support = WritableTagStream(
        features=~SerializationFeature.MaxCompatibility
    )
    assert SerializationFeature.Float16Array in wts_with_support.features

    wts_without_support.write_header()
    with pytest.raises(
        FeatureNotEnabledEncodeV8SerializeError,
        match=r"Cannot write Float16Array when the Float16Array "
        r"SerializationFeature is not enabled",
    ):
        wts_without_support.write_host_object(float16_array, serializer=nodejs_handler)

    wts_with_support.write_header()
    wts_with_support.write_host_object(float16_array, serializer=nodejs_handler)

    rts = ReadableTagStream(wts_with_support.data)
    rts.read_header()
    read_float16_array = rts.read_host_object(tag=True, deserializer=nodejs_handler)
    assert rts.eof

    assert isinstance(read_float16_array, JSFloat16Array)
    with read_float16_array.get_buffer() as values:
        assert list(values) == float_values


class Test_serialize_js_array_buffer_views_as_nodejs_host_object:
    @pytest.mark.parametrize(
        "is_encodable,value,enabled_features",
        [
            (True, JSFloat16Array(b"\x00\x40"), ~SerializationFeature.MaxCompatibility),
            (False, JSFloat16Array(b"\x00\x40"), SerializationFeature.MaxCompatibility),
            (True, JSUint8Array(b"\x00\xff"), SerializationFeature.MaxCompatibility),
            (False, "foobar", SerializationFeature.MaxCompatibility),
        ],
    )
    def test_encodes_supported_objects_and_passes_on_unsupported_objects(
        self, is_encodable: bool, value: object, enabled_features: SerializationFeature
    ) -> None:
        wts = WritableTagStream(features=enabled_features)
        encode_context = DefaultEncodeContext(
            encode_steps=[serialize_js_array_buffer_views_as_nodejs_host_object],
            stream=wts,
        )

        if is_encodable:
            encode_context.encode_object(value)

            result = ReadableTagStream(wts.data).read_host_object(
                deserializer=NodeJsArrayBufferViewHostObjectHandler(), tag=True
            )
            assert result == value
            assert len(result.get_buffer_as_memoryview()) > 0
        else:
            with pytest.raises(UnhandledValueEncodeV8SerializeError):
                encode_context.encode_object(value)
            assert wts.pos == 0
