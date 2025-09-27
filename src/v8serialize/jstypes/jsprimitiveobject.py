from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Generic, Literal, Union, overload

from v8serialize.constants import (
    FLOAT64_SAFE_INT_RANGE,
    PrimitiveObjectTag,
    SerializationTag,
)
from v8serialize.jstypes.jsbigint import JSBigInt

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

PrimitiveObjectValue: TypeAlias = Union[float, bool, JSBigInt, str]
"""
The types that can be wrapped in a [JSPrimitiveObject].

[JSPrimitiveObject]: `v8serialize.jstypes.JSPrimitiveObject`
"""

if TYPE_CHECKING:
    from typing_extensions import TypeVar

    T_co = TypeVar(
        "T_co", bound=PrimitiveObjectValue, default=PrimitiveObjectValue, covariant=True
    )
    TagT_co = TypeVar(
        "TagT_co", bound=PrimitiveObjectTag, default=PrimitiveObjectTag, covariant=True
    )
else:
    from typing import TypeVar

    T_co = TypeVar("T_co", bound=PrimitiveObjectValue)
    TagT_co = TypeVar("TagT_co", bound=PrimitiveObjectTag)


@dataclass(frozen=True, order=True, init=False, slots=True)
class JSPrimitiveObject(Generic[T_co, TagT_co], metaclass=ABCMeta):
    """
    Python equivalent of a wrapped/boxed JavaScript primitive.

    :::{.callout-tip}
    This is a low-level type that won't occur in decoded data by default, and
    can be ignored.

    If you *do* want it to occur in decoded data, pass the
    `js_primitive_objects=True` option to [`loads()`] or [`TagReader`].
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


    ---
    Each `tag` has a single `value` type:

    | `tag`           | JavaScript | Python `value` |
    |-----------------|----------- |----------------|
    | [kTrueObject]   | `true`     | `True`         |
    | [kFalseObject]  | `false`    | `False`        |
    | [kNumberObject] | `number`   | `float`        |
    | [kBigIntObject] | `bigint`   | `JSBigInt`     |
    | [kStringObject] | `string`   | `str`          |

    The constructor infers the tag automatically given a value of one of these
    Python types.

    An `int` `value` is inferred as [kNumberObject] if it's in
    [FLOAT64_SAFE_INT_RANGE], otherwise [kBigIntObject]. The `int` is converted
    to `float` or `JSBigInt` according to the inferred `tag`.

    [kTrueObject]: `v8serialize.constants.SerializationTag.kTrueObject`
    [kFalseObject]: `v8serialize.constants.SerializationTag.kFalseObject`
    [kNumberObject]: `v8serialize.constants.SerializationTag.kNumberObject`
    [kBigIntObject]: `v8serialize.constants.SerializationTag.kBigIntObject`
    [kStringObject]: `v8serialize.constants.SerializationTag.kStringObject`
    [FLOAT64_SAFE_INT_RANGE]: `v8serialize.constants.FLOAT64_SAFE_INT_RANGE`
    [`loads()`]: `v8serialize.decode.loads`
    [`TagReader`]: `v8serialize.decode.TagReader`

    Parameters
    ----------
    value:
        The Python type representing the wrapped JavaScript primitive value.
    tag:
        The serialization tag that identifies the type of the wrapped primitive.

        Inferred from the value if `None`.
    """

    value: Final[T_co]  # type: ignore[misc]  # mypy thinks it's uninitialised
    """The primitive value."""
    tag: Final[TagT_co]  # type: ignore[misc]
    """The type of primitive wrapped in this object."""

    @overload
    def __init__(
        self: TrueJSPrimitiveObject,
        value: Literal[True],
        tag: Literal[SerializationTag.kTrueObject] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: FalseJSPrimitiveObject,
        value: Literal[False],
        tag: Literal[SerializationTag.kFalseObject] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: NumberJSPrimitiveObject,
        value: float,  # also allows int
        tag: Literal[SerializationTag.kNumberObject],
    ) -> None: ...

    @overload
    def __init__(
        self: BigIntJSPrimitiveObject,
        value: int,
        tag: Literal[SerializationTag.kBigIntObject],
    ) -> None: ...

    @overload
    def __init__(
        self: BigIntJSPrimitiveObject,
        value: JSBigInt,
        tag: None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: NumberJSPrimitiveObject | BigIntJSPrimitiveObject,
        value: int,
        tag: None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: NumberJSPrimitiveObject,
        value: float,
        tag: None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: StringJSPrimitiveObject,
        value: str,
        tag: Literal[SerializationTag.kStringObject] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: UnknownJSPrimitiveObject,
        value: PrimitiveObjectValue | int,
        tag: None = None,
    ) -> None: ...

    def __init__(
        self, value: PrimitiveObjectValue | int, tag: PrimitiveObjectTag | None = None
    ) -> None:
        if isinstance(value, str):
            tag = _require_tag(SerializationTag.kStringObject, tag=tag, value=value)
        elif value is True:
            tag = _require_tag(SerializationTag.kTrueObject, tag=tag, value=value)
        elif value is False:
            tag = _require_tag(SerializationTag.kFalseObject, tag=tag, value=value)
        elif isinstance(value, float):
            tag = _require_tag(SerializationTag.kNumberObject, tag=tag, value=value)
        elif isinstance(value, JSBigInt):
            tag = _require_tag(SerializationTag.kBigIntObject, tag=tag, value=value)
        elif isinstance(value, int):
            # non-specific int values are always cast to a tag-specific type.
            # Unlike unboxed Number values, NumberObject values are always
            # serialized as Double (i.e. float64) values, never int types like
            # Int32.
            if tag is SerializationTag.kNumberObject:
                value = float(value)
            elif tag is SerializationTag.kBigIntObject:
                value = JSBigInt(value)
            else:
                default_tag: PrimitiveObjectTag = (
                    SerializationTag.kNumberObject
                    if value in FLOAT64_SAFE_INT_RANGE
                    else SerializationTag.kBigIntObject
                )
                tag = _require_tag(
                    SerializationTag.kNumberObject,
                    SerializationTag.kBigIntObject,
                    tag=tag,
                    value=value,
                    default_tag=default_tag,
                )
                value = (
                    float(value)
                    if tag is SerializationTag.kNumberObject
                    else JSBigInt(value)
                )
        else:
            raise TypeError("value is not a supported primitive type")

        assert tag is not None and isinstance(value, (str, bool, float, JSBigInt))
        object.__setattr__(self, "tag", tag)
        object.__setattr__(self, "value", value)


@overload
def _require_tag(
    allowed_tag1: PrimitiveObjectTag,
    allowed_tag2: PrimitiveObjectTag,
    /,
    *,
    tag: PrimitiveObjectTag | None,
    value: object,
    default_tag: PrimitiveObjectTag,
) -> PrimitiveObjectTag: ...


@overload
def _require_tag(
    allowed_tag1: PrimitiveObjectTag,
    /,
    *,
    tag: PrimitiveObjectTag | None,
    value: object,
) -> PrimitiveObjectTag: ...


def _require_tag(
    *allowed_tags: PrimitiveObjectTag,
    tag: PrimitiveObjectTag | None,
    value: object,
    default_tag: PrimitiveObjectTag | None = None,
) -> PrimitiveObjectTag:
    assert len(allowed_tags) > 0
    if tag is None or tag in allowed_tags:
        return tag or default_tag or allowed_tags[0]
    msg = f"tag must be {' or '.join(str(t) for t in allowed_tags)}"
    raise ValueError(f"{msg} with value {value!r} of type {type(value)}")


# fmt: off
TrueJSPrimitiveObject: TypeAlias =   JSPrimitiveObject[Literal[True],  Literal[SerializationTag.kTrueObject]]    # noqa: E501
FalseJSPrimitiveObject: TypeAlias =  JSPrimitiveObject[Literal[False], Literal[SerializationTag.kFalseObject]]   # noqa: E501
NumberJSPrimitiveObject: TypeAlias = JSPrimitiveObject[float,          Literal[SerializationTag.kNumberObject]]  # noqa: E501
BigIntJSPrimitiveObject: TypeAlias = JSPrimitiveObject[JSBigInt,       Literal[SerializationTag.kBigIntObject]]  # noqa: E501
StringJSPrimitiveObject: TypeAlias = JSPrimitiveObject[str,            Literal[SerializationTag.kStringObject]]  # noqa: E501
UnknownJSPrimitiveObject: TypeAlias = Union[
    TrueJSPrimitiveObject,
    FalseJSPrimitiveObject,
    NumberJSPrimitiveObject,
    BigIntJSPrimitiveObject,
    StringJSPrimitiveObject
]
# fmt: on
