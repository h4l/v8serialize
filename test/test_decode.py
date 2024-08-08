from base64 import b64decode

import pytest
from hypothesis import given
from hypothesis import strategies as st

from v8serialize.decode import DecodeV8CodecError, ReadableTagStream, loads
from v8serialize.encode import WritableTagStream


@given(st.integers(min_value=1))
def test_decode_varint__truncated(n: int) -> None:
    wts = WritableTagStream()
    wts.write_varint(n)
    rts = ReadableTagStream(wts.data[:-2])

    with pytest.raises(DecodeV8CodecError, match="Data truncated") as exc_info:
        rts.read_varint()

    assert exc_info.value.position == max(0, len(rts.data) - 1)


@pytest.mark.parametrize(
    "serialized,expected",
    [
        # v8.serialize(new Map([["a", BigInt(1)], ["b", BigInt(2)]])).toString('base64')
        ("/w87IgFhWhABAAAAAAAAACIBYloQAgAAAAAAAAA6BA==", {"a": 1, "b": 2})
    ],
)
def test_loads(serialized: str, expected: object) -> None:
    result = loads(b64decode(serialized))
    assert result == expected
