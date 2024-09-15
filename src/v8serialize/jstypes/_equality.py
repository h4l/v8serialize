from __future__ import annotations

from math import isnan
from typing import Final, NewType

from v8serialize.jstypes.jsundefined import JSUndefinedEnum

_nankey: Final = (float("nan"),)  # equal thanks to tuple identity

JSSameValueZero = NewType("JSSameValueZero", object)
"""
The type of the opaque values returned by [`same_value_zero`].

[`same_value_zero`]: `v8serialize.jstypes.same_value_zero`
"""


def same_value_zero(value: object) -> JSSameValueZero:
    """
    Get a surrogate value that follows [JavaScript same-value-zero equality rules][samevaluezero].

    Python values can be compared according to same-value-zero by using `==`,
    `hash()` on the result of calling this function on the values, rather than
    on the values them directly. Like a key function when sorting.

    `same_value_zero(x) == same_value_zero(y)` is `True` if `x` and `y` are
    equal under [JavaScript's same-value-zero rule][samevaluezero].

    [samevaluezero]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/\
Equality_comparisons_and_sameness#same-value-zero_equality

    Parameters
    ----------
    value
        Any Python object

    Returns
    -------
    :
        An opaque value that follows the same-value-zero rules when compared
        with `==` or passed to `hash()`.


    Examples
    --------
    >>> NaN = float('nan')
    >>> NaN == NaN
    False
    >>> same_value_zero(NaN) == same_value_zero(NaN)
    True

    >>> True == 1
    True
    >>> same_value_zero(True) == same_value_zero(1)
    False

    >>> l1, l2 = [0], [0]
    >>> l1 is l2
    False
    >>> l1 == l2
    True
    >>> same_value_zero(l1) == same_value_zero(l2)
    False
    >>> same_value_zero(l1) == same_value_zero(l1)
    True

    Strings and numbers are equal by value.

    >>> s1, s2 = str([ord('a')]), str([ord('a')])
    >>> s1 is s2
    False
    >>> s1 == s2
    True
    >>> same_value_zero(s1) == same_value_zero(s2)
    True
    >>> same_value_zero(1.0) == same_value_zero(1)
    True
    """  # noqa: E501
    # These values are equal by value.
    if isinstance(value, bool):
        # bools are equal to 0 and 1 by default
        return (bool, value)  # type: ignore[return-value]
    elif isinstance(value, (int, float)):
        if isnan(value):
            # Represent nan as a value equal to itself.
            return _nankey  # type: ignore[return-value]
        return value  # type: ignore[return-value]

    # bytes is included here despite not existing in JS. I don't think it makes
    # sense to consider bytes equal by identity; it's a type that would be
    # equal under these rules if it did exist in JS.
    elif isinstance(value, (JSUndefinedEnum, type(None), str, bytes)):
        return value  # type: ignore[return-value]
    # Everything else is equal by object identity. Wrap id in a tuple to avoid
    # clashing with int.
    return (id(value),)  # type: ignore[return-value]
