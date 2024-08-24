import math
from datetime import datetime
from typing import Optional, TypeVar, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from v8serialize._values import SharedArrayBufferId, TransferId
from v8serialize.constants import (
    JS_CONSTANT_TAGS,
    JS_PRIMITIVE_OBJECT_TAGS,
    MAX_ARRAY_LENGTH,
    ConstantTags,
    JSErrorName,
    JSRegExpFlag,
    SerializationTag,
)
from v8serialize.decode import ReadableTagStream, TagMapper
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
from v8serialize.jstypes.jsarrayproperties import JSHole
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    JSArrayBuffer,
    JSArrayBufferTransfer,
    JSDataView,
    JSSharedArrayBuffer,
    JSTypedArray,
    ViewFormat,
    create_view,
)
from v8serialize.jstypes.jserror import JSError, JSErrorData
from v8serialize.jstypes.jsprimitiveobject import JSPrimitiveObject
from v8serialize.jstypes.jsregexp import JSRegExp

T = TypeVar("T")


@pytest.fixture(scope="session")
def object_mapper() -> ObjectMapper:
    return ObjectMapper()


@pytest.fixture(scope="session")
def tag_mapper() -> TagMapper:
    return TagMapper()


any_int_or_text = st.one_of(st.integers(), st.text())
uint32s = st.integers(min_value=0, max_value=2**32 - 1)

name_properties = st.text().filter(
    lambda name: isinstance(normalise_property_key(name), str)
)
"""Generate JavaScript object property strings which aren't array indexes."""


def js_objects(
    values: st.SearchStrategy[T],
    *,
    keys: st.SearchStrategy[str | int] = any_int_or_text,
    min_size: int = 0,
    max_size: int | None = None,
) -> st.SearchStrategy[JSObject[T]]:
    """Generates `JSObject` instances with keys drawn from `keys` argument
    and values drawn from `values` argument.

    Behaves like the default `hypothesis.strategies.lists`.
    """
    if (min_size < 0) if max_size is None else not (0 <= min_size <= max_size):
        raise ValueError(
            f"0 <= min_size <= max_size does not hold: {min_size=}, {max_size=}"
        )

    return st.lists(
        st.tuples(keys, values),
        min_size=min_size,
        max_size=max_size,
        # Ensure generated int/str keys are not aliases of each other, which
        # would allow the obj to be less than min_size.
        unique_by=lambda kv: normalise_property_key(kv[0]),
    ).map(JSObject)


def dense_js_arrays(
    elements: st.SearchStrategy[T],
    *,
    min_size: int = 0,
    max_size: Optional[int] = None,
    properties: st.SearchStrategy[JSObject[T]] | None = None,
) -> st.SearchStrategy[JSArray[T]]:

    if (min_size < 0) if max_size is None else not (0 <= min_size <= max_size):
        raise ValueError(
            f"0 <= min_size <= max_size does not hold: {min_size=}, {max_size=}"
        )

    def create_array(content: tuple[list[T], JSObject[T] | None]) -> JSArray[T]:
        elements, properties = content
        js_array = JSArray[T]()
        js_array.array.extend(elements)
        if properties is not None:
            js_array.update(properties)
        return js_array

    return st.tuples(
        st.lists(
            elements,
            min_size=min_size,
            max_size=max_size,
        ),
        st.none() if properties is None else properties,
    ).map(create_array)


def sparse_js_arrays(
    elements: st.SearchStrategy[T],
    *,
    min_element_count: int = 0,
    max_element_count: int = 512,
    max_size: int = MAX_ARRAY_LENGTH,
    properties: st.SearchStrategy[JSObject[T]] | None = None,
) -> st.SearchStrategy[JSArray[T]]:

    if (
        max_size is not None
        and max_element_count is not None
        and max_size < max_element_count
    ):
        raise ValueError("max_size must be >= max_element_count when both are set")
    if max_size is not None and not (0 <= max_size <= MAX_ARRAY_LENGTH):
        raise ValueError(f"max_size must be >=0 and <= {MAX_ARRAY_LENGTH}")

    def create_array(
        content: tuple[st.DataObject, list[T], JSObject[T] | None]
    ) -> JSArray[T]:
        data, values, properties = content
        length = data.draw(st.integers(min_value=len(values), max_value=max_size))
        possible_indexes = st.lists(
            st.integers(min_value=0, max_value=max(0, length - 1)),
            unique=True,
            min_size=len(values),
            max_size=len(values),
        )

        indexes = data.draw(possible_indexes)
        items = zip(indexes, values)

        js_array = JSArray[T]()
        if length > 0:
            js_array[length - 1] = cast(T, JSHole)
        js_array.update(items)
        assert js_array.array.elements_used == len(values)
        if properties:
            js_array.update(properties.items())
        return js_array

    return st.tuples(
        st.data(),
        st.lists(elements, min_size=min_element_count, max_size=max_element_count),
        properties if properties is not None else st.none(),
    ).map(create_array)


fixed_js_array_buffers = st.binary().map(lambda data: JSArrayBuffer(data))

resizable_js_array_buffers = st.builds(
    lambda data, headroom_byte_length: JSArrayBuffer(
        data, max_byte_length=len(data) + headroom_byte_length, resizable=True
    ),
    st.binary(),
    st.integers(min_value=0),
)

normal_js_array_buffers = st.one_of(fixed_js_array_buffers, resizable_js_array_buffers)

shared_array_buffers = uint32s.map(
    lambda value: JSSharedArrayBuffer(SharedArrayBufferId(value))
)
array_buffer_transfers = uint32s.map(
    lambda value: JSArrayBufferTransfer(TransferId(value))
)

js_array_buffers = st.one_of(
    fixed_js_array_buffers,
    resizable_js_array_buffers,
    shared_array_buffers,
    array_buffer_transfers,
)


def js_array_buffer_views(
    backing_buffers: st.SearchStrategy[
        JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer
    ] = js_array_buffers,
    view_formats: st.SearchStrategy[ViewFormat] | None = None,
) -> st.SearchStrategy[JSTypedArray | JSDataView]:
    if view_formats is None:
        view_formats = st.sampled_from(ArrayBufferViewStructFormat)

    def create(
        data: st.DataObject,
        view_format: ViewFormat,
        backing_buffer: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer,
    ) -> JSTypedArray | JSDataView:

        if isinstance(backing_buffer, JSArrayBuffer):
            buffer_byte_length = len(backing_buffer.data)
        else:
            # make up a length — the buffer is not connected
            buffer_byte_length = data.draw(
                st.integers(min_value=0, max_value=2**32 - 1)
            )

        byte_offset = data.draw(st.integers(min_value=0, max_value=buffer_byte_length))
        item_length = data.draw(
            st.integers(
                min_value=0,
                max_value=(buffer_byte_length - byte_offset) // view_format.itemsize,
            )
        )
        byte_length = item_length * view_format.itemsize

        return view_format.view_type(
            backing_buffer, byte_offset=byte_offset, byte_length=byte_length
        )

    return st.builds(
        create, data=st.data(), view_format=view_formats, backing_buffer=backing_buffers
    )


def js_errors(
    names: st.SearchStrategy[str] | None = None,
    messages: st.SearchStrategy[str | None] | None = None,
    stacks: st.SearchStrategy[str | None] | None = None,
    causes: st.SearchStrategy[object] | None = None,
) -> st.SearchStrategy[JSError]:
    return st.builds(
        JSError,
        name=st.sampled_from(JSErrorName) if names is None else names,
        message=st.text() | st.none() if messages is None else messages,
        stack=st.text() | st.none() if stacks is None else stacks,
        cause=st.none() if causes is None else causes,
    )


def js_error_data(
    names: st.SearchStrategy[str] | None = None,
    messages: st.SearchStrategy[str | None] | None = None,
    stacks: st.SearchStrategy[str | None] | None = None,
    causes: st.SearchStrategy[object] | None = None,
) -> st.SearchStrategy[JSErrorData]:
    return st.builds(
        JSErrorData,
        name=st.sampled_from(JSErrorName) if names is None else names,
        message=st.text() | st.none() if messages is None else messages,
        stack=st.text() | st.none() if stacks is None else stacks,
        cause=st.none() if causes is None else causes,
    )


js_regexp_flags = st.builds(
    JSRegExpFlag, st.integers(min_value=0, max_value=int(JSRegExpFlag(0xFFF).canonical))
)
js_regexps = st.builds(JSRegExp, source=st.text(), flags=js_regexp_flags)


naive_timestamp_datetimes = st.datetimes(min_value=datetime(1, 1, 2)).map(
    # Truncate timestamp precision to nearest 0.25 milliseconds to avoid lossy
    # float operations breaking equality. We don't really care about testing the
    # precision of float operations, just that the values are encoded and
    # decoded as provided.
    lambda dt: datetime.fromtimestamp(round(dt.timestamp() * 4000 + 1) / 4000)
)
"""datetime values rounded slightly by passing through timestamp() representation.

These datetime values can be represented exactly as their timestamp value.
The datetime code does some rounding when converting a timestamp to a datetime,
so if we start form an arbitrary datetime, the fromtimestamp result can be
slightly different, which breaks round-trip equality.
"""

v8_shared_object_references = st.builds(
    V8SharedObjectReference, shared_value_id=uint32s
)


any_atomic = st.one_of(
    st.integers(),
    # NaN breaks equality when nested inside objects. We test with nan in
    # test_codec_rt_double.
    st.floats(allow_nan=False),
    st.text(),
    st.just(JSUndefined),
    st.just(None),
    st.just(True),
    st.just(False),
    # FIXME: non-hashable objects are a problem for maps/sets
    # js_array_buffers,
    js_regexps,
    # Use naive datetimes for general tests to avoid needing to normalise tz.
    # (Can't serialize tz, so aware datetimes come back as naive or a fixed tz;
    # epoch timestamp always matches though.)
    naive_timestamp_datetimes,
    v8_shared_object_references,
)


# https://hypothesis.works/articles/recursive-data/
any_object = st.recursive(
    any_atomic,
    lambda children: st.one_of(
        st.dictionaries(
            keys=any_atomic,
            values=children,
        ),
        js_objects(values=children),
        dense_js_arrays(
            elements=children,
            properties=js_objects(
                # Extra properties should only be names, not extra array indexes
                keys=name_properties,
                values=children,
                max_size=10,
            ),
            max_size=10,
        ),
        sparse_js_arrays(
            elements=children,
            max_element_count=32,
            properties=js_objects(
                # Extra properties should only be names, not extra array indexes
                keys=name_properties,
                values=children,
                max_size=10,
            ),
        ),
        st.sets(elements=any_atomic),
        js_errors(causes=children),
    ),
    max_leaves=3,  # TODO: tune this, perhaps increase in CI
)


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
    result = rts.read_double()
    assert value == result or math.isnan(value) and math.isnan(result)
    assert rts.eof


@given(st.text(alphabet=st.characters(codec="latin1")))
def test_codec_rt_string_onebyte(value: str) -> None:
    wts = WritableTagStream()
    wts.write_string_onebyte(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_string_onebyte()
    assert value == result
    assert rts.eof


@given(st.text(alphabet=st.characters(codec="utf-16")), st.integers(0, 1))
def test_codec_rt_string_twobyte(value: str, offset: int) -> None:
    wts = WritableTagStream()
    # randomise the start position because we align the UTF-16 pairs to even
    wts.data.extend(b"\x00" * offset)
    wts.write_string_twobyte(value)
    rts = ReadableTagStream(wts.data, pos=offset)
    result = rts.read_string_twobyte()
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
    result = rts.read_string_utf8()
    assert value == result
    assert rts.eof


@given(st.integers())
def test_codec_rt_bigint(value: int) -> None:
    wts = WritableTagStream()
    wts.write_bigint(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_bigint()
    assert value == result
    assert rts.eof


@given(st.integers(min_value=-(2**31), max_value=2**31 - 1))
def test_codec_rt_int32(value: int) -> None:
    wts = WritableTagStream()
    wts.write_int32(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_int32()
    assert value == result
    assert rts.eof


@given(st.integers(min_value=0, max_value=2**32 - 1))
def test_codec_rt_uint32(value: int) -> None:
    wts = WritableTagStream()
    wts.write_uint32(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_uint32()
    assert value == result
    assert rts.eof


@given(st.sampled_from(sorted(JS_CONSTANT_TAGS.allowed_tags)))
def test_codec_rt_constants(value: ConstantTags) -> None:
    wts = WritableTagStream()
    wts.write_constant(value)
    rts = ReadableTagStream(wts.data)
    result = rts.read_constant(value)
    assert value == result
    assert rts.eof


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
    result = rts.read_js_date().object
    assert result == value
    assert rts.eof


@given(value=st.dictionaries(keys=any_atomic, values=any_object))
def test_codec_rt_jsmap(
    value: dict[object, object],
    tag_mapper: TagMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([ObjectMapper()])
    encode_ctx.stream.write_jsmap(value.items(), ctx=encode_ctx, identity=value)
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kBeginJSMap
    result = dict[object, object]()
    result.update(rts.read_jsmap(tag_mapper, identity=result))
    assert value == result
    assert rts.eof


@given(value=st.sets(elements=any_atomic))
def test_codec_rt_jsset(
    value: set[object], object_mapper: ObjectMapper, tag_mapper: TagMapper
) -> None:
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_jsset(value, ctx=encode_ctx)
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kBeginJSSet
    result = set[object]()
    result.update(rts.read_jsset(tag_mapper, identity=result))
    assert value == result
    assert rts.eof


@given(value=js_objects(values=any_object))
def test_codec_rt_js_object(
    value: JSObject[object],
    tag_mapper: TagMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([ObjectMapper()])
    encode_ctx.stream.write_js_object(value.items(), ctx=encode_ctx, identity=value)
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kBeginJSObject
    result = JSObject[object]()
    result.update(rts.read_js_object(tag_mapper, identity=result))
    assert value == result
    assert rts.eof


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
        any_object,
    ),
)


@given(value=js_object_raw_properties)
def test_codec_rt_js_object_raw_properties(
    value: list[tuple[int | str | float, object]],
    tag_mapper: TagMapper,
) -> None:
    """
    (In general, not just here) the user-facing JavaScript Object API converts
    non-int keys to strings, but serialized data can contain actual float
    values. Here we verify that we can encode and decode float keys, as well as
    the normal ints and strings.
    """
    encode_ctx = DefaultEncodeContext([ObjectMapper()])
    encode_ctx.stream.write_js_object(value, ctx=encode_ctx, identity=value)
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kBeginJSObject
    result: list[tuple[int | float | str, object]] = []
    result.extend(rts.read_js_object(tag_mapper, identity=result))
    assert value == result
    assert rts.eof


@given(
    value=dense_js_arrays(
        elements=st.one_of(st.just(JSHole), any_object),
        properties=js_objects(
            # Extra properties should only be names, not extra array indexes
            keys=name_properties,
            values=any_atomic,
            max_size=10,
        ),
        max_size=10,
    )
)
def test_codec_rt_js_array_dense(
    value: JSArray[object],
    tag_mapper: TagMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([ObjectMapper()])
    encode_ctx.stream.write_js_array_dense(
        value.array, ctx=encode_ctx, properties=value.properties.items(), identity=value
    )
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kBeginDenseJSArray
    result = JSArray[object]()
    result.update(rts.read_js_array_dense(tag_mapper, identity=result))
    assert value == result
    assert rts.eof


@given(
    value=sparse_js_arrays(
        elements=any_object,
        properties=js_objects(
            # Extra properties should only be names, not extra array indexes
            keys=name_properties,
            values=any_atomic,
            max_size=10,
        ),
        max_element_count=64,
    )
)
def test_codec_rt_js_array_sparse(
    value: JSArray[object],
    tag_mapper: TagMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([ObjectMapper()])
    encode_ctx.stream.write_js_array_sparse(
        value.items(),
        ctx=encode_ctx,
        length=len(value.array),
        identity=value,
    )
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kBeginSparseJSArray
    result = JSArray[object]()
    length, items = rts.read_js_array_sparse(tag_mapper, identity=result)
    if length > 0:
        result[length - 1] = JSHole
    result.update(items)
    assert value == result
    assert rts.eof


@given(value=js_array_buffers)
def test_codec_rt_js_array_buffer(
    value: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer,
    object_mapper: ObjectMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_js_array_buffer(value)
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) in {
        SerializationTag.kArrayBuffer,
        SerializationTag.kResizableArrayBuffer,
        SerializationTag.kSharedArrayBuffer,
        SerializationTag.kArrayBufferTransfer,
    }
    result: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer = (
        rts.read_js_array_buffer(
            array_buffer=JSArrayBuffer,
            shared_array_buffer=JSSharedArrayBuffer,
            array_buffer_transfer=JSArrayBufferTransfer,
        )
    )
    assert value == result
    assert rts.eof


@given(value=js_array_buffer_views())
def test_codec_rt_js_array_buffer_view(
    value: JSTypedArray | JSDataView,
    object_mapper: ObjectMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_js_array_buffer_view(value)
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kArrayBufferView
    result: JSTypedArray | JSDataView = rts.read_js_array_buffer_view(
        backing_buffer=value.backing_buffer, array_buffer_view=create_view
    )
    assert value == result
    assert rts.eof


def test_codec_rt_object_identity__simple(
    object_mapper: ObjectMapper, tag_mapper: TagMapper
) -> None:
    encode_ctx = DefaultEncodeContext(
        object_mappers=[serialize_object_references, object_mapper]
    )
    set1 = {1, 2}
    set2 = {1, 2}
    value = {"a": set1, "b": set2, "c": set1}
    encode_ctx.stream.write_object(value, ctx=encode_ctx)

    rts = ReadableTagStream(encode_ctx.stream.data)
    result = dict[object, object]()
    result.update(rts.read_jsmap(tag_mapper, identity=result))

    assert value == result
    assert value["a"] is value["c"]
    assert value["a"] is not value["b"]


@given(value=any_object)
def test_codec_rt_object(
    value: object, object_mapper: ObjectMapper, tag_mapper: TagMapper
) -> None:
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_object(value, ctx=encode_ctx)

    rts = ReadableTagStream(encode_ctx.stream.data)
    result = rts.read_object(tag_mapper)
    assert value == result
    assert rts.eof


python_binary_types = st.builds(
    lambda binary_type, data: binary_type(data),
    st.sampled_from([bytes, bytearray, memoryview]),
    st.binary(),
)


@given(value=python_binary_types)
def test_codec_rt_object__encodes_python_binary_types_as_array_buffers(
    value: bytes | bytearray | memoryview,
    object_mapper: ObjectMapper,
    tag_mapper: TagMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_object(value, ctx=encode_ctx)

    rts = ReadableTagStream(encode_ctx.stream.data)
    result = rts.read_object(tag_mapper)

    assert isinstance(result, JSArrayBuffer)
    assert bytes(result.data) == bytes(result)
    assert rts.eof


@given(
    value=js_array_buffer_views(
        view_formats=st.sampled_from(
            sorted(
                set(ArrayBufferViewStructFormat)
                - {ArrayBufferViewStructFormat.Float16Array},
                key=lambda s: s.view_tag,
            )
        ),
        backing_buffers=normal_js_array_buffers,
    )
)
def test_codec_rt_nodejs_array_buffer_host_object(
    value: JSTypedArray | JSDataView,
    object_mapper: ObjectMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_host_object(
        value, serializer=node_js_array_buffer_view_host_object_handler
    )
    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kHostObject
    result: JSTypedArray | JSDataView = rts.read_host_object(
        deserializer=node_js_array_buffer_view_host_object_handler
    )
    # Node's view serialization intentionally only shares the portion of the
    # buffer that the view references, so the rest of the initial buffer is not
    # present in the result.
    assert result.byte_offset == 0
    assert result.is_length_tracking
    assert result.byte_length is None
    assert type(result) is type(value)
    assert result.view_format == value.view_format
    assert result.view_tag == value.view_tag
    assert bytes(result.get_buffer_as_memoryview()) == bytes(
        value.get_buffer_as_memoryview()
    )
    assert rts.eof


@given(value=js_regexps)
def test_codec_rt_js_regexp(
    value: JSRegExp, object_mapper: ObjectMapper, tag_mapper: TagMapper
) -> None:
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_object(value, ctx=encode_ctx)

    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kRegExp
    result = rts.read_object(tag_mapper)
    assert value == result
    assert rts.eof


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
def test_codec_rt_js_error(value: JSErrorData, object_mapper: ObjectMapper) -> None:
    tag_mapper = TagMapper(js_error_type=JSErrorData)
    encode_ctx = DefaultEncodeContext([object_mapper])
    encode_ctx.stream.write_object(value, ctx=encode_ctx)

    rts = ReadableTagStream(encode_ctx.stream.data)
    assert rts.read_tag(consume=False) == SerializationTag.kError
    result = rts.read_object(tag_mapper)
    assert rts.eof
    assert isinstance(result, JSErrorData)

    # Unknown error names become "Error" after loading. Normalise result name
    # back to initial values to verify overall equality.
    err_before: JSErrorData | None = value
    err_after: JSErrorData | None = result

    while err_before and err_after:
        if err_before.name not in JSErrorName:
            assert err_after.name == JSErrorName.Error
            err_after.name = err_before.name

        err_before = cast(JSErrorData | None, err_before.cause)
        err_after = cast(JSErrorData | None, err_after.cause)
        assert (err_before and err_after) or not (err_before or err_after)

    assert value == result


@given(value=v8_shared_object_references)
def test_codec_rt_v8_shared_object_reference(value: V8SharedObjectReference) -> None:
    wts = WritableTagStream()
    wts.write_v8_shared_object_reference(value)
    rts = ReadableTagStream(wts.data)
    assert rts.read_tag(consume=False, tag=SerializationTag.kSharedObject)
    result = rts.read_v8_shared_object_reference().object
    assert result == value
    assert rts.eof
