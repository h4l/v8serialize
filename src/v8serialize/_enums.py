from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import TypeVar

TypeT = TypeVar("TypeT", bound=type)


def frozen_setattr(cls: type, name: str, value: object) -> None:
    raise FrozenInstanceError(f"Cannot assign to field {name!r}")


def frozen(cls: TypeT) -> TypeT:
    """Disable `__setattr__`, much like @dataclass(frozen=True)."""
    cls.__setattr__ = frozen_setattr  # type: ignore[method-assign,assignment]
    return cls
