import math

import pytest
from frozendict import frozendict
from hypothesis import given
from hypothesis import strategies as st

from v8serialize.decode import ReadableTagStream, TagMapper
from v8serialize.encode import ObjectMapper, WritableTagStream


@pytest.fixture(scope="session")
def object_mapper() -> ObjectMapper:
    return ObjectMapper()


@pytest.fixture(scope="session")
def tag_mapper() -> TagMapper:
    return TagMapper(jsmap_type=frozendict, jsset_type=frozenset)


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
        st.dictionaries(keys=children, values=children, dict_class=frozendict),
        st.frozensets(elements=children),
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


@given(value=st.dictionaries(keys=any_object, values=any_object))
def test_codec_rt_jsmap(
    value: dict[object, object], object_mapper: ObjectMapper, tag_mapper: TagMapper
) -> None:
    wts = WritableTagStream()
    wts.write_jsmap(value.items(), object_mapper)
    rts = ReadableTagStream(wts.data)
    result = dict(rts.read_jsmap(tag_mapper))
    assert value == result
    assert rts.eof


@given(value=st.sets(elements=any_object))
def test_codec_rt_jsset(
    value: set[object], object_mapper: ObjectMapper, tag_mapper: TagMapper
) -> None:
    wts = WritableTagStream()
    wts.write_jsset(value, object_mapper)
    rts = ReadableTagStream(wts.data)
    result = set(rts.read_jsset(tag_mapper))
    assert value == result
    assert rts.eof


@given(value=any_object)
def test_codec_rt_object(
    value: object, object_mapper: ObjectMapper, tag_mapper: TagMapper
) -> None:
    wts = WritableTagStream()
    wts.write_object(value, object_mapper)

    rts = ReadableTagStream(wts.data)
    result = rts.read_object(tag_mapper)
    assert value == result
    assert rts.eof
