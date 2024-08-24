from base64 import b64decode

import pytest
from hypothesis import given
from hypothesis import strategies as st

from v8serialize.constants import SerializationTag
from v8serialize.decode import ReadableTagStream, TagMapper, loads
from v8serialize.encode import WritableTagStream
from v8serialize.errors import DecodeV8CodecError
from v8serialize.jstypes.jsbuffers import JSUint8Array


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
        ("/w87IgFhWhABAAAAAAAAACIBYloQAgAAAAAAAAA6BA==", {"a": 1, "b": 2}),
        # v8.serialize(new Set(["a", BigInt(1), "b", BigInt(2)])).toString('base64')
        ("/w8nIgFhWhABAAAAAAAAACIBYloQAgAAAAAAAAAsBA==", {"a", 1, "b", 2}),
        # s = new Set([1]); v8.serialize(new Map([['a', s], ['b', s]]))
        #   .toString('base64')
        ("/w87IgFhJ0kCLAEiAWJeAToE", {"a": {1}, "b": {1}}),  # TODO: verify identity
    ],
)
def test_loads(serialized: str, expected: object) -> None:
    result = loads(b64decode(serialized))
    assert result == expected


def test_load_v13_arraybufferview() -> None:
    # Format v13 is the oldest version it makes sense to support, introduced in
    # 2017 and used in Node.js 16. It serializes ArrayBufferView without flags
    #
    # $ docker container run --rm -it node:16-alpine -e '
    #     const v8 = require("v8");
    #     const ser = new v8.Serializer();
    #     ser.writeHeader();
    #     ser.writeValue(Uint8Array.from([1, 2, 3]));
    #     console.log(ser.releaseBuffer().toString("base64"));'
    #
    # Note, this flag field was mistakenly added without bumping the version in
    # V8, which seems to have resulted in some v13 versions writing the flags
    # field while reporting v13 format.
    #
    # The V8 code attempts to work around the issue by caching an exception when
    # reading in v13 mode, and retrying with v14 behaviour enabled. We've not
    # implemented this behaviour as v13 is so old that probably nothing is using
    # it any more, and even if they are they should have updated to a version
    # that fixed this issue, as the change was reverted later.

    v13_array_buffer_view = b64decode("/w1CAwECA1ZCAAM=")
    assert v13_array_buffer_view[1] == 13  # v13
    result = loads(v13_array_buffer_view)
    assert isinstance(result, JSUint8Array)
    assert result.get_buffer().tolist() == [1, 2, 3]


@pytest.mark.parametrize(
    "tag", [SerializationTag.kWasmMemoryTransfer, SerializationTag.kWasmModuleTransfer]
)
def test_wasm_is_not_supported(tag: SerializationTag) -> None:
    wts = WritableTagStream()
    wts.write_tag(tag)
    rts = ReadableTagStream(wts.data)

    with pytest.raises(
        DecodeV8CodecError,
        match=f"Stream contains a {tag.name} which is not supported.",
    ):
        rts.read_object(TagMapper())
