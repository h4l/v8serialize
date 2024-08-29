import re
from datetime import datetime

import pytest

from v8serialize.constants import JSRegExpFlag, SerializationFeature
from v8serialize.decode import loads
from v8serialize.encode import (
    DefaultEncodeContext,
    FeatureNotEnabledEncodeV8CodecError,
    ObjectMapper,
    UnmappedValueEncodeV8CodecError,
    WritableTagStream,
    dumps,
    serialize_object_references,
)
from v8serialize.jstypes import JSRegExp
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsbuffers import JSArrayBuffer, JSFloat16Array
from v8serialize.jstypes.jserror import JSError
from v8serialize.jstypes.jsmap import JSMap
from v8serialize.jstypes.jsobject import JSObject
from v8serialize.jstypes.jsset import JSSet
from v8serialize.jstypes.jsundefined import JSUndefined
from v8serialize.references import IllegalCyclicReferenceV8CodecError


@pytest.mark.parametrize(
    "py_value,js_value",
    [
        (1, 1),
        (1.5, 1.5),
        (2**100, 2**100),
        (True, True),
        (False, False),
        (None, None),
        ("Snake 🐍", "Snake 🐍"),
        (b"foo", JSArrayBuffer(b"foo")),
        (JSUndefined, JSUndefined),
        (
            datetime(2024, 1, 2, 3, 4, 5, 500_000),
            datetime(2024, 1, 2, 3, 4, 5, 500_000),
        ),
        (
            re.compile("[a-z].*", re.DOTALL | re.IGNORECASE | re.ASCII),
            JSRegExp("[a-z].*", JSRegExpFlag.DotAll | JSRegExpFlag.IgnoreCase),
        ),
        # dict values() is a simple Collection, not a list
        (dict(a=1, b=2).values(), JSArray([1, 2])),
        ([1, 2], JSArray([1, 2])),
        ({1, 2}, JSSet([1, 2])),
        # Python dicts serialize as Map, not objects by default
        (dict(a=1, b=2), JSMap(a=1, b=2)),
        # JSObjects serialize as JS objects
        (JSObject(a=1, b=2), JSObject(a=1, b=2)),
        (
            ValueError("Oops!"),
            JSError(message="ValueError: Oops!", stack="ValueError: Oops!"),
        ),
    ],
)
def test_python_collections(py_value: object, js_value: object) -> None:
    serialized = dumps(py_value)
    deserialized = loads(serialized)

    assert deserialized == js_value


def test_feature_float16__cannot_write_float16array_when_disabled() -> None:
    f16 = JSFloat16Array(JSArrayBuffer(b"\x00\xff"))

    ctx = DefaultEncodeContext(
        stream=WritableTagStream(features=~SerializationFeature.Float16Array)
    )

    with pytest.raises(
        UnmappedValueEncodeV8CodecError,
        match="No object mapper was able to write the value",
    ):
        ctx.encode_object(f16)

    with pytest.raises(
        FeatureNotEnabledEncodeV8CodecError,
        match="Cannot write Float16Array when the Float16Array "
        "SerializationFeature is not enabled",
    ) as exc_info:
        ctx.stream.write_js_array_buffer_view(f16)

    assert exc_info.value.feature_required == SerializationFeature.Float16Array


def test_feature_float16__can_write_float16array_when_enabled() -> None:
    f16 = JSFloat16Array(JSArrayBuffer(b"\xaa\xbb"))

    ctx = DefaultEncodeContext(
        stream=WritableTagStream(features=SerializationFeature.Float16Array)
    )

    ctx.stream.write_header()
    ctx.encode_object(f16)
    result = loads(ctx.stream.data)
    assert result == f16


def test_feature_resizable_array_buffers__resizable_arrays_are_written_as_regular_when_disabled() -> (  # noqa: B950
    None
):
    buf = JSArrayBuffer(b"foo", max_byte_length=32)
    assert buf.resizable

    ctx = DefaultEncodeContext(
        stream=WritableTagStream(features=~SerializationFeature.ResizableArrayBuffers)
    )

    ctx.stream.write_header()
    ctx.encode_object(buf)
    result = loads(ctx.stream.data)
    assert isinstance(result, JSArrayBuffer)
    assert result == JSArrayBuffer(b"foo")
    assert not result.resizable
    assert result.max_byte_length == 3


def test_feature_resizable_array_buffers__resizable_arrays_are_written_as_resizable_when_enabled() -> (  # noqa: B950
    None
):
    buf = JSArrayBuffer(b"foo", max_byte_length=32)
    assert buf.resizable

    ctx = DefaultEncodeContext(
        stream=WritableTagStream(features=SerializationFeature.ResizableArrayBuffers)
    )

    ctx.stream.write_header()
    ctx.encode_object(buf)
    result = loads(ctx.stream.data)
    assert isinstance(result, JSArrayBuffer)
    assert result == JSArrayBuffer(b"foo", max_byte_length=32)
    assert result.resizable


def test_feature_cyclic_error_cause__cyclic_errors_not_allowed_when_disabled() -> None:
    err = JSError("I broke myself")
    err.cause = err

    ctx = DefaultEncodeContext(
        object_mappers=[serialize_object_references, ObjectMapper()],
        stream=WritableTagStream(features=~SerializationFeature.CircularErrorCause),
    )

    ctx.stream.write_header()
    with pytest.raises(
        IllegalCyclicReferenceV8CodecError,
    ) as exc_info:
        ctx.encode_object(err)

    assert (
        "An illegal cyclic reference was made to an object: Errors cannot "
        "reference themselves in their cause without CircularErrorCause enabled:"
        in str(exc_info.value)
    )


def test_feature_cyclic_error_cause__cyclic_errors_are_allowed_when_enabled() -> None:
    err = JSError("I broke myself")
    err.cause = err

    ctx = DefaultEncodeContext(
        object_mappers=[serialize_object_references, ObjectMapper()],
        stream=WritableTagStream(features=SerializationFeature.CircularErrorCause),
    )

    ctx.stream.write_header()
    ctx.encode_object(err)
    result = loads(ctx.stream.data)

    assert isinstance(result, JSError)
    assert result == err
    assert result is not err
    assert result.cause is result
