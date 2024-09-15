from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic

from v8serialize._pycompat.dataclasses import slots_if310
from v8serialize.constants import (
    FLOAT64_SAFE_INT_RANGE,
    PrimitiveObjectTag,
    SerializationTag,
)

if TYPE_CHECKING:
    from typing_extensions import TypeVar

    T = TypeVar(
        "T", bound="float | bool | int | str", default="float | bool | int | str"
    )
else:
    from typing import TypeVar

    T = TypeVar("T", bound="float | bool | int | str")


@dataclass(frozen=True, order=True, init=False, **slots_if310())
class JSPrimitiveObject(Generic[T], metaclass=ABCMeta):
    """
    Python equivalent of a wrapped/boxed JavaScript primitive.

    :::{.callout-tip}
    This is a low-level type that won't occur in decoded data by default, and
    can be ignored.
    :::

    JavaScript primitives like `string` and `number` have object wrapper types
    like `String` and `Number` which are used when calling methods on
    primitives. `JSPrimitiveObject` represents primitives wrapped in this way.

    In JavaScript, the difference between a wrapped and plain primitive is not
    visible, and the same is the case by default with `v8serialize`, as the
    default decoding behaviour is to unwrap wrapped primitive objects. So users
    of `v8serialize` shouldn't encounter this type in decoded values, and don't
    need to handle it.

    `JSPrimitiveObject` has two main uses:

    * It allows primitive values to be serialized once and referenced multiple
        times in a V8 serialized data stream. This could be used to de-duplicate
        strings or bigints.
    * It allows data streams to be round-tripped exactly.
    """

    value: T
    """The primitive value."""
    tag: PrimitiveObjectTag
    """The type of primitive wrapped in this object."""

    def __init__(self, value: T, tag: PrimitiveObjectTag | None = None) -> None:
        object.__setattr__(self, "value", value)

        expected_tag: PrimitiveObjectTag
        expected_tag2: PrimitiveObjectTag | None = None
        if isinstance(value, str):
            expected_tag = SerializationTag.kStringObject
        elif value is True:
            expected_tag = SerializationTag.kTrueObject
        elif value is False:
            expected_tag = SerializationTag.kFalseObject
        elif isinstance(value, float):
            expected_tag = SerializationTag.kNumberObject
        elif isinstance(value, int):
            if value in FLOAT64_SAFE_INT_RANGE:
                expected_tag = SerializationTag.kNumberObject
                expected_tag2 = SerializationTag.kBigIntObject
            else:
                expected_tag = SerializationTag.kBigIntObject
        else:
            raise TypeError("value is not a supported primitive type")

        if tag is None:
            object.__setattr__(self, "tag", expected_tag)
        elif expected_tag is not tag and expected_tag2 is not tag:
            if expected_tag2 is not None:
                msg = f"tag must be {expected_tag} or {expected_tag2}"
            else:
                msg = f"tag must be {expected_tag}"

            raise ValueError(f"{msg} with value {value!r} of type {type(value)}")
        else:
            object.__setattr__(self, "tag", tag)
