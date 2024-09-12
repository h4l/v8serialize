from __future__ import annotations

import math
from datetime import datetime
from typing import Callable, cast
from typing_extensions import Literal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from v8serialize.constants import (
    JS_PRIMITIVE_OBJECT_TAGS,
    JSErrorName,
    SerializationFeature,
    SerializationTag,
)
from v8serialize.decode import DefaultDecodeContext, ReadableTagStream, TagMapper
from v8serialize.encode import (
    DefaultEncodeContext,
    ObjectMapper,
    WritableTagStream,
    serialize_object_references,
)
from v8serialize.extensions import node_js_array_buffer_view_host_object_handler
from v8serialize.jstypes import JSObject, JSUndefined
from v8serialize.jstypes._normalise_property_key import normalise_property_key
from v8serialize.jstypes._v8 import V8SharedObjectReference
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsarrayproperties import JSHole, JSHoleType
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    JSArrayBuffer,
    JSArrayBufferTransfer,
    JSDataView,
    JSSharedArrayBuffer,
    JSTypedArray,
    create_view,
    get_buffer,
)
from v8serialize.jstypes.jserror import JSErrorData
from v8serialize.jstypes.jsmap import JSMap
from v8serialize.jstypes.jsprimitiveobject import JSPrimitiveObject
from v8serialize.jstypes.jsregexp import JSRegExp
from v8serialize.jstypes.jsset import JSSet
from v8serialize.jstypes.jsundefined import JSUndefinedType

from .strategies import (
    any_atomic,
    any_object,
    dense_js_arrays,
    js_array_buffer_views,
    js_array_buffers,
    js_error_data,
    js_maps,
    js_objects,
    js_regexps,
    js_sets,
    naive_timestamp_datetimes,
    name_properties,
    normal_js_array_buffers,
    sparse_js_arrays,
    v8_shared_object_references,
)

CreateContexts = Callable[[], tuple[DefaultEncodeContext, DefaultDecodeContext]]

any_theoretical_object = any_object(allow_theoretical=True)
any_theoretical_atomic = any_atomic(allow_theoretical=True)


@pytest.fixture(scope="session")
def create_rw_ctx() -> CreateContexts:
    def create_rw_ctx() -> tuple[DefaultEncodeContext, DefaultDecodeContext]:
        encode_ctx = DefaultEncodeContext(
            object_mappers=[ObjectMapper()],
            # Enable all features
            stream=WritableTagStream(features=~SerializationFeature.MaxCompatibility),
        )
        decode_ctx = DefaultDecodeContext(
            data=encode_ctx.stream.data, tag_mappers=[TagMapper()]
        )
        return encode_ctx, decode_ctx

    return create_rw_ctx


@given(st.integers(min_value=0))
def test_codec_rt_varint(n: int) -> None:
    wts = WritableTagStream()
    wts.write_varint(n)
    rts = ReadableTagStream(wts.data)
    result = rts.read_varint()
    assert n == result
    assert rts.eof


@given(st.integers())
def test_codec_rt_zigzag(n: int) -> None:
    wts = WritableTagStream()
    wts.write_zigzag(n)
    rts = ReadableTagStream(wts.data)
    result = rts.read_zigzag()
    assert n == result
    assert rts.eof


@given(st.floats())
def test_codec_rt_double(value: float) -> None:
    wts = WritableTagStream()
    wts.write_double(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_double(tag=True)
    assert value == result or math.isnan(value) and math.isnan(result)
    assert rts.eof


@given(st.text(alphabet=st.characters(codec="latin1")))
def test_codec_rt_string_onebyte(value: str) -> None:
    wts = WritableTagStream()
    wts.write_string_onebyte(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_string_onebyte(tag=True)
    assert value == result
    assert rts.eof


@given(st.text(alphabet=st.characters(codec="utf-16")), st.integers(0, 1))
def test_codec_rt_string_twobyte(value: str, offset: int) -> None:
    wts = WritableTagStream()
    # randomise the start position because we align the UTF-16 pairs to even
    wts.data.extend(b"\x00" * offset)
    wts.write_string_twobyte(value)
    rts = ReadableTagStream(wts.data, pos=offset)
    result = rts.read_string_twobyte(tag=True)
    assert value == result
    assert rts.eof

    # UTF-16 always writes pairs of bytes, so if we aligned correctly the data
    # will be an even length
    assert len(rts.data) % 2 == 0


@given(st.text(alphabet=st.characters(codec="utf-8")))
def test_codec_rt_string_utf8(value: str) -> None:
    wts = WritableTagStream()
    wts.write_string_utf8(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_string_utf8(tag=True)
    assert value == result
    assert rts.eof


@given(st.integers())
def test_codec_rt_bigint(value: int) -> None:
    wts = WritableTagStream()
    wts.write_bigint(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_bigint(tag=True)
    assert value == result
    assert rts.eof


@given(st.integers(min_value=-(2**31), max_value=2**31 - 1))
def test_codec_rt_int32(value: int) -> None:
    wts = WritableTagStream()
    wts.write_int32(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_int32(tag=True)
    assert value == result
    assert rts.eof


@given(st.integers(min_value=0, max_value=2**32 - 1))
def test_codec_rt_uint32(value: int) -> None:
    wts = WritableTagStream()
    wts.write_uint32(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_uint32(tag=True)
    assert value == result
    assert rts.eof


all_constants = st.sampled_from([JSHole, JSUndefined, None, True, False])
"""JS Constant values, including JSHole."""


@given(value=all_constants)
def test_codec_rt_constants(
    value: Literal[JSHoleType, JSUndefinedType, None, True, False],
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.encode_object(value)
    result = decode_ctx.decode_object()
    assert value == result
    assert decode_ctx.stream.eof


@given(st.one_of(st.booleans(), st.text(), st.floats(allow_nan=False), st.integers()))
def test_codec_rt_primitive_object(value: bool | str | float | int) -> None:
    wrapped = JSPrimitiveObject(value)
    wts = WritableTagStream()
    wts.write_js_primitive_object(wrapped)
    rts = ReadableTagStream(wts.data)
    assert rts.read_tag(consume=False, tag=JS_PRIMITIVE_OBJECT_TAGS)
    serialized_id, result = rts.read_js_primitive_object()
    assert result == wrapped
    assert rts.eof


@given(value=naive_timestamp_datetimes)
def test_codec_rt_naive_datetimes(value: datetime) -> None:
    wts = WritableTagStream()
    wts.write_js_date(value)
    rts = ReadableTagStream(wts.data)
    assert rts.read_tag(consume=False, tag=SerializationTag.kDate)
    result = rts.read_js_date(tag=True).object
    assert result == value
    assert rts.eof


@given(value=js_maps(keys=any_theoretical_object, values=any_theoretical_object))
def test_codec_rt_jsmap(
    value: JSMap[object, object], create_rw_ctx: CreateContexts
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_jsmap(value.items(), ctx=encode_ctx, identity=value)
    assert decode_ctx.stream.read_tag(consume=False) == SerializationTag.kBeginJSMap
    result = JSMap[object, object]()
    result.update(
        decode_ctx.stream.read_jsmap(ctx=decode_ctx, identity=result, tag=True)
    )
    assert value == result
    assert decode_ctx.stream.eof


@given(value=js_sets(elements=any_theoretical_object))
def test_codec_rt_jsset(value: set[object], create_rw_ctx: CreateContexts) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()

    encode_ctx.stream.write_jsset(value, ctx=encode_ctx)
    assert decode_ctx.stream.read_tag(consume=False) == SerializationTag.kBeginJSSet
    result = JSSet[object]()
    result |= decode_ctx.stream.read_jsset(ctx=decode_ctx, identity=result, tag=True)
    assert value == result
    assert decode_ctx.stream.eof


@given(value=js_objects(values=any_theoretical_object))
def test_codec_rt_js_object(
    value: JSObject[object], create_rw_ctx: CreateContexts
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_js_object(value.items(), ctx=encode_ctx, identity=value)
    assert decode_ctx.stream.read_tag(consume=False) == SerializationTag.kBeginJSObject
    result = JSObject[object]()
    result.update(
        decode_ctx.stream.read_js_object(ctx=decode_ctx, identity=result, tag=True)
    )
    assert value == result
    assert decode_ctx.stream.eof


def normalise_raw_js_object_key(key: int | str | float) -> int | str | float:
    if isinstance(key, float):
        return key
    return normalise_property_key(key)


js_object_raw_properties = st.lists(
    st.tuples(
        st.one_of(st.integers(), st.floats(allow_nan=False), st.text()).map(
            normalise_raw_js_object_key
        ),
        # maybe we should use something simple here as we care about keys, not
        # values here.
        any_theoretical_object,
    ),
)


@given(value=js_object_raw_properties)
def test_codec_rt_js_object_raw_properties(
    value: list[tuple[int | str | float, object]], create_rw_ctx: CreateContexts
) -> None:
    """
    (In general, not just here) the user-facing JavaScript Object API converts
    non-int keys to strings, but serialized data can contain actual float
    values. Here we verify that we can encode and decode float keys, as well as
    the normal ints and strings.
    """
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_js_object(value, ctx=encode_ctx, identity=value)
    assert decode_ctx.stream.read_tag(consume=False) == SerializationTag.kBeginJSObject
    result: list[tuple[int | float | str, object]] = []
    result.extend(
        decode_ctx.stream.read_js_object(ctx=decode_ctx, identity=result, tag=True)
    )
    assert value == result
    assert decode_ctx.stream.eof


@given(
    value=dense_js_arrays(
        elements=st.one_of(st.just(JSHole), any_theoretical_object),
        properties=js_objects(
            # Extra properties should only be names, not extra array indexes
            keys=name_properties,
            values=any_theoretical_atomic,
            max_size=10,
        ),
        max_size=10,
    )
)
def test_codec_rt_js_array_dense(
    value: JSArray[object], create_rw_ctx: CreateContexts
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()

    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_js_array_dense(
        value.array, ctx=encode_ctx, properties=value.properties.items(), identity=value
    )
    assert (
        decode_ctx.stream.read_tag(consume=False) == SerializationTag.kBeginDenseJSArray
    )
    result = JSArray[object]()
    result.update(
        decode_ctx.stream.read_js_array_dense(ctx=decode_ctx, identity=result, tag=True)
    )
    assert value == result
    assert decode_ctx.stream.eof


@given(
    value=sparse_js_arrays(
        elements=any_theoretical_object,
        properties=js_objects(
            # Extra properties should only be names, not extra array indexes
            keys=name_properties,
            values=any_theoretical_atomic,
            max_size=10,
        ),
        max_element_count=64,
    )
)
def test_codec_rt_js_array_sparse(
    value: JSArray[object], create_rw_ctx: CreateContexts
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_js_array_sparse(
        value.items(),
        ctx=encode_ctx,
        length=len(value.array),
        identity=value,
    )
    assert (
        decode_ctx.stream.read_tag(consume=False)
        == SerializationTag.kBeginSparseJSArray
    )
    result = JSArray[object]()
    length, items = decode_ctx.stream.read_js_array_sparse(
        ctx=decode_ctx, identity=result, tag=True
    )
    if length > 0:
        result[length - 1] = JSHole
    result.update(items)
    assert value == result
    assert decode_ctx.stream.eof


@given(value=js_array_buffers(allow_shared=True))
def test_codec_rt_js_array_buffer(
    value: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer,
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_js_array_buffer(value)
    assert decode_ctx.stream.read_tag(consume=False) in {
        SerializationTag.kArrayBuffer,
        SerializationTag.kResizableArrayBuffer,
        SerializationTag.kSharedArrayBuffer,
        SerializationTag.kArrayBufferTransfer,
    }
    result: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer = (
        decode_ctx.stream.read_js_array_buffer(
            array_buffer=JSArrayBuffer,
            shared_array_buffer=JSSharedArrayBuffer,
            array_buffer_transfer=JSArrayBufferTransfer,
        )
    )
    assert value == result
    assert decode_ctx.stream.eof


@given(value=js_array_buffer_views())
def test_codec_rt_js_array_buffer_view(
    value: JSTypedArray | JSDataView,
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_js_array_buffer_view(value)
    assert (
        decode_ctx.stream.read_tag(consume=False) == SerializationTag.kArrayBufferView
    )
    result: JSTypedArray | JSDataView = decode_ctx.stream.read_js_array_buffer_view(
        backing_buffer=value.backing_buffer, array_buffer_view=create_view, tag=True
    )
    assert value == result
    assert decode_ctx.stream.eof


def test_codec_rt_object_identity__simple(
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx = DefaultEncodeContext(
        # Change test-default mappers to include serialize_object_references
        object_mappers=[serialize_object_references, ObjectMapper()]
    )
    decode_ctx = DefaultDecodeContext(
        data=encode_ctx.stream.data, tag_mappers=[TagMapper()]
    )

    set1 = {1, 2}
    set2 = {1, 2}
    value = {"a": set1, "b": set2, "c": set1}
    encode_ctx.encode_object(value)

    result = dict[object, object]()
    result.update(
        decode_ctx.stream.read_jsmap(ctx=decode_ctx, identity=result, tag=True)
    )

    assert value == result
    assert result["a"] is result["c"]
    assert result["a"] is not result["b"]


@given(value=any_object(allow_theoretical=True))
def test_codec_rt_object(
    value: object,
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.encode_object(value)

    result = decode_ctx.decode_object()
    assert value == result
    assert decode_ctx.stream.eof


python_binary_types = st.builds(
    lambda binary_type, data: binary_type(data),
    st.sampled_from([bytes, bytearray, memoryview]),
    st.binary(),
)


@given(value=python_binary_types)
def test_codec_rt_object__encodes_python_binary_types_as_array_buffers(
    value: bytes | bytearray | memoryview,
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.encode_object(value)

    result = decode_ctx.decode_object()

    assert isinstance(result, JSArrayBuffer)
    assert bytes(get_buffer(result.data)) == bytes(value)
    assert decode_ctx.stream.eof


@given(
    value=js_array_buffer_views(
        view_formats=st.sampled_from(
            sorted(
                set(ArrayBufferViewStructFormat)
                # The NodeJS format doesn't support Float16Array
                - {ArrayBufferViewStructFormat.Float16Array},
                key=lambda s: s.view_tag,
            )
        ),
        backing_buffers=normal_js_array_buffers,
    )
)
def test_codec_rt_nodejs_array_buffer_host_object(
    value: JSTypedArray | JSDataView,
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.stream.write_host_object(
        value, serializer=node_js_array_buffer_view_host_object_handler
    )
    assert decode_ctx.stream.read_tag(consume=False) == SerializationTag.kHostObject
    result: JSTypedArray | JSDataView = decode_ctx.stream.read_host_object(
        deserializer=node_js_array_buffer_view_host_object_handler, tag=True
    )
    # Node's view serialization intentionally only shares the portion of the
    # buffer that the view references, so the rest of the initial buffer is not
    # present in the result.
    assert result.byte_offset == 0
    assert not result.is_length_tracking
    assert result.byte_length == value.byte_length
    assert type(result) is type(value)
    assert result.data_format == value.data_format
    assert result.view_tag == value.view_tag
    assert result == value
    assert decode_ctx.stream.eof


@given(value=js_regexps(allow_linear=True))
def test_codec_rt_js_regexp(
    value: JSRegExp,
    create_rw_ctx: CreateContexts,
) -> None:
    encode_ctx, decode_ctx = create_rw_ctx()
    encode_ctx.encode_object(value)

    assert decode_ctx.stream.read_tag(consume=False) == SerializationTag.kRegExp
    result = decode_ctx.decode_object()
    assert value == result
    assert decode_ctx.stream.eof


# Test with JSErrorData here, as its a pure representation of the serializable
# data, and supports equality. In contrast, JSError is a Python Exception, and
# Exception uses identity for equality.
@given(
    value=st.recursive(
        js_error_data(names=st.sampled_from(JSErrorName) | st.text()),
        lambda children: js_error_data(
            names=st.sampled_from(JSErrorName) | st.text(), causes=children
        ),
    )
)
def test_codec_rt_js_error(value: JSErrorData) -> None:
    encode_ctx = DefaultEncodeContext(object_mappers=[ObjectMapper()])
    decode_ctx = DefaultDecodeContext(
        data=encode_ctx.stream.data,
        # Change default error type to deserialize as JSErrorData
        tag_mappers=[TagMapper(js_error_builder=JSErrorData.builder)],
    )

    encode_ctx.encode_object(value)

    assert decode_ctx.stream.read_tag(consume=False) == SerializationTag.kError
    result = decode_ctx.decode_object()
    assert decode_ctx.stream.eof
    assert isinstance(result, JSErrorData)

    # Unknown error names become "Error" after loading. Normalise result name
    # back to initial values to verify overall equality.
    err_before: JSErrorData | None = value
    err_after: JSErrorData | None = result

    while err_before and err_after:
        if err_before.name not in JSErrorName:
            assert err_after.name == JSErrorName.Error
            err_after.name = err_before.name

        err_before = cast("JSErrorData | None", err_before.cause)
        err_after = cast("JSErrorData | None", err_after.cause)
        assert (err_before and err_after) or not (err_before or err_after)

    assert value == result


@given(value=v8_shared_object_references)
def test_codec_rt_v8_shared_object_reference(value: V8SharedObjectReference) -> None:
    wts = WritableTagStream()
    wts.write_v8_shared_object_reference(value)
    rts = ReadableTagStream(wts.data)
    assert rts.read_tag(consume=False, tag=SerializationTag.kSharedObject)
    result = rts.read_v8_shared_object_reference(tag=True).object
    assert result == value
    assert rts.eof
