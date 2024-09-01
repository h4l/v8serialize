from __future__ import annotations

import re

from hypothesis import example, given
from hypothesis import strategies as st

from v8serialize.jstypes._normalise_property_key import (
    canonical_numeric_index_string,
    normalise_property_key,
)
from v8serialize.jstypes.jsarrayproperties import MAX_ARRAY_LENGTH

int_integer_indexes = st.integers(min_value=0, max_value=MAX_ARRAY_LENGTH - 1)
float_integer_indexes = st.one_of(st.just(-0.0), int_integer_indexes.map(float))
integer_indexes = st.one_of(int_integer_indexes, float_integer_indexes)

invalid_integer_indexes = st.one_of(
    st.integers(max_value=-1), st.integers(min_value=MAX_ARRAY_LENGTH)
)
"""Integers below or above the allowed range for array indexes."""

invalid_float_indexes = st.one_of(
    st.floats(min_value=0, max_value=MAX_ARRAY_LENGTH - 1).filter(
        lambda f: not f.is_integer()
    ),
    st.floats(max_value=-0.0, exclude_max=True),  # exclude -0.0, which is valid
    st.floats(min_value=MAX_ARRAY_LENGTH),
)


non_canonical_integers = st.integers().map(lambda i: f"0{i}")
# Note: this includes the string "-0" which does not match index 0.
# See test_normalise_property_key__handles_negative_zero().
negative_integer_strings = st.integers(min_value=0).map(lambda i: f"-{i}")
non_int_strings = st.text().filter(lambda x: not is_base10_int_str(x))

non_index_strings = st.one_of(
    non_canonical_integers, negative_integer_strings, non_int_strings
)


def is_base10_int_str(value: str) -> bool:
    return bool(re.match(r"^(0|[1-9][0-9]*)$", value))


@given(valid_index=int_integer_indexes)
def test_canonical_numeric_index_string__range__matches_valid_indexes(
    valid_index: int,
) -> None:
    result = canonical_numeric_index_string(str(valid_index))
    assert result == valid_index


@given(non_index=non_index_strings)
@example("-0")
def test_canonical_numeric_index_string__range__rejects_non_index_strings(
    non_index: str,
) -> None:
    result = canonical_numeric_index_string(non_index)
    assert result is None


@given(valid_index=integer_indexes)
def test_normalise_property_key__returns_int_for_integers_in_array_index_range(
    valid_index: int | float,
) -> None:
    assert normalise_property_key(valid_index) == valid_index


@given(valid_index=int_integer_indexes)
def test_normalise_property_key__returns_int_for_canonical_integer_strings_in_array_index_range(  # noqa: B950
    valid_index: int,
) -> None:
    assert normalise_property_key(str(valid_index)) == valid_index


@given(invalid_index=invalid_integer_indexes)
def test_normalise_property_key__returns_str_for_ints_not_in_array_index_range(
    invalid_index: int,
) -> None:
    assert normalise_property_key(invalid_index) == str(invalid_index)


@given(invalid_index=invalid_integer_indexes)
def test_normalise_property_key__returns_str_for_str_ints_not_in_array_index_range(
    invalid_index: int,
) -> None:
    assert normalise_property_key(str(invalid_index)) == str(invalid_index)


@given(invalid_index=invalid_float_indexes)
def test_normalise_property_key__returns_str_for_floats_that_are_not_valid(
    invalid_index: float,
) -> None:
    result = normalise_property_key(invalid_index)
    if invalid_index.is_integer():
        assert result == f"{int(invalid_index)}"
    else:
        assert result == str(invalid_index)


@given(invalid_index=invalid_float_indexes)
def test_normalise_property_key__returns_str_for_float_strings_that_are_not_valid(
    invalid_index: float,
) -> None:
    # We can use "-1.0" rather than "-1" because we test negative int strings
    # separately.
    assert normalise_property_key(str(invalid_index)) == str(invalid_index)


@given(non_index_strings)
def test_normalise_property_key__returns_str_for_non_index_strings(
    non_index: str,
) -> None:
    assert normalise_property_key(non_index) == non_index


def test_normalise_property_key__handles_negative_zero() -> None:
    # ECMA 262 notes in particular that:
    # > "-0" is neither an integer index nor an array index.
    # -0 is a special case as it could be interpreted as -0.0 or 0.
    assert normalise_property_key("-0") == "-0"

    # Despite the above, the actual float value -0.0 is treated as 0. The reason
    # this is the case may not be immediately obvious from reading the spec:
    # - https://tc39.es/ecma262/#sec-object-type
    # - The spec requires that CanonicalNumericIndexString(n) returns a
    #   non-negative integer. And if you read the definition of
    #   CanonicalNumericIndexString(n) you see a rule that "-0" returns -0.
    # - The thing to realise is that the argument n is a string, so -0.0 is
    #   converted to a string first. Number::toString returns -0 as "0":
    #   > If x is either +0𝔽 or -0𝔽, return "0".
    # - Hence with -0 we call CanonicalNumericIndexString("0") which is 0.
    assert type(normalise_property_key(-0.0)) == int
    assert normalise_property_key(-0.0) == 0
