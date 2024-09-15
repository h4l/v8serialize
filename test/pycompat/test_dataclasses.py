from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, dataclass
from typing import Generic, TypeVar

import pytest

from v8serialize._pycompat.dataclasses import FrozenAfterInitDataclass, slots_if310

T = TypeVar("T")


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 10), reason="Test applies only to py310"
)
def test_frozen_generic_dataclass() -> None:
    @dataclass(frozen=True, slots=True)  # type: ignore[call-overload]  # for py39
    class BrokenOn310(Generic[T]):
        foo: T

    # Using the class directly works
    assert BrokenOn310(foo="")

    # Subscripting with a type does not
    with pytest.raises(
        TypeError,
        match=r"super\(type, obj\): obj must be an instance or subtype of type",
    ):
        BrokenOn310[str](foo="")

    @dataclass(slots=True)  # type: ignore[call-overload]  # for py39
    class OKOn310(FrozenAfterInitDataclass, Generic[T]):
        foo: T

    assert OKOn310[str](foo="")


def test_FrozenAfterInitDataclass() -> None:
    @dataclass(unsafe_hash=True, **slots_if310())
    class Example(FrozenAfterInitDataclass):
        a: int

    e = Example(a=1)
    assert e.a == 1

    with pytest.raises(FrozenInstanceError):
        e.a = 2

    with pytest.raises(FrozenInstanceError):
        del e.a

    assert Example(a=1) == Example(a=1)
    assert hash(Example(a=1)) == hash(Example(a=1))

    # No need for object.__setattr__ to initialise frozen fields
    @dataclass(init=False)
    class Example2(Example):
        b: str

        def __init__(self, a: int) -> None:
            super().__init__(a)
            self.b = str(a)

    ex2 = Example2(10)
    assert ex2.a == 10
    assert ex2.b == "10"
