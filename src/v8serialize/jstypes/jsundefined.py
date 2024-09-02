from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


class JSUndefinedEnum(Enum):
    """Defines the JSUndefined enum value."""

    JSUndefined = "JSUndefined"
    """Represents the JavaScript value `undefined`."""

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


JSUndefinedType: TypeAlias = Literal[JSUndefinedEnum.JSUndefined]
JSUndefined: Final = JSUndefinedEnum.JSUndefined
"""Represents the JavaScript value `undefined`."""
