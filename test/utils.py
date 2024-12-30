from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def typeval(x: T) -> tuple[type[T], T]:
    return type(x), x
