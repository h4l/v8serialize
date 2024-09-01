from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass
from typing_extensions import TYPE_CHECKING, Generic, TypeVar

from v8serialize.constants import (
    FLOAT64_SAFE_INT_RANGE,
    PrimitiveObjectTag,
    SerializationTag,
)

if TYPE_CHECKING:
    T = TypeVar("T", bound=float | bool | int | str, default=float | bool | int | str)
else:
    T = TypeVar("T", bound=float | bool | int | str)


@dataclass(frozen=True, order=True, slots=True, init=False)
class JSPrimitiveObject(Generic[T], metaclass=ABCMeta):
    value: T
    tag: PrimitiveObjectTag

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
