import re
from datetime import datetime

import pytest

from v8serialize.constants import JSRegExpFlag
from v8serialize.decode import loads
from v8serialize.encode import dumps
from v8serialize.jstypes import JSRegExp
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsbuffers import JSArrayBuffer
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
