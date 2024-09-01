from __future__ import annotations

from math import isnan
from typing import Final, NewType

from v8serialize.jstypes.jsundefined import JSUndefinedEnum

_nankey: Final = (float("nan"),)  # equal thanks to tuple identity

JSSameValueZero = NewType("JSSameValueZero", object)


def same_value_zero(value: object) -> JSSameValueZero:
    """Get a surrogate value that follows JavaScript same-value-zero rules when
    compared with == and used with hash().

    `same_value_zero(x) == same_value_zero(y)` is `True` if `x` and `y` are
    equal under [JavaScript's same-value-zero rule][samevaluezero].

    [samevaluezero]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/\
Equality_comparisons_and_sameness#same-value-zero_equality
    """
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
