from __future__ import annotations

from typing import Final
from typing_extensions import assert_type

from v8serialize.constants import FLOAT64_SAFE_INT_RANGE, SerializationTag
from v8serialize.jstypes import JSPrimitiveObject
from v8serialize.jstypes.jsbigint import JSBigInt
from v8serialize.jstypes.jsprimitiveobject import (
    BigIntJSPrimitiveObject,
    FalseJSPrimitiveObject,
    NumberJSPrimitiveObject,
    StringJSPrimitiveObject,
    TrueJSPrimitiveObject,
)

# 2**53 + 2 is an integer that can be represented exactly as a float64, but is
# outside the limit of sequential integers that float64 can represent.
# (e.g. float64 cannot represent 2**53 + 1 exactly.)
UNSAFE_INTEGER_FLOAT: Final = float(2**53 + 2)
assert int(UNSAFE_INTEGER_FLOAT) == 2**53 + 2


def test_init_types() -> None:
    true_obj = assert_type(JSPrimitiveObject(True), TrueJSPrimitiveObject)
    assert true_obj.value is True
    assert true_obj.tag is SerializationTag.kTrueObject

    false_obj = assert_type(JSPrimitiveObject(False), FalseJSPrimitiveObject)
    assert false_obj.value is False
    assert false_obj.tag is SerializationTag.kFalseObject

    number_obj = assert_type(JSPrimitiveObject(1.0), NumberJSPrimitiveObject)
    assert number_obj.value == 1.0
    assert type(number_obj.value) is float
    assert number_obj.tag is SerializationTag.kNumberObject

    # int values are mapped to JavaScript Number when in the safe int range,
    # or JavaScript bigint outside that.

    # mypy doesn't match the ambiguous int overload for some reason, it falls
    # back to the default typevar bounds.
    int_bigint_obj = assert_type(  # type: ignore[assert-type]
        JSPrimitiveObject(FLOAT64_SAFE_INT_RANGE.stop),
        "NumberJSPrimitiveObject | BigIntJSPrimitiveObject",
    )
    assert int_bigint_obj.value == FLOAT64_SAFE_INT_RANGE.stop
    assert type(int_bigint_obj.value) is JSBigInt
    assert int_bigint_obj.tag is SerializationTag.kBigIntObject

    # force int as bigint by specifying tag
    int_bigint_obj2 = assert_type(
        JSPrimitiveObject(0, tag=SerializationTag.kBigIntObject),
        BigIntJSPrimitiveObject,
    )
    assert int_bigint_obj2.value == 0
    assert type(int_bigint_obj2.value) is JSBigInt
    assert int_bigint_obj2.tag is SerializationTag.kBigIntObject

    # mypy doesn't match the ambiguous int overload for some reason
    int_number_obj = assert_type(  # type: ignore[assert-type]
        JSPrimitiveObject(FLOAT64_SAFE_INT_RANGE.stop - 1),
        "NumberJSPrimitiveObject | BigIntJSPrimitiveObject",
    )
    assert int_number_obj.value == FLOAT64_SAFE_INT_RANGE.stop - 1
    assert type(int_number_obj.value) is float
    assert int_number_obj.tag is SerializationTag.kNumberObject

    # force int as number by specifying tag
    int_number_obj2 = assert_type(
        JSPrimitiveObject(
            int(UNSAFE_INTEGER_FLOAT), tag=SerializationTag.kNumberObject
        ),
        NumberJSPrimitiveObject,
    )
    assert int_number_obj2.value == UNSAFE_INTEGER_FLOAT
    assert type(int_number_obj2.value) is float
    assert int_number_obj2.tag is SerializationTag.kNumberObject

    string_obj = assert_type(JSPrimitiveObject("s"), StringJSPrimitiveObject)
    assert string_obj.value == "s"
    assert string_obj.tag is SerializationTag.kStringObject
