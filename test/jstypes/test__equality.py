from __future__ import annotations

from math import isnan
from test.strategies import values_and_objects as mk_values_and_objects

import pytest
from hypothesis import given

from v8serialize.jstypes._equality import same_value_zero
from v8serialize.jstypes.jsobject import JSObject
from v8serialize.jstypes.jsprimitiveobject import JSPrimitiveObject
from v8serialize.jstypes.jsundefined import JSUndefined

values_and_objects = mk_values_and_objects(allow_nan=True, only_hashable=False)


# Examples from: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Equality_comparisons_and_sameness#comparing_equality_methods  # noqa: B950
@pytest.mark.parametrize(
    "x, y, equal",
    [
        (JSUndefined, JSUndefined, True),
        (None, None, True),
        (True, True, True),
        (False, False, True),
        ("foo", "foo", True),
        (b"foo", b"foo", True),
        (0, 0, True),
        (0.0, 0.0, True),
        (-0.0, -0.0, True),
        (0, False, False),
        (0.0, False, False),
        ("", False, False),
        (b"", False, False),
        ("", 0, False),
        (b"", 0, False),
        ("0", 0, False),
        ("17", 17, False),
        ([1, 2], "1,2", False),
        (JSPrimitiveObject("foo"), "foo", False),
        (None, JSUndefined, False),
        (None, False, False),
        (JSUndefined, False, False),
        (JSObject(foo="bar"), JSObject(foo="bar"), False),
        (JSPrimitiveObject("foo"), JSPrimitiveObject("foo"), False),
        (0, None, False),
        (0, float("nan"), False),
        (float("nan"), float("nan"), True),
    ],
)
def test_same_value_zero__mdn_examples(x: object, y: object, equal: bool) -> None:
    assert (same_value_zero(x) == same_value_zero(y)) is equal


@given(x=values_and_objects, y=values_and_objects)
def test_same_value_zero(x: object, y: object) -> None:
    both_same_constant = any(
        x is _ and y is _ for _ in [JSUndefined, None, True, False]
    )
    both_same_string = isinstance(x, str) and isinstance(y, str) and x == y
    both_same_bytes = isinstance(x, bytes) and isinstance(y, bytes) and x == y
    both_nan = isinstance(x, float) and isinstance(y, float) and isnan(x) and isnan(y)
    # note: -0.0 == 0.0 by default in Python
    both_equal_numbers = (
        isinstance(x, (int, float)) and isinstance(y, (int, float)) and x == y
    )
    both_same_object = x is y
    should_be_equal = (
        both_same_constant
        or both_same_string
        or both_same_bytes
        or both_nan
        or both_equal_numbers
        or both_same_object
    )

    assert (same_value_zero(x) == same_value_zero(y)) is should_be_equal
