from types import MappingProxyType

import pytest

from v8serialize.jstypes.jsarrayproperties import JSHole
from v8serialize.jstypes.jsobject import JSObject


def test_init() -> None:
    assert dict(JSObject()) == {}

    with pytest.raises(TypeError, match=r"'NoneType' object is not iterable"):
        JSObject(None)  # type: ignore[call-overload]


def test_init__keys_and_get_item() -> None:
    assert dict(JSObject({})) == {}
    assert dict(JSObject({"x": "X"})) == {"x": "X"}
    # Supports arbitrary mapping types
    assert dict(JSObject(MappingProxyType({"x": "X"}))) == {"x": "X"}
    assert dict(JSObject({"x": "X", 0: "zero"})) == {0: "zero", "x": "X"}
    assert dict(JSObject({"x": "XA", 0: "zeroA", "0": "zeroB"}, x="XB")) == (
        {0: "zeroB", "x": "XB"}
    )


def test_init__iterable_kv_pairs() -> None:
    assert dict(JSObject([])) == {}
    assert dict(JSObject([("x", "X")])) == {"x": "X"}
    assert dict(JSObject(iter([("x", "X")]))) == {"x": "X"}
    assert dict(JSObject([("x", "X"), (0, "zero")])) == {0: "zero", "x": "X"}
    assert dict(JSObject([("x", "XA"), (0, "zeroA"), ("0", "zeroB")], x="XB")) == (
        {0: "zeroB", "x": "XB"}
    )

    with pytest.raises(ValueError, match=r"not enough values to unpack"):
        JSObject(["a", "b", "c"])  # type: ignore[list-item]
