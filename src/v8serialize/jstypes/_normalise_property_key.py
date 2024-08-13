from v8serialize.jstypes.jsarrayproperties import MAX_ARRAY_LENGTH


def canonical_numeric_index_string(value: str) -> int | None:
    """Get the int representation of value or None.

    The result is None unless interpreting value as a base10 int and back to a
    string is equal to value.

    This is very similar to the ECMA spec's function, except that negative
    values are returned as None.
    https://tc39.es/ecma262/#sec-canonicalnumericindexstring
    """
    # isdecimal includes non-ascii decimal numbers.
    if value.isdecimal() and value.isascii():
        int_value = int(value)
        # numbers with unnecessary leading zeros are not canonical
        return None if value[0] == "0" and value != "0" else int_value
    return None


def normalise_property_key(key: str | int) -> str | int:
    """Get the canonical representation of a JavaScript property key as int or str.

    A key is an int if the str value is the base10 representation of the same
    integer and falls in the inclusive range 0..2**32-2 (which is the max
    JavaScript array index).

    >>> normalise_property_key('3')
    3
    >>> normalise_property_key('A')
    'A'
    >>> normalise_property_key('-3')
    '-3'

    This reflects the behaviour defined in: https://tc39.es/ecma262/#integer-index
    """
    if isinstance(key, str):
        int_value = canonical_numeric_index_string(key)
        if int_value is None:
            return key
        key = int_value

    if 0 <= key < MAX_ARRAY_LENGTH:
        return key
    return str(key)
