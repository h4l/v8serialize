from __future__ import annotations

from typing import Sequence

from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsarrayproperties import JSHole, JSHoleType
from v8serialize.jstypes.jsobject import JSObject


def test_init__array() -> None:
    assert dict(JSArray([])) == {}

    items1: list[str] = ["a", "b"]
    assert dict(JSArray[str](items1)) == {0: "a", 1: "b"}

    items2: list[str | JSHoleType] = ["a", "b", JSHole, "d"]
    assert dict(JSArray[str](items2)) == {0: "a", 1: "b", 3: "d"}

    assert dict(JSArray[str]([JSHole, "b"], x="X")) == {1: "b", "x": "X"}
    assert dict(JSArray[str](["a", "b"], x="X", **{"0": "override"})) == (
        {0: "override", 1: "b", "x": "X"}
    )


def test_init__mapping() -> None:
    assert dict(JSArray({})) == {}

    items1: dict[str | int, str] = {0: "a", "1": "b"}
    assert dict(JSArray[str](items1)) == {0: "a", 1: "b"}

    items2: dict[str | int, str] = {0: "a", 1: "b", 3: "d"}
    assert dict(JSArray[str](items2)) == {0: "a", 1: "b", 3: "d"}

    assert dict(JSArray[str]({1: "b"}, x="X")) == {1: "b", "x": "X"}
    assert dict(JSArray[str]({0: "a", 1: "b"}, x="X", **{"0": "override"})) == (
        {0: "override", 1: "b", "x": "X"}
    )


def test_jsarray_is_not_sequence() -> None:
    assert not isinstance(JSArray(), Sequence)
    # Its array properties are though
    assert isinstance(JSArray().array, Sequence)


def test_abc_registration() -> None:

    class Example:
        pass

    assert not isinstance(Example(), JSArray)
    assert not isinstance(Example(), JSObject)
    JSArray.register(Example)
    assert isinstance(Example(), JSArray)
    # Registered objects also become subtypes of JSObject, because JSArray is.
    assert isinstance(Example(), JSObject)
