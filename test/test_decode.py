from __future__ import annotations

from base64 import b64decode

import pytest
from hypothesis import given
from hypothesis import strategies as st

from v8serialize.constants import JSErrorName, SerializationTag, kLatestVersion
from v8serialize.decode import DefaultDecodeContext, ReadableTagStream, TagMapper, loads
from v8serialize.encode import (
    DefaultEncodeContext,
    ObjectMapper,
    WritableTagStream,
    serialize_object_references,
)
from v8serialize.errors import DecodeV8CodecError
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsbuffers import JSArrayBuffer, JSUint8Array
from v8serialize.jstypes.jserror import JSError, JSErrorData


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
    with result.get_buffer() as buffer:
        assert buffer.tolist() == [1, 2, 3]


def test_VerifyObjectCount_not_supported() -> None:
    # VerifyObjectCount tag has not been written by any version of the V8
    # serializer in the V8 git repo (I think v9 is the earliest version in the
    # current source layout). Therefore we don't need to implement support for
    # ignoring it.
    wts = WritableTagStream()
    wts.write_header()
    wts.write_tag(SerializationTag.kVerifyObjectCount)
    wts.write_varint(1)

    with pytest.raises(
        DecodeV8CodecError,
        match="No tag mapper was able to read the tag kVerifyObjectCount",
    ):
        loads(wts.data)


@pytest.mark.parametrize("version", [12, kLatestVersion + 1])
def test_ReadableTagStream__rejects_unsupported_versions(version: int) -> None:
    wts = WritableTagStream()
    wts.write_tag(SerializationTag.kVersion)
    wts.write_varint(version)

    rts = ReadableTagStream(wts.data)
    with pytest.raises(DecodeV8CodecError) as exc_info:
        rts.read_header()

    assert f"Unsupported version {version}" in str(exc_info.value)


@pytest.mark.parametrize(
    "tag", [SerializationTag.kWasmMemoryTransfer, SerializationTag.kWasmModuleTransfer]
)
def test_wasm_is_not_supported(tag: SerializationTag) -> None:
    wts = WritableTagStream()
    wts.write_tag(tag)
    decode_ctx = DefaultDecodeContext(stream=ReadableTagStream(wts.data))

    with pytest.raises(
        DecodeV8CodecError,
        match=f"Stream contains a {tag.name} which is not supported.",
    ):
        decode_ctx.decode_object()


@pytest.mark.parametrize(
    "example",
    [
        JSErrorData(cause=JSArrayBuffer(b"foobar")),
        JSErrorData(cause=JSUint8Array(JSArrayBuffer(b"foobar"))),
        # The Uint8 view applies to a reference to the buffer
        (lambda buf: JSArray([buf, JSErrorData(cause=JSUint8Array(buf))]))(
            JSArrayBuffer(b"foobar")
        ),
    ],
)
def test_decode_array_buffer_as_error_cause(example: object) -> None:
    # ArrayBuffers are weird in that they can be followed by an ArrayBufferView
    # serialized as a separate object. Normally, the byte following any object
    # is EOF (nothing) or a valid SerializationTag. However when an object is
    # serialized as the cause of a JSError, the next byte is the error's End
    # tag, which is not a Serialization Tag.

    encode_ctx = DefaultEncodeContext(
        object_mappers=[serialize_object_references, ObjectMapper()]
    )
    encode_ctx.stream.write_header()
    encode_ctx.encode_object(example)

    # The buffer is referenced, not duplicated when it occurs twice
    assert encode_ctx.stream.data.count(b"foobar") == 1

    result = loads(
        encode_ctx.stream.data,
        tag_mappers=[TagMapper(js_error_builder=JSErrorData.builder)],
    )
    assert result == example


def test_decode_legacy_v15_error_stack() -> None:
    # V8 used to encode errors with the stack string after the cause, which is
    # incompatible with the current fixed field order it uses (with stack before
    # cause). This is an example of such an error encoding.
    result = loads(b'\xff\x0frEm"\x00cI\x00s"\x00.')
    assert result == JSError(message="", name=JSErrorName.EvalError, stack="", cause=0)
