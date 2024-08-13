import re

from hypothesis import given
from hypothesis import strategies as st

from v8serialize.jstypes._normalise_property_key import (
    canonical_numeric_index_string,
    normalise_property_key,
)
from v8serialize.jstypes.jsarrayproperties import MAX_ARRAY_LENGTH

integer_indexes = st.integers(min_value=0, max_value=MAX_ARRAY_LENGTH - 1)

invalid_integer_indexes = st.one_of(
    st.integers(max_value=-1), st.integers(min_value=MAX_ARRAY_LENGTH)
)
"""Integers below or above the allowed range for array indexes."""

non_canonical_integers = st.integers().map(lambda i: f"0{i}")
non_int_strings = st.text().filter(lambda x: not is_base10_int_str(x))

non_index_strings = st.one_of(non_canonical_integers, non_int_strings)


def is_base10_int_str(value: str) -> bool:
    return bool(re.match(r"^(0|[1-9][0-9]*)$", value))


@given(valid_index=integer_indexes)
def test_canonical_numeric_index_string__range__matches_valid_indexes(
    valid_index: int,
) -> None:
    result = canonical_numeric_index_string(str(valid_index))
    assert result == valid_index


@given(non_index=non_index_strings)
def test_canonical_numeric_index_string__range__rejects_non_index_strings(
    non_index: str,
) -> None:
    result = canonical_numeric_index_string(non_index)
    assert result is None


@given(valid_index=integer_indexes)
def test_normalise_property_key__returns_int_for_ints_in_array_index_range(
    valid_index: int,
) -> None:
    assert normalise_property_key(valid_index) == valid_index


@given(valid_index=integer_indexes)
def test_normalise_property_key__returns_int_for_canonical_int_strings_in_array_index_range(  # noqa: B950
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


@given(non_index_strings)
def test_normalise_property_key__returns_str_for_non_index_strings(
    non_index: str,
) -> None:
    assert normalise_property_key(non_index) == non_index
