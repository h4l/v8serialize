from __future__ import annotations

import operator
import sys
from typing import Any

from test.utils import typeval
from v8serialize.jstypes.jsbigint import JSBigInt


def test_repr() -> None:
    assert repr(JSBigInt(42)) == "JSBigInt(42)"


def test_is_instanceof_int() -> None:
    assert isinstance(JSBigInt(42), int)


def check_int_attr(name: str, *, value: int = 42) -> None:
    jsbigint = JSBigInt(value)
    i = int(value)
    assert typeval(getattr(jsbigint, name)) == (JSBigInt, getattr(i, name))


def check_int_method(name: str, *args: Any, value: int = 42) -> None:
    jsbigint = JSBigInt(value)
    int_value = int(value)

    expected: int | tuple[int, ...] = getattr(int_value, name)(*args)
    actual: JSBigInt | tuple[JSBigInt, ...] = getattr(jsbigint, name)(*args)

    if isinstance(expected, tuple):
        assert isinstance(actual, tuple)
        assert expected == actual
        assert set(type(v) for v in actual) == {JSBigInt}
    else:
        assert typeval(actual) == (JSBigInt, expected)


def test_methods_and_operators_return_JSBigInt() -> None:
    """All the methods returning int values return JSBigInt."""
    # Same order as methods defined in JSBigInt
    check_int_method("as_integer_ratio")
    check_int_attr("real")
    check_int_attr("imag")
    check_int_attr("numerator")
    check_int_attr("denominator")
    check_int_method("conjugate")
    check_int_method("__add__", 2)
    check_int_method("__sub__", 2)
    check_int_method("__mul__", 2)
    check_int_method("__floordiv__", 2)
    check_int_method("__mod__", 2)
    check_int_method("__divmod__", 2)
    check_int_method("__radd__", 2)
    check_int_method("__rsub__", 2)
    check_int_method("__rmul__", 2)
    check_int_method("__rfloordiv__", 2)
    check_int_method("__rmod__", 2)
    check_int_method("__rdivmod__", 2)
    check_int_method("__pow__", 2)
    check_int_method("__pow__", 2, 100)
    check_int_method("__rpow__", 2)
    check_int_method("__rpow__", 2, 100)
    check_int_method("__and__", 2)
    check_int_method("__or__", 2)
    check_int_method("__xor__", 2)
    check_int_method("__lshift__", 2)
    check_int_method("__rshift__", 2)
    check_int_method("__rand__", 2)
    check_int_method("__ror__", 2)
    check_int_method("__rxor__", 2)
    check_int_method("__rlshift__", 2)
    check_int_method("__rrshift__", 2)
    check_int_method("__neg__")
    check_int_method("__pos__")
    check_int_method("__invert__")
    check_int_method("__trunc__")
    check_int_method("__ceil__")
    check_int_method("__floor__")
    check_int_method("__round__")
    check_int_method("__round__", 2)
    assert typeval(float(JSBigInt(42))) == (float, 42.0)
    assert typeval(JSBigInt(42).__int__()) == (int, 42)
    assert typeval(int(JSBigInt(42))) == (int, 42)
    check_int_method("__abs__")
    assert typeval(hash(JSBigInt(42))) == (int, 42)

    # Before 3.10 operator.index() returns the instance without calling the
    # __index__ method, so the type is JSBigInt (we'd rather it was int).
    # https://github.com/python/cpython/blob/340a82d9cff7127bb5a777d8b9a30b861bb4beee/Objects/abstract.c#L1324
    if sys.version_info >= (3, 10):
        assert typeval(operator.index(JSBigInt(42))) == (int, 42)
    else:
        assert typeval(operator.index(JSBigInt(42))) == (JSBigInt, 42)


def test_types() -> None:
    # Can assign to int var
    i: int = JSBigInt(42) + 3
    # Types reflect that JSBigInt is preserved by operators
    big: JSBigInt = 4 * JSBigInt(4)

    assert i == 45
    assert big == 16
