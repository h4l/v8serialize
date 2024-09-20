from __future__ import annotations

from collections.abc import Sequence

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


def test_eq() -> None:
    assert JSArray() == JSArray()
    assert JSArray(**{"0": 1}, a=1, b=2) == JSArray(**{"0": 1}, a=1, b=2)
    assert JSArray(a=1, b=2) == JSArray(a=1, b=2)

    assert JSArray() != []
    assert JSArray([1, 2]) != [1, 2]
    assert JSArray([1, JSHole, 2]) != [1, 2]
    assert JSArray([], a=1) != []
    assert JSArray([], a=1) != {"a": 1}
    assert JSArray([], a=1) != JSObject({"a": 1})

    # Objects are not equal to equivalent arrays, like dicts are not equal to lists
    assert JSObject() != JSArray()
    assert JSObject(**{"0": 1}) != JSArray([1])
    assert JSObject(a=1) != JSArray(a=1)


def test_eq__cycle_direct() -> None:
    # Objects that contain reference cycles with the same identity structure are
    # equal. See test__recursive_eq.py.
    x = JSArray[object](a=1)
    x["b"] = x
    y = JSArray[object](a=1)
    y["b"] = y

    assert x == y


def test__eq__cycle_direct_unequal() -> None:
    x = JSArray[object](a=1)
    x["b"] = x

    # Same shape as l, but identity is different as r and _r repeat alternately
    y_ = JSArray[object](a=1)
    y = JSArray[object](a=1)
    y_["b"] = y
    y["b"] = y_

    assert x != y


def test__eq__cycle_indirect() -> None:
    # Objects that contain reference cycles with the same identity structure are
    # equal. See test__recursive_eq.py.
    x = JSArray(a=1, b=(x_b := JSObject()))
    x_b["c"] = x
    y = JSArray(a=1, b=(y_b := JSObject()))
    y_b["c"] = y

    assert x == y


def test__eq__cycle_indirect_unequal() -> None:
    x = JSArray(a=1, b=(x_b := JSArray()))
    x_b["c"] = x

    # Same shape as l, but identity is different as r and _r repeat alternately
    y_ = JSArray(a=1, b=(y__b := JSObject()))
    y = JSArray(a=1, b=(y_b := JSObject()))
    y__b["c"] = y
    y_b["c"] = y_

    assert x != y
