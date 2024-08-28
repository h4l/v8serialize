import re
from datetime import datetime

import pytest

from v8serialize.constants import JSRegExpFlag, SerializationFeature
from v8serialize.decode import loads
from v8serialize.encode import (
    DefaultEncodeContext,
    FeatureNotEnabledEncodeV8CodecError,
    UnmappedValueEncodeV8CodecError,
    WritableTagStream,
    dumps,
)
from v8serialize.jstypes import JSRegExp
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsbuffers import JSArrayBuffer, JSFloat16Array
from v8serialize.jstypes.jserror import JSError
from v8serialize.jstypes.jsmap import JSMap
from v8serialize.jstypes.jsobject import JSObject
from v8serialize.jstypes.jsset import JSSet
from v8serialize.jstypes.jsundefined import JSUndefined


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
