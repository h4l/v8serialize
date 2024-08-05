import pytest
from hypothesis import given
from hypothesis import strategies as st

from v8serialize.decode import DecodeV8CodecError, ReadableTagStream
from v8serialize.encode import WritableTagStream


@given(st.integers(min_value=1))
def test_decode_varint__truncated(n: int) -> None:
    wts = WritableTagStream()
    wts.write_varint(n)
    rts = ReadableTagStream(wts.data[:-2])

    with pytest.raises(DecodeV8CodecError, match="Data truncated") as exc_info:
        rts.read_varint()

    assert exc_info.value.position == max(0, len(rts.data) - 1)
