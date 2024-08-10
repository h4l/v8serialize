import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from v8serialize.decode import ReadableTagStream, TagMapper
from v8serialize.encode import (
    DefaultEncodeContext,
    ObjectMapper,
    WritableTagStream,
    serialize_object_references,
)


@pytest.fixture(scope="session")
def object_mapper() -> ObjectMapper:
    return ObjectMapper()


@pytest.fixture(scope="session")
def tag_mapper() -> TagMapper:
    return TagMapper()


any_atomic = st.one_of(
    st.integers(),
    # NaN breaks equality when nested inside objects. We test with nan in
    # test_codec_rt_double.
    st.floats(allow_nan=False),
    st.text(),
)

# https://hypothesis.works/articles/recursive-data/
any_object = st.recursive(
    any_atomic,
    lambda children: st.one_of(
        st.dictionaries(
            keys=any_atomic,
            values=children,
        ),
        st.sets(elements=any_atomic),
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


@given(value=st.dictionaries(keys=any_atomic, values=any_object))
def test_codec_rt_jsmap(
    value: dict[object, object],
    tag_mapper: TagMapper,
) -> None:
    encode_ctx = DefaultEncodeContext([ObjectMapper()])
    encode_ctx.stream.write_jsmap(value.items(), ctx=encode_ctx, identity=value)
    rts = ReadableTagStream(encode_ctx.stream.data)
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
    result = set[object]()
    result.update(rts.read_jsset(tag_mapper, identity=result))
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
