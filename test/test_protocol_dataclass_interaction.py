from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:

    @runtime_checkable
    class Proto(Protocol):
        @property
        def thing(self) -> int: ...

else:

    @runtime_checkable
    class Proto(Protocol):
        # Assigning a field is enough for @runtime_checkable to check its
        # presence, but without an annotation it won't affect @dataclass.
        thing = ...


@dataclass
class Thing(Proto):
    thing: int


@dataclass
class ImplicitThing:
    thing: int


@dataclass
class NonThing:
    thing2: int


def test_runtime_checkable_dual_typing_runtime_protocol() -> None:
    assert isinstance(Thing(1), Proto)
    assert isinstance(ImplicitThing(1), Proto)
    assert not isinstance(NonThing(1), Proto)


# Can also have one definition and override the descriptors immediately
@runtime_checkable
class Proto2(Protocol):
    if TYPE_CHECKING:

        @property
        def thing(self) -> int: ...

    else:
        thing = ...


@dataclass
class Thing2(Proto2):
    thing: int


@dataclass
class ImplicitThing2:
    thing: int


@dataclass
class NonThing2:
    thing2: int


def test_runtime_checkable_removed_descriptor_runtime_protocol() -> None:
    # type check
    obj: Proto2 = Thing2(1)
    foo = ImplicitThing2(1)
    foo = NonThing2(1)  # type: ignore[assignment]

    assert obj and foo  # not unused

    assert isinstance(Thing2(1), Proto2)
    assert isinstance(ImplicitThing2(1), Proto2)
    assert not isinstance(NonThing2(1), Proto2)
